FROM python:3.11-slim

# Apply available distribution security fixes before installing application packages.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER 10001
# Instrumentação automática OpenTelemetry (Flask, requests, psycopg2 e logging).
# O endpoint OTLP vem de OTEL_EXPORTER_OTLP_ENDPOINT, definido no ambiente de execução.
ENV OTEL_SERVICE_NAME=flag-service \
    OTEL_TRACES_EXPORTER=otlp \
    OTEL_METRICS_EXPORTER=otlp \
    OTEL_LOGS_EXPORTER=otlp \
    OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
    OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true \
    OTEL_SEMCONV_STABILITY_OPT_IN=http \
    OTEL_PYTHON_EXCLUDED_URLS=health

EXPOSE 8002
CMD ["sh", "-c", "exec opentelemetry-instrument gunicorn --bind 0.0.0.0:${PORT:-8002} app:app"]
