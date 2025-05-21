import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import requests
import os
import logging

DISPATCHER_URL = "https://127.0.0.1:5000/convert"
USERNAME = os.getenv("BASIC_AUTH_USERNAME", "admin")
PASSWORD = os.getenv("BASIC_AUTH_PASSWORD", "admin_password")

FORMATS = ["pdf", "docx", "jpg", "png"]

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
        logging.FileHandler(log_file),  # Logs para o ficheiro
        logging.StreamHandler()        # Logs para o terminal
    ]
)

def convert_file():
    file_path = file_var.get()
    target_format = format_var.get()
    if not file_path or not target_format:
        messagebox.showerror("Erro", "Seleciona um ficheiro e formato de destino.")
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
                timeout=60
            )
        if resp.status_code == 200:
            save_path = filedialog.asksaveasfilename(defaultextension=f".{target_format}")
            if save_path:
                with open(save_path, "wb") as out:
                    out.write(resp.content)
                messagebox.showinfo("Sucesso", f"Ficheiro convertido guardado em:\n{save_path}")
        else:
            messagebox.showerror("Erro", f"Erro na conversão: {resp.text}")
    except Exception as e:
        messagebox.showerror("Erro", str(e))

def browse_file():
    path = filedialog.askopenfilename()
    if path:
        file_var.set(path)

root = tk.Tk()
root.title("Conversor de Ficheiros")

file_var = tk.StringVar()
format_var = tk.StringVar(value=FORMATS[0])

frame = ttk.Frame(root, padding=20)
frame.pack()

ttk.Label(frame, text="Ficheiro:").grid(row=0, column=0, sticky="e")
ttk.Entry(frame, textvariable=file_var, width=40).grid(row=0, column=1)
ttk.Button(frame, text="Procurar", command=browse_file).grid(row=0, column=2)

ttk.Label(frame, text="Formato destino:").grid(row=1, column=0, sticky="e")
ttk.Combobox(frame, textvariable=format_var, values=FORMATS, state="readonly").grid(row=1, column=1)

ttk.Button(frame, text="Converter", command=convert_file).grid(row=2, column=1, pady=10)

root.mainloop()