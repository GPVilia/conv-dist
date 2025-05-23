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

# --- CORREÇÃO: Configuração manual dos handlers ---
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
    Tenta converter DOCX para PDF usando o executável docx2pdf (CLI).
    """
    try:
        import shutil
        import sys
        import platform

        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)

        # Caminho para o executável docx2pdf
        if hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix):
            # Ambiente virtual
            docx2pdf_exe = os.path.join(sys.prefix, "Scripts", "docx2pdf.exe")
        else:
            # Fora de venv
            docx2pdf_exe = shutil.which("docx2pdf") or "docx2pdf"

        if not os.path.exists(docx2pdf_exe):
            raise FileNotFoundError(f"docx2pdf.exe não encontrado em {docx2pdf_exe}")

        subprocess.run([
            docx2pdf_exe, input_path, output_dir
        ], check=True)
        base = os.path.splitext(os.path.basename(input_path))[0]
        converted_pdf = os.path.join(output_dir, base + ".pdf")
        if converted_pdf != output_path:
            shutil.move(converted_pdf, output_path)
        return True
    except Exception as e:
        logging.error(f"docx2pdf CLI falhou: {e}", exc_info=True)
        return False

def save_image(img, img_path):
    img.save(img_path, 'PNG')
    return img_path

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

    try:
        # DOCX para PDF
        if input_ext == "docx" and target_format == "pdf":
            output_path = input_path.replace('.docx', '.pdf')
            logging.info(f"Convertendo DOCX para PDF: {input_path} -> {output_path}")
            if not convert_docx_to_pdf(input_path, output_path):
                return jsonify({"error": "Erro ao converter DOCX para PDF (Word e LibreOffice falharam)"}), 500
            output_files = [output_path]

        # DOCX para PNG (cada página como imagem)
        elif input_ext == "docx" and target_format == "png":
            temp_pdf = input_path.replace('.docx', '_temp.pdf')
            logging.info(f"Convertendo DOCX para PDF temporário: {input_path} -> {temp_pdf}")
            if not convert_docx_to_pdf(input_path, temp_pdf):
                return jsonify({"error": "Erro ao converter DOCX para PDF (Word e LibreOffice falharam)"}), 500
            try:
                logging.info(f"Convertendo PDF para PNG(s): {temp_pdf}")
                images = convert_from_path(temp_pdf)
                output_files = []
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = []
                    for i, img in enumerate(images):
                        img_path = input_path.replace('.docx', f'_{i+1}.png')
                        futures.append(executor.submit(save_image, img, img_path))
                    for future in concurrent.futures.as_completed(futures):
                        output_files.append(future.result())
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

        # PDF para PNG (cada página como imagem)
        elif input_ext == "pdf" and target_format == "png":
            logging.info(f"Convertendo PDF para PNG(s): {input_path}")
            images = convert_from_path(input_path)
            output_files = []
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = []
                for i, img in enumerate(images):
                    img_path = input_path.replace('.pdf', f'_{i+1}.png')
                    futures.append(executor.submit(save_image, img, img_path))
                for future in concurrent.futures.as_completed(futures):
                    output_files.append(future.result())
            # ...existing code...

        else:
            logging.warning("Conversão não suportada para este tipo de ficheiro.")
            return jsonify({"error": "Conversão não suportada para este tipo de ficheiro."}), 400

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

        # Se só há um ficheiro, envia diretamente, senão envia zip
        if len(output_files) == 1:
            logging.info(f"Envio de ficheiro convertido: {output_files[0]}")
            return send_file(output_files[0], as_attachment=True)
        else:
            zip_path = input_path + "_imgs.zip"
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for f in output_files:
                    zipf.write(f, os.path.basename(f))
            output_files.append(zip_path)
            logging.info(f"Envio de ficheiro ZIP com imagens: {zip_path}")
            return send_file(zip_path, as_attachment=True)

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
        address="127.0.0.1",
        port=SERVICE_PORT,
        tags=["text", "docx", "pdf", "png"],
        check=check
    )
    logging.info("Serviço registado no Consul.")

if __name__ == "__main__":
    register_service()
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../certs"))
    cert_path = os.path.join(base_dir, "server.crt")
    key_path = os.path.join(base_dir, "server.key")
    context = (cert_path, key_path)
    logging.info("Serviço iniciado.")
    app.run(host="127.0.0.1", port=SERVICE_PORT, ssl_context=context)