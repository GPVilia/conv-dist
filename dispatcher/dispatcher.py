import os
import requests
import consul
from flask import Flask, request, jsonify, send_file
from flask_httpauth import HTTPBasicAuth
from werkzeug.utils import secure_filename
import logging
from io import BytesIO
import pika
import json
import base64

# --- OpenCL imports (opcional, para demonstração de disponibilidade) ---
try:
    import pyopencl as cl
    import numpy as np
    OPENCL_AVAILABLE = True
except ImportError:
    OPENCL_AVAILABLE = False

USERNAME = os.getenv("BASIC_AUTH_USERNAME", "admin")
PASSWORD = os.getenv("BASIC_AUTH_PASSWORD", "admin_password")
CONSUL_HTTP_ADDR = os.getenv("CONSUL_HTTP_ADDR", "localhost:8500")
SERVICE_PORT = 5000

# Configuração de logs
base_log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../logs"))
if not os.path.exists(base_log_dir):
    os.makedirs(base_log_dir)
log_file = os.path.join(base_log_dir, "dispatcher-logs.txt")
if not os.path.exists(os.path.dirname(log_file)):
    os.makedirs(os.path.dirname(log_file))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),  # Logs para o ficheiro
        logging.StreamHandler()        # Logs para o terminal
    ]
)

app = Flask(__name__)
auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username, password):
    return username == USERNAME and password == PASSWORD

def discover_service(filetype):
    consul_host, consul_port = CONSUL_HTTP_ADDR.split(":")
    c = consul.Consul(host=consul_host, port=int(consul_port))
    # filetype é a extensão do ficheiro de origem!
    if filetype in ["docx", "pdf"]:
        service = "service-text"
    elif filetype in ["jpg", "jpeg", "png", "gif"]:
        service = "service-image"
    else:
        return None
    services = c.agent.services()
    for s in services.values():
        if s["Service"] == service:
            return s
    return None

def publish_to_queue(payload, queue_name):
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='rabbitmq'))
    channel = connection.channel()
    channel.queue_declare(queue=queue_name, durable=True)
    channel.basic_publish(
        exchange='',
        routing_key=queue_name,
        body=json.dumps(payload),
        properties=pika.BasicProperties(delivery_mode=2)
    )
    connection.close()

@app.route("/convert", methods=["POST"])
@auth.login_required
def dispatch():
    if 'file' not in request.files or 'target_format' not in request.form:
        return jsonify({"error": "Missing file or target_format"}), 400
    file = request.files['file']
    target_format = request.form['target_format'].lower()
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[-1].lower()

    # Descobrir serviço com base na extensão do ficheiro de origem!
    service = discover_service(ext)
    if not service:
        return jsonify({"error": "No service found for this format"}), 404

    # --- CALLBACK SYSTEM ---
    callback_url = request.form.get("callback_url")
    if not callback_url:
        return jsonify({"error": "Missing callback_url"}), 400

    # Codifica o ficheiro em base64 para enviar na fila
    file_bytes = file.read()
    payload = {
        "filename": filename,
        "file_bytes": base64.b64encode(file_bytes).decode("utf-8"),
        "target_format": target_format,
        "callback_url": callback_url
    }
    queue_name = "text_convert_queue" if service["Service"] == "service-text" else "image_convert_queue"
    publish_to_queue(payload, queue_name)
    logging.info(f"Pedido publicado em {queue_name} com callback_url: {callback_url}")
    return jsonify({"status": "Pedido enviado para processamento assíncrono via RabbitMQ! O resultado será enviado para o callback_url."}), 202

@app.route("/health", methods=["GET"])
def health():
    # Mostra se OpenCL está disponível no dispatcher
    return jsonify({"status": "ok", "opencl": OPENCL_AVAILABLE}), 200

if __name__ == "__main__":
    cert_path = os.path.join("certs", "server.crt")
    key_path = os.path.join("certs", "server.key")
    context = (cert_path, key_path)
    app.run(host="0.0.0.0", port=SERVICE_PORT, ssl_context=context)