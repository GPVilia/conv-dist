import os
from flask import Flask, request, send_file, jsonify, after_this_request
from flask_httpauth import HTTPBasicAuth
from werkzeug.utils import secure_filename
from PIL import Image
import logging
import consul
import tempfile

# Configurações
USERNAME = os.getenv("BASIC_AUTH_USERNAME", "admin")
PASSWORD = os.getenv("BASIC_AUTH_PASSWORD", "admin_password")
SERVICE_NAME = "service-image"
SERVICE_PORT = 5002

# Configuração de logs
base_log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../logs"))
if not os.path.exists(base_log_dir):
    os.makedirs(base_log_dir)
log_file = os.path.join(base_log_dir, "service-logs", "service-image-logs.txt")
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
    logging.info(f"Autenticação recebida para o utilizador: {username}")
    return username == USERNAME and password == PASSWORD

@app.route("/convert", methods=["POST"])
@auth.login_required
def convert_image():
    logging.info("Pedido recebido para conversão de imagem.")
    if 'file' not in request.files:
        logging.warning("Nenhum ficheiro foi enviado no pedido.")
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        logging.warning("Nenhum ficheiro foi selecionado.")
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    input_path = os.path.join(tempfile.gettempdir(), filename)
    file.save(input_path)

    output_format = request.form.get("format", "").lower()
    if output_format not in ["jpg", "png", "gif"]:
        logging.warning("Formato de destino inválido.")
        return jsonify({"error": "Invalid format. Supported formats: jpg, png, gif"}), 400

    output_path = input_path.rsplit('.', 1)[0] + f".{output_format}"

    try:
        with Image.open(input_path) as img:
            if output_format in ["jpg", "jpeg"]:
                if img.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])  # Usa o canal alpha como máscara
                    img = background
                else:
                    img = img.convert("RGB")
            elif output_format == "gif":
                img = img.convert("P", palette=Image.ADAPTIVE)
            format_map = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "gif": "GIF"}
            img.save(output_path, format_map.get(output_format, output_format.upper()))
        logging.info(f"Ficheiro {filename} convertido com sucesso para {output_format.upper()}.")

        @after_this_request
        def cleanup(response):
            try:
                if os.path.exists(input_path):
                    os.remove(input_path)
                if os.path.exists(output_path):
                    os.remove(output_path)
            except Exception as e:
                logging.error(f"Erro ao remover ficheiros temporários: {e}")
            return response

        return send_file(output_path, as_attachment=True)
    except Exception as e:
        logging.error(f"Erro ao converter {filename}: {e}")
        # Limpeza mesmo em caso de erro
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
            if os.path.exists(output_path):
                os.remove(output_path)
        except Exception as err:
            logging.error(f"Erro ao remover ficheiros temporários após erro: {err}")
        return jsonify({"error": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    logging.info("Health check recebido.")
    return jsonify({"status": "ok"}), 200

def register_service():
    consul_host = os.getenv("CONSUL_HTTP_ADDR", "localhost:8500").split(":")[0]
    consul_port = int(os.getenv("CONSUL_HTTP_ADDR", "localhost:8500").split(":")[1])
    c = consul.Consul(host=consul_host, port=consul_port)
    check = {
        "http": f"https://host.docker.internal:{SERVICE_PORT}/health",
        "interval": "10s",
        "tls_skip_verify": True
    }
    c.agent.service.register(
        name=SERVICE_NAME,
        service_id=SERVICE_NAME,
        address="service-image",
        port=SERVICE_PORT,
        tags=["image", "jpg", "png", "gif"],
        check=check
    )
    logging.info("Serviço registado no Consul.")

if __name__ == "__main__":
    register_service()
    cert_path = os.path.join("certs", "server.crt")
    key_path = os.path.join("certs", "server.key")
    context = (cert_path, key_path)
    logging.info("Serviço iniciado.")
    app.run(host="0.0.0.0", port=SERVICE_PORT, ssl_context=context)