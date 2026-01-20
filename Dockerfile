FROM python:3.12

# Install Tesseract OCR
RUN apt-get update && \
    apt-get install -y tesseract-ocr tesseract-ocr-eng && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Default port (Railway overrides via PORT env)
ENV PORT=8000

# Start command
CMD python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
