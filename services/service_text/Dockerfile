FROM python:3.12-slim

WORKDIR /app

COPY services/service_text/service.py .
COPY certs ./certs
COPY logs ./logs
COPY requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

# Instala o poppler-utils para PDF->PNG (Linux)
RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*

EXPOSE 5001

CMD ["python", "service.py"]