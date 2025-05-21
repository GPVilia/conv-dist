import os
import requests
import consul
from flask import Flask, request, jsonify, send_file
from flask_httpauth import HTTPBasicAuth
from werkzeug.utils import secure_filename
import logging
from io import BytesIO

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
    if filetype in ["docx", "pdf"]:
        service = "service-text"
    elif filetype in ["jpg", "png"]:
        service = "service-image"
    else:
        return None
    services = c.agent.services()
    for s in services.values():
        if s["Service"] == service:
            return s
    return None

@app.route("/convert", methods=["POST"])
@auth.login_required
def dispatch():
    if 'file' not in request.files or 'target_format' not in request.form:
        return jsonify({"error": "Missing file or target_format"}), 400
    file = request.files['file']
    target_format = request.form['target_format'].lower()
    filename = secure_filename(file.filename)
    ext = filename.rsplit('.', 1)[-1].lower()

    # Descobrir serviço
    service = discover_service(target_format)
    if not service:
        return jsonify({"error": "No service found for this format"}), 404

    url = f"https://127.0.0.1:{service['Port']}/convert"
    files = {'file': (filename, file.stream, file.mimetype)}
    data = {"format": target_format} if service["Service"] == "service-image" else {}

    try:
        resp = requests.post(
            url,
            files=files,
            data=data,
            auth=(USERNAME, PASSWORD),
            verify=False,
            timeout=60
        )
        if resp.status_code == 200:
            return send_file(BytesIO(resp.content), download_name=f"converted.{target_format}", as_attachment=True)
        else:
            return jsonify({"error": resp.text}), resp.status_code
    except Exception as e:
        logging.error(f"Dispatcher error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../certs"))
    cert_path = os.path.join(base_dir, "server.crt")
    key_path = os.path.join(base_dir, "server.key")
    context = (cert_path, key_path)
    app.run(host="127.0.0.1", port=SERVICE_PORT, ssl_context=context)