FROM python:3.12-slim

WORKDIR /app

COPY services/service_image/service.py .
COPY certs ./certs
COPY logs ./logs
COPY requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5002

CMD ["python", "service.py"]