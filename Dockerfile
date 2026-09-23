# Container für den Betrieb mit Docker (lokal, eigener Server, Azure Container Apps, ...).
# Build-Kontext ist das Repository-Hauptverzeichnis:
#   docker compose up -d --build
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CONFIG_PATH=/config/xml_to_xlsx_config.json

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Konverter (Umwandlungslogik) + Standard-Feldkonfiguration
COPY converter/xml_to_xlsx.py /app/xml_to_xlsx.py
COPY converter/xml_to_xlsx_config.json /config/xml_to_xlsx_config.json

# REST-API
COPY app/ /app/

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
