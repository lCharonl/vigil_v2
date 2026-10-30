"""Vigil V2 entry point: wires ingestion, engine and output together."""

import argparse
import asyncio
import logging

from src.core.queue_manager import QueueManager
from src.engine.scorer import Scorer
from src.ingestion.certstream_ws import DEFAULT_URL, CertstreamClient
from src.output.dispatcher import AlertDispatcher
from src.output.formatter import AlertFormatter

logger = logging.getLogger("vigil")


async def engine_worker(
    queue: QueueManager,
    scorer: Scorer,
    formatter: AlertFormatter,
    dispatcher: AlertDispatcher,
) -> None:
    """Consume the queue, score each domain and emit alerts.

    Args:
        queue: Queue fed by the ingestion layer.
        scorer: Scoring engine.
        formatter: Alert formatter.
        dispatcher: Alert destination.
    """
    while True:
        event = await queue.get()
        try:
            result = scorer.evaluate(event)
            if scorer.is_suspicious(result):
                await dispatcher.dispatch(formatter.to_json(result))
        except Exception:
            logger.exception("Échec de traitement pour %s", event.domain)
        finally:
            queue.task_done()


async def stats_reporter(queue: QueueManager, interval: float) -> None:
    """Periodically log the queue state.

    Args:
        queue: Queue to monitor.
        interval: Delay in seconds between two reports.
    """
    while True:
        await asyncio.sleep(interval)
        logger.info("file=%d abandonnés=%d", queue.qsize(), queue.dropped)


async def run(args: argparse.Namespace) -> None:
    """Initialize the components and start the concurrent tasks.

    Args:
        args: Parsed command-line arguments.
    """
    queue = QueueManager(maxsize=args.queue_size)
    scorer = Scorer(threshold=args.threshold)
    formatter = AlertFormatter()
    dispatcher = AlertDispatcher(file_path=args.output_file)
    client = CertstreamClient(queue, url=args.url)

    tasks = [
        asyncio.create_task(client.run(), name="ingestion"),
        asyncio.create_task(stats_reporter(queue, args.stats_interval), name="stats"),
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
    """Parse command-line arguments.

    Returns:
        The Vigil runtime parameters.
    """
    parser = argparse.ArgumentParser(description="Vigil V2 - détection de phishing via CertStream")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL du serveur CertStream")
    parser.add_argument("--threshold", type=int, default=50, help="score minimal d'alerte")
    parser.add_argument("--output-file", default=None, help="fichier JSON Lines de sortie")
    parser.add_argument("--queue-size", type=int, default=10000, help="capacité de la file")
    parser.add_argument("--workers", type=int, default=1, help="nombre de consommateurs")
    parser.add_argument("--stats-interval", type=float, default=60.0, help="période des stats (s)")
    parser.add_argument("--verbose", action="store_true", help="active les logs DEBUG")
    return parser.parse_args()


def main() -> None:
    """Configure logging and start the asyncio event loop."""
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        logger.info("Arrêt demandé")


if __name__ == "__main__":
    main()
