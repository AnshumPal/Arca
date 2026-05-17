FROM python:3.11-slim

WORKDIR /app

# Install dependencies first — Docker layer caching keeps rebuilds fast
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code only (tests, docs, .env excluded via .dockerignore)
COPY app/ ./app/

# Cloud Run injects PORT — must listen on it; fall back to 8080
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
