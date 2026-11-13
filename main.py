"""Vigil V2 entry point: wires ingestion, engine and output together."""

import argparse
import asyncio
import logging

from src.core.queue_manager import QueueManager
from src.engine.rules_brand import load_brand_index, load_typosquat_index
from src.engine.scorer import Scorer
from src.engine.whitelist import Whitelist
from src.ingestion.certstream_ws import DEFAULT_URL, CertstreamClient
from src.output.archiver import AlertArchiver
from src.output.dispatcher import AlertDispatcher
from src.output.formatter import AlertFormatter

logger = logging.getLogger("vigil")


async def engine_worker(
    queue: QueueManager,
    scorer: Scorer,
    formatter: AlertFormatter,
    dispatcher: AlertDispatcher,
) -> None:
    while True:
        event = await queue.get()
        try:
            result = scorer.evaluate(event)
            if scorer.is_suspicious(result):
                await dispatcher.dispatch(formatter.to_json(result))
        except Exception:
            logger.exception("Processing failed for %s", event.domain)
        finally:
            queue.task_done()


async def stats_reporter(queue: QueueManager, interval: float) -> None:
    while True:
        await asyncio.sleep(interval)
        logger.info("queue=%d dropped=%d", queue.qsize(), queue.dropped)


async def run(args: argparse.Namespace) -> None:
    await asyncio.to_thread(load_brand_index)
    await asyncio.to_thread(load_typosquat_index)
    queue = QueueManager(maxsize=args.queue_size)
    scorer = Scorer(threshold=args.threshold, whitelist=Whitelist.from_file(args.whitelist))
    formatter = AlertFormatter()
    archiver = (
        AlertArchiver(args.archive_dir, retention_days=args.archive_retention_days)
        if args.archive
        else None
    )
    dispatcher = AlertDispatcher(file_path=args.output_file, archiver=archiver)
    client = CertstreamClient(queue, url=args.url)

    tasks = [
        asyncio.create_task(client.run(), name="ingestion"),
        asyncio.create_task(stats_reporter(queue, args.stats_interval), name="stats"),
        *(
            [asyncio.create_task(archiver.run_maintenance(), name="archive")]
            if archiver is not None
            else []
        ),
        *(
            asyncio.create_task(
                engine_worker(queue, scorer, formatter, dispatcher),
                name=f"engine-{i}",
            )
            for i in range(args.workers)
        ),
    ]

    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vigil V2 - phishing detection from the CertStream feed")
    parser.add_argument("--url", default=DEFAULT_URL, help="CertStream server URL")
    parser.add_argument("--threshold", type=int, default=50, help="minimum score to raise an alert")
    parser.add_argument("--whitelist", default=None, help="YAML file of whitelist regexes")
    parser.add_argument("--output-file", default=None, help="JSON Lines output file")
    parser.add_argument(
        "--archive",
        action="store_true",
        help="enable hourly archive, daily zip and retention purge",
    )
    parser.add_argument("--archive-dir", default="archive", help="archive root directory")
    parser.add_argument(
        "--archive-retention-days",
        type=int,
        default=30,
        help="days of zipped archives to keep",
    )
    parser.add_argument("--queue-size", type=int, default=10000, help="queue capacity")
    parser.add_argument("--workers", type=int, default=1, help="number of engine consumers")
    parser.add_argument("--stats-interval", type=float, default=60.0, help="stats reporting interval (s)")
    parser.add_argument("--verbose", action="store_true", help="enable DEBUG logs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        logger.info("Shutdown requested")


if __name__ == "__main__":
    main()
