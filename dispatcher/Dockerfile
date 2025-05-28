FROM python:3.12-slim

WORKDIR /app

COPY dispatcher/dispatcher.py .
COPY certs ./certs
COPY logs ./logs
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000

CMD ["python", "dispatcher.py"]