import os
from flask import Flask, request, send_file, jsonify, after_this_request
from flask_httpauth import HTTPBasicAuth
from werkzeug.utils import secure_filename
from docx2pdf import convert
from pdf2image import convert_from_path
from pdf2docx import Converter
from docx import Document
import logging
import sys
import consul
import tempfile
import zipfile
import subprocess
import concurrent.futures

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

# Configurações
USERNAME = os.getenv("BASIC_AUTH_USERNAME", "admin")
PASSWORD = os.getenv("BASIC_AUTH_PASSWORD", "admin_password")
SERVICE_NAME = "service-text"
SERVICE_PORT = 5001

# Configuração de logs
base_log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../logs"))
if not os.path.exists(base_log_dir):
    os.makedirs(base_log_dir)
log_dir = os.path.join(base_log_dir, "service-logs")
if not os.path.exists(log_dir):
    os.makedirs(log_dir)
log_file = os.path.join(log_dir, "service-text-logs.txt")

# --- Configuração manual dos handlers ---
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

def convert_docx_to_pdf(input_path, output_path):
    """
    Converte DOCX para PDF usando docx2pdf (Windows) ou LibreOffice (Linux/Docker).
    """
    import shutil
    import sys
    import platform

    output_dir = os.path.dirname(output_path)
    os.makedirs(output_dir, exist_ok=True)

    try:
        system = platform.system().lower()
        if system == "windows":
            # Tenta usar docx2pdf (Word)
            try:
                from docx2pdf import convert as docx2pdf_convert
                docx2pdf_convert(input_path, output_path)
                return True
            except Exception as e:
                logging.error(f"docx2pdf falhou no Windows: {e}", exc_info=True)
                return False
        else:
            # Usa LibreOffice em Linux/Docker
            try:
                subprocess.run([
                    "libreoffice", "--headless", "--convert-to", "pdf", input_path, "--outdir", output_dir
                ], check=True)
                base = os.path.splitext(os.path.basename(input_path))[0]
                converted_pdf = os.path.join(output_dir, base + ".pdf")
                if converted_pdf != output_path:
                    os.rename(converted_pdf, output_path)
                return True
            except Exception as e:
                logging.error(f"Erro ao converter DOCX para PDF com LibreOffice: {e}", exc_info=True)
                return False
    except Exception as e:
        logging.error(f"Erro inesperado na conversão DOCX para PDF: {e}", exc_info=True)
        return False

def opencl_invert_image(img_path):
    """
    Exemplo de processamento OpenCL: inverte as cores da imagem PNG.
    """
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

def save_image(img, img_path):
    img.save(img_path, 'PNG')
    # Pós-processamento com OpenCL (exemplo: inverter cores)
    try:
        opencl_invert_image(img_path)
    except Exception as e:
        logging.warning(f"OpenCL não disponível ou erro ao inverter imagem: {e}")
    return img_path

def process_text_conversion(data):
    """
    Função para processar pedidos vindos do RabbitMQ.
    """
    try:
        filename = data["filename"]
        file_bytes = base64.b64decode(data["file_bytes"])
        input_ext = filename.rsplit('.', 1)[-1].lower()
        target_format = data["target_format"].lower()
        input_path = os.path.join(tempfile.gettempdir(), filename)
        with open(input_path, "wb") as f:
            f.write(file_bytes)

        output_files = []
        zip_path = None

        # DOCX para PDF
        if input_ext == "docx" and target_format == "pdf":
            output_path = input_path.replace('.docx', '.pdf')
            logging.info(f"RabbitMQ: Convertendo DOCX para PDF: {input_path} -> {output_path}")
            if not convert_docx_to_pdf(input_path, output_path):
                logging.error("RabbitMQ: Erro ao converter DOCX para PDF (Word e LibreOffice falharam)")
                return
            output_files = [output_path]

        # DOCX para PNG
        elif input_ext == "docx" and target_format == "png":
            temp_pdf = input_path.replace('.docx', '_temp.pdf')
            logging.info(f"RabbitMQ: Convertendo DOCX para PDF temporário: {input_path} -> {temp_pdf}")
            if not convert_docx_to_pdf(input_path, temp_pdf):
                logging.error("RabbitMQ: Erro ao converter DOCX para PDF (Word e LibreOffice falharam)")
                return
            try:
                images = convert_from_path(temp_pdf)
                output_files = []
                def process_page(i_img):
                    i, img = i_img
                    img_path = input_path.replace('.docx', f'_page_{i+1:03d}.png')
                    save_image(img, img_path)
                    return img_path
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(process_page, (i, img)) for i, img in enumerate(images)]
                    for future in concurrent.futures.as_completed(futures):
                        output_files.append(future.result())
                output_files.sort(key=lambda x: int(x.split('_page_')[-1].split('.png')[0]))
            finally:
                if os.path.exists(temp_pdf):
                    os.remove(temp_pdf)

        # PDF para DOCX
        elif input_ext == "pdf" and target_format == "docx":
            output_path = input_path.replace('.pdf', '.docx')
            logging.info(f"RabbitMQ: Convertendo PDF para DOCX: {input_path} -> {output_path}")
            cv = Converter(input_path)
            cv.convert(output_path, start=0, end=None)
            cv.close()
            output_files = [output_path]

        # PDF para PNG
        elif input_ext == "pdf" and target_format == "png":
            images = convert_from_path(input_path)
            output_files = []
            def process_page(i_img):
                i, img = i_img
                img_path = input_path.replace('.pdf', f'_page_{i+1:03d}.png')
                save_image(img, img_path)
                return img_path
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(process_page, (i, img)) for i, img in enumerate(images)]
                for future in concurrent.futures.as_completed(futures):
                    output_files.append(future.result())
            output_files.sort(key=lambda x: int(x.split('_page_')[-1].split('.png')[0]))

        # Para PNG, cria SEMPRE um ZIP com todas as páginas
        if target_format == "png":
            zip_path = input_path + "_pages.zip"
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for f in output_files:
                    zipf.write(f, os.path.basename(f))
            logging.info(f"RabbitMQ: ZIP criado com {len(output_files)} imagens: {zip_path}")
            # Opcional: guardar resultado numa pasta partilhada, enviar notificação, etc.
            # Limpeza
            for f in output_files:
                if os.path.exists(f):
                    os.remove(f)
            if os.path.exists(zip_path):
                os.remove(zip_path)
        elif len(output_files) == 1:
            # Limpeza
            for f in output_files:
                if os.path.exists(f):
                    os.remove(f)
        if os.path.exists(input_path):
            os.remove(input_path)
    except Exception as e:
        logging.error(f"Erro ao processar pedido RabbitMQ: {e}")

def rabbitmq_consumer():
    """
    Thread para consumir pedidos RabbitMQ.
    """
    def callback(ch, method, properties, body):
        try:
            data = json.loads(body)
            process_text_conversion(data)
        except Exception as e:
            logging.error(f"Erro no callback RabbitMQ: {e}")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    while True:
        try:
            connection = pika.BlockingConnection(pika.ConnectionParameters(host='rabbitmq'))
            channel = connection.channel()
            channel.queue_declare(queue='text_convert_queue', durable=True)
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue='text_convert_queue', on_message_callback=callback)
            logging.info("A consumir pedidos RabbitMQ em text_convert_queue...")
            channel.start_consuming()
        except Exception as e:
            logging.error(f"Erro na ligação ao RabbitMQ: {e}")
            import time
            time.sleep(5)

@app.route("/convert", methods=["POST"])
@auth.login_required
def convert_text():
    logging.info("Pedido recebido para conversão de texto.")
    if 'file' not in request.files:
        logging.warning("Nenhum ficheiro foi enviado no pedido.")
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        logging.warning("Nenhum ficheiro foi selecionado.")
        return jsonify({"error": "No selected file"}), 400

    filename = secure_filename(file.filename)
    input_ext = filename.rsplit('.', 1)[-1].lower()
    input_path = os.path.join(tempfile.gettempdir(), filename)
    file.save(input_path)
    logging.info(f"Ficheiro recebido: {filename} ({input_ext}) guardado em {input_path}")

    target_format = request.form.get("target_format", "").lower()
    logging.info(f"Formato de destino pedido: {target_format}")
    if target_format not in ["pdf", "docx", "png"]:
        logging.warning("Formato de destino inválido.")
        return jsonify({"error": "Invalid format. Supported formats: pdf, docx, png"}), 400

    output_files = []
    zip_path = None

    try:
        # DOCX para PDF
        if input_ext == "docx" and target_format == "pdf":
            output_path = input_path.replace('.docx', '.pdf')
            logging.info(f"Convertendo DOCX para PDF: {input_path} -> {output_path}")
            if not convert_docx_to_pdf(input_path, output_path):
                return jsonify({"error": "Erro ao converter DOCX para PDF (Word e LibreOffice falharam)"}), 500
            output_files = [output_path]

        # DOCX para PNG (cada página como imagem, threads limitadas a 5)
        elif input_ext == "docx" and target_format == "png":
            temp_pdf = input_path.replace('.docx', '_temp.pdf')
            logging.info(f"Convertendo DOCX para PDF temporário: {input_path} -> {temp_pdf}")
            if not convert_docx_to_pdf(input_path, temp_pdf):
                return jsonify({"error": "Erro ao converter DOCX para PDF (Word e LibreOffice falharam)"}), 500
            try:
                logging.info(f"Convertendo PDF para PNG(s): {temp_pdf}")
                images = convert_from_path(temp_pdf)
                logging.info(f"Total de páginas a processar: {len(images)}")
                output_files = []
                
                def process_page(i_img):
                    i, img = i_img
                    img_path = input_path.replace('.docx', f'_page_{i+1:03d}.png')
                    save_image(img, img_path)
                    logging.info(f"Página {i+1} processada: {img_path}")
                    return img_path
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(process_page, (i, img)) for i, img in enumerate(images)]
                    for future in concurrent.futures.as_completed(futures):
                        output_files.append(future.result())
                
                # Ordena por número da página
                output_files.sort(key=lambda x: int(x.split('_page_')[-1].split('.png')[0]))
                logging.info(f"Todas as {len(output_files)} páginas processadas com sucesso")
                
            except Exception as e:
                logging.error(f"Erro ao converter PDF para PNG: {e}", exc_info=True)
                return jsonify({"error": f"Erro ao converter PDF para PNG: {e}"}), 500
            finally:
                if os.path.exists(temp_pdf):
                    os.remove(temp_pdf)
                    logging.info(f"PDF temporário removido: {temp_pdf}")

        # PDF para DOCX
        elif input_ext == "pdf" and target_format == "docx":
            output_path = input_path.replace('.pdf', '.docx')
            logging.info(f"Convertendo PDF para DOCX: {input_path} -> {output_path}")
            cv = Converter(input_path)
            cv.convert(output_path, start=0, end=None)
            cv.close()
            output_files = [output_path]

        # PDF para PNG (cada página como imagem, threads limitadas a 5)
        elif input_ext == "pdf" and target_format == "png":
            logging.info(f"Convertendo PDF para PNG(s): {input_path}")
            images = convert_from_path(input_path)
            logging.info(f"Total de páginas a processar: {len(images)}")
            output_files = []
            
            def process_page(i_img):
                i, img = i_img
                img_path = input_path.replace('.pdf', f'_page_{i+1:03d}.png')
                save_image(img, img_path)
                logging.info(f"Página {i+1} processada: {img_path}")
                return img_path
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(process_page, (i, img)) for i, img in enumerate(images)]
                for future in concurrent.futures.as_completed(futures):
                    output_files.append(future.result())
            
            # Ordena por número da página
            output_files.sort(key=lambda x: int(x.split('_page_')[-1].split('.png')[0]))
            logging.info(f"Todas as {len(output_files)} páginas processadas com sucesso")

        else:
            logging.warning("Conversão não suportada para este tipo de ficheiro.")
            return jsonify({"error": "Conversão não suportada para este tipo de ficheiro."}), 400

        # Para PNG, cria SEMPRE um ZIP com todas as páginas
        if target_format == "png":
            zip_path = input_path + "_pages.zip"
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for f in output_files:
                    zipf.write(f, os.path.basename(f))
            logging.info(f"ZIP criado com {len(output_files)} imagens: {zip_path}")
            
            # Define a função de limpeza
            @after_this_request
            def cleanup(response):
                try:
                    if os.path.exists(input_path):
                        os.remove(input_path)
                        logging.info(f"Removido ficheiro temporário: {input_path}")
                    for f in output_files:
                        if os.path.exists(f):
                            os.remove(f)
                            logging.info(f"Removido ficheiro PNG temporário: {f}")
                    if zip_path and os.path.exists(zip_path):
                        os.remove(zip_path)
                        logging.info(f"Removido ficheiro ZIP temporário: {zip_path}")
                except Exception as e:
                    logging.error(f"Erro ao remover ficheiros temporários: {e}")
                return response
            
            return send_file(zip_path, as_attachment=True, download_name="pages.zip")
        
        # Para outros formatos (PDF, DOCX)
        elif len(output_files) == 1:
            @after_this_request
            def cleanup(response):
                try:
                    if os.path.exists(input_path):
                        os.remove(input_path)
                        logging.info(f"Removido ficheiro temporário: {input_path}")
                    for f in output_files:
                        if os.path.exists(f):
                            os.remove(f)
                            logging.info(f"Removido ficheiro temporário: {f}")
                except Exception as e:
                    logging.error(f"Erro ao remover ficheiros temporários: {e}")
                return response
            
            logging.info(f"Envio de ficheiro convertido: {output_files[0]}")
            return send_file(output_files[0], as_attachment=True)

    except Exception as e:
        logging.error(f"Erro ao converter {filename}: {e}", exc_info=True)
        # Limpeza mesmo em caso de erro
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
                logging.info(f"Removido ficheiro temporário após erro: {input_path}")
            for f in output_files:
                if os.path.exists(f):
                    os.remove(f)
                    logging.info(f"Removido ficheiro temporário após erro: {f}")
            if zip_path and os.path.exists(zip_path):
                os.remove(zip_path)
                logging.info(f"Removido ficheiro ZIP temporário após erro: {zip_path}")
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
        address="service-text",
        port=SERVICE_PORT,
        tags=["text", "docx", "pdf", "png"],
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