# Data-plane API-key gateway -- separate image/service from the control
# plane at the repo root. No shared dependencies, no shared code.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --timeout=100 --retries=5 -r requirements.txt

COPY keystore.py app.py manage_keys.py ./

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8080
ENTRYPOINT ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
