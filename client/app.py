import customtkinter as ctk
from tkinter import filedialog, messagebox
import requests
import os
import logging
import threading

DISPATCHER_URL = "https://127.0.0.1:5000/convert"
USERNAME = os.getenv("BASIC_AUTH_USERNAME", "admin")
PASSWORD = os.getenv("BASIC_AUTH_PASSWORD", "admin_password")

# Mapas de conversão possíveis
CONVERSION_MAP = {
    "docx": ["pdf", "png"],
    "pdf": ["docx", "png"],
    "jpg": ["png", "gif"],
    "png": ["jpg", "gif"],
    "gif": ["jpg", "png"]
}

# Configuração de logs
base_log_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../logs"))
if not os.path.exists(base_log_dir):
    os.makedirs(base_log_dir)
log_file = os.path.join(base_log_dir, "client-logs.txt")
if not os.path.exists(os.path.dirname(log_file)):
    os.makedirs(os.path.dirname(log_file))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

def get_file_extension(path):
    return os.path.splitext(path)[-1][1:].lower()

def update_formats(*args):
    file_path = file_var.get()
    ext = get_file_extension(file_path)
    valid_formats = CONVERSION_MAP.get(ext, [])
    if valid_formats:
        segmented_btn.configure(values=[f".{fmt}" for fmt in valid_formats])
        format_var.set(f".{valid_formats[0]}")
        segmented_btn.configure(state="normal")
    else:
        segmented_btn.configure(values=[""])
        format_var.set("")
        segmented_btn.configure(state="disabled")
    logging.info(f"Ficheiro selecionado: {file_path} | Extensão: {ext} | Opções: {valid_formats}")

def convert_file_thread():
    file_path = file_var.get()
    target_format = format_var.get().replace(".", "")
    if not file_path or not target_format:
        messagebox.showerror("Erro", "Seleciona um ficheiro e formato de destino.")
        hide_progress()
        return

    try:
        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f)}
            data = {"target_format": target_format}
            resp = requests.post(
                DISPATCHER_URL,
                files=files,
                data=data,
                auth=(USERNAME, PASSWORD),
                verify=False,
                timeout=120
            )
        logging.info(f"Resposta recebida do servidor: status_code={resp.status_code}")
        if resp.status_code == 200:
            save_path = filedialog.asksaveasfilename(defaultextension=f".{target_format}")
            if save_path:
                with open(save_path, "wb") as out:
                    out.write(resp.content)
                messagebox.showinfo("Sucesso", f"Ficheiro convertido guardado em:\n{save_path}")
        else:
            messagebox.showerror("Erro", f"Erro na conversão: {resp.text}")
    except Exception as e:
        logging.error(f"Erro na conversão: {e}")
        messagebox.showerror("Erro", str(e))
    finally:
        hide_progress()

def start_conversion():
    convert_btn.configure(state="disabled")
    show_progress()
    threading.Thread(target=convert_file_thread, daemon=True).start()

def browse_file():
    path = filedialog.askopenfilename(
        filetypes=[
            ("Todos os ficheiros suportados", "*.docx *.pdf *.jpg *.png *.gif"),
            ("Documentos Word", "*.docx"),
            ("PDF", "*.pdf"),
            ("Imagens JPG", "*.jpg"),
            ("Imagens PNG", "*.png"),
            ("Imagens GIF", "*.gif"),
            ("Todos os ficheiros", "*.*")
        ]
    )
    if path:
        file_var.set(path)
        update_formats()

def show_progress():
    progress_bar.grid(row=6, column=0, columnspan=2, pady=(2, 0), sticky="ew")
    progress_label.grid(row=7, column=0, columnspan=2, pady=(2, 10))
    progress_bar.start()
    convert_btn.configure(state="disabled")

def hide_progress():
    progress_bar.stop()
    progress_bar.grid_remove()
    progress_label.grid_remove()
    convert_btn.configure(state="normal")

# --- Interface gráfica minimalista ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")  # Escolha um tema mais suave/minimalista

root = ctk.CTk()
root.title("Conversor de Ficheiros")
root.geometry("420x280")
root.resizable(False, False)

main_frame = ctk.CTkFrame(root, fg_color="#242424", corner_radius=12)
main_frame.pack(fill="both", expand=True, padx=18, pady=18)

file_var = ctk.StringVar()
format_var = ctk.StringVar()

# Ficheiro
file_label = ctk.CTkLabel(main_frame, text="Selecionar ficheiro", font=("Segoe UI", 15, "bold"), text_color="#FFFFFF")
file_label.grid(row=0, column=0, sticky="w", pady=(0, 2), padx=(2,0), columnspan=2)

file_entry = ctk.CTkEntry(main_frame, textvariable=file_var, width=220, font=("Segoe UI", 13), border_width=1, corner_radius=8)
file_entry.grid(row=1, column=0, padx=(0, 8), pady=(0, 10), sticky="ew")

browse_btn = ctk.CTkButton(
    main_frame,
    text="Procurar",
    command=browse_file,
    width=80,
    fg_color="#1F6AA5",
    hover_color="#033E6D",
    text_color="white",
    font=("Segoe UI", 13),
    corner_radius=8
)
browse_btn.grid(row=1, column=1, padx=(0, 0), pady=(0, 10))

# Formato destino
format_label = ctk.CTkLabel(main_frame, text="Formato de destino", font=("Segoe UI", 15, "bold"), text_color="#FFFFFF")
format_label.grid(row=2, column=0, sticky="w", pady=(0, 2), padx=(2,0), columnspan=2)

segmented_btn = ctk.CTkSegmentedButton(
    main_frame,
    variable=format_var,
    values=[],
    font=("Segoe UI", 13),
    width=180,
    state="disabled",
    corner_radius=8,
    fg_color="#52575A",
    selected_color="#1F6AA5",
    selected_hover_color="#033E6D",
    unselected_color="#52575A",
    unselected_hover_color="#343638"
)
segmented_btn.grid(row=3, column=0, columnspan=2, padx=(0,0), pady=(0, 10), sticky="ew")

# Botão converter
convert_btn = ctk.CTkButton(
    main_frame,
    text="Converter",
    command=start_conversion,
    width=180,
    font=("Segoe UI", 14, "bold"),
    fg_color="#1F6AA5",
    hover_color="#033E6D",
    text_color="white",
    corner_radius=12
)
convert_btn.grid(row=5, column=0, columnspan=2, pady=12, sticky="ew")

# Barra de progresso (agora em baixo do botão)
progress_bar = ctk.CTkProgressBar(main_frame, width=320, height=8, mode="indeterminate", progress_color="#1F6AA5", fg_color="#52575A", corner_radius=4)
progress_bar.grid(row=6, column=0, columnspan=2, pady=(2, 0), sticky="ew")
progress_bar.grid_remove()
progress_label = ctk.CTkLabel(main_frame, text="A converter ficheiro...", font=("Segoe UI", 11), text_color="#666")
progress_label.grid(row=7, column=0, columnspan=2, pady=(2, 10))
progress_label.grid_remove()

# Centralizar e espaçar
main_frame.grid_columnconfigure(0, weight=1)
main_frame.grid_columnconfigure(1, weight=0)

root.mainloop()
