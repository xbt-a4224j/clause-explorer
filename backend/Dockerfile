FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY data/ ./data/
ENV PYTHONPATH=/app/backend PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD curl -fs http://localhost:8000/healthz || exit 1
CMD ["uvicorn", "explorer.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
