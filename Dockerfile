FROM python:3.11-slim

# Install Tesseract
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway sets PORT env var, default to 8000 for local testing
ENV PORT=8000

# Use python -m to ensure uvicorn is found
CMD python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
