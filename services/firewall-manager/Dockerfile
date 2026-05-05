FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        "httpx==0.27.2" \
        "pyyaml==6.0.2" \
        "structlog==24.4.0"

COPY services/firewall-manager/manager.py /app/manager.py

EXPOSE 8081

ENTRYPOINT ["python", "-u", "/app/manager.py"]
