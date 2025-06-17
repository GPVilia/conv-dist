import os
from flask import Flask, request, send_file, jsonify, after_this_request
from flask_httpauth import HTTPBasicAuth
from werkzeug.utils import secure_filename
import logging
import consul
import tempfile
import requests

# --- RabbitMQ imports ---
import pika
import json
import base64
import threading

# --- OpenCL imports ---
try:
    import pyopencl as cl
    import numpy as np
    from PIL import Image
    OPENCL_AVAILABLE = True
except ImportError:
    from PIL import Image
    OPENCL_AVAILABLE = False

USERNAME = os.getenv("BASIC_AUTH_USERNAME", "admin")
PASSWORD = os.getenv("BASIC_AUTH_PASSWORD", "admin_password")
SERVICE_NAME = "service-image"
SERVICE_PORT = 5002

# Configuração de logs
base_log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../logs"))
if not os.path.exists(base_log_dir):
    os.makedirs(base_log_dir)
log_dir = os.path.join(base_log_dir, "service-logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
log_file = os.path.join(log_dir, "service-image-logs.txt")

# --- Configuração manual dos handlers (igual ao service_text) ---
logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# Remove handlers antigos (importante para evitar duplicados)
if logger.hasHandlers():
    logger.handlers.clear()

file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)
# --- FIM DA CORREÇÃO ---

app = Flask(__name__)
auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username, password):
    logging.info(f"Autenticação recebida para o utilizador: {username}")
    return username == USERNAME and password == PASSWORD

def opencl_invert_image(img_path):
    if not OPENCL_AVAILABLE:
        return
    try:
        img = Image.open(img_path).convert("RGB")
        img_np = np.array(img).astype(np.uint8)
        flat_img = img_np.flatten()

        ctx = cl.create_some_context()
        queue = cl.CommandQueue(ctx)
        mf = cl.mem_flags
        buf = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=flat_img)

        kernel = """
        __kernel void invert(__global uchar *data) {
            int i = get_global_id(0);
            data[i] = 255 - data[i];
        }
        """
        prg = cl.Program(ctx, kernel).build()
        prg.invert(queue, flat_img.shape, None, buf)
        result = np.empty_like(flat_img)
        cl.enqueue_copy(queue, result, buf)
        img_out = Image.fromarray(result.reshape(img_np.shape))
        img_out.save(img_path)
        logging.info(f"Imagem processada com OpenCL (inversão de cores): {img_path}")
    except Exception as e:
        logging.warning(f"Erro ao processar imagem com OpenCL: {e}")

def save_image_with_opencl(img, output_path, output_format):
    img.save(output_path, output_format)
    try:
        opencl_invert_image(output_path)
    except Exception as e:
        logging.warning(f"OpenCL não disponível ou erro ao inverter imagem: {e}")
    return output_path

def process_image_conversion(data):
    """
    Função para processar pedidos vindos do RabbitMQ.
    Agora envia o resultado para o callback_url fornecido.
    """
    try:
        filename = data["filename"]
        file_bytes = base64.b64decode(data["file_bytes"])
        output_format = data["output_format"] if "output_format" in data else data.get("target_format")
        callback_url = data.get("callback_url")
        input_path = os.path.join(tempfile.gettempdir(), filename)
        with open(input_path, "wb") as f:
            f.write(file_bytes)

        output_path = input_path.rsplit('.', 1)[0] + f".{output_format}"

        with Image.open(input_path) as img:
            if output_format in ["jpg", "jpeg"]:
                if img.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                else:
                    img = img.convert("RGB")
            elif output_format == "gif":
                img = img.convert("P", palette=Image.ADAPTIVE)
            format_map = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "gif": "GIF"}
            save_image_with_opencl(img, output_path, format_map.get(output_format, output_format.upper()))
        logging.info(f"Ficheiro {filename} convertido com sucesso para {output_format.upper()}.")

        # --- CALLBACK: envia o ficheiro convertido para o callback_url ---
        if callback_url and os.path.exists(output_path):
            with open(output_path, "rb") as f:
                files = {"file": (os.path.basename(output_path), f)}
                try:
                    resp = requests.post(callback_url, files=files, timeout=30)
                    if resp.status_code == 200:
                        logging.info(f"Ficheiro enviado com sucesso para callback_url: {callback_url}")
                    else:
                        logging.error(f"Falha ao enviar ficheiro para callback_url: {callback_url} | Status: {resp.status_code}")
                except Exception as e:
                    logging.error(f"Erro ao fazer callback para {callback_url}: {e}")

        # Limpeza
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
    except Exception as e:
        logging.error(f"Erro ao processar pedido RabbitMQ: {e}")

def rabbitmq_consumer():
    """
    Thread para consumir pedidos RabbitMQ.
    """
    def callback(ch, method, properties, body):
        try:
            data = json.loads(body)
            process_image_conversion(data)
        except Exception as e:
            logging.error(f"Erro no callback RabbitMQ: {e}")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host='rabbitmq'))
            channel = connection.channel()
            channel.queue_declare(queue='image_convert_queue', durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue='image_convert_queue', on_message_callback=callback)
            logging.info("A consumir pedidos RabbitMQ em image_convert_queue...")
            channel.start_consuming()
        except Exception as e:
            logging.error(f"Erro na ligação ao RabbitMQ: {e}")
            import time
            time.sleep(5)  # Espera antes de tentar novamente

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
                    background.paste(img, mask=img.split()[-1])
                    img = background
                else:
                    img = img.convert("RGB")
            elif output_format == "gif":
                img = img.convert("P", palette=Image.ADAPTIVE)
            format_map = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "gif": "GIF"}
            save_image_with_opencl(img, output_path, format_map.get(output_format, output_format.upper()))
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
    # Arranca o consumidor RabbitMQ numa thread separada
    threading.Thread(target=rabbitmq_consumer, daemon=True).start()
    register_service()
    cert_path = os.path.join("certs", "server.crt")
    key_path = os.path.join("certs", "server.key")
    context = (cert_path, key_path)
    logging.info("Serviço iniciado.")
    app.run(host="0.0.0.0", port=SERVICE_PORT, ssl_context=context)