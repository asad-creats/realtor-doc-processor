# Backend image for Hugging Face Spaces (Docker SDK, port 7860).
FROM python:3.11-slim

WORKDIR /app

# poppler-utils + tesseract-ocr are only needed for scanned/image PDFs.
# Included so scanned packets degrade gracefully instead of failing.
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

# HF Spaces sets PORT=7860. Writable job dir for output zips.
ENV PORT=7860
ENV JOBS_DIR=/tmp
EXPOSE 7860

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
