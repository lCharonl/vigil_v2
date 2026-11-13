FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./
COPY src ./src

RUN useradd --system --uid 10001 vigil \
    && mkdir /data \
    && chown vigil /data

USER vigil
VOLUME /data

ENTRYPOINT ["python", "main.py"]
CMD ["--output-file", "/data/alerts.jsonl", "--archive", "--archive-dir", "/data/archive"]
