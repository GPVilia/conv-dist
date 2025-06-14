# Conversor de Ficheiros Distribuído

Este projeto é uma solução moderna baseada em microserviços para conversão de ficheiros de texto e imagem de forma escalável, segura e eficiente.  
A arquitetura utiliza Python, Flask, Docker, Consul para service discovery, autenticação básica e HTTPS com certificados self-signed.  
Inclui suporte a processamento paralelo (multi-threading), aceleração opcional com OpenCL, e interface gráfica em CustomTkinter.

---

## 🏗️ Arquitetura

- **Cliente**: Interface gráfica em CustomTkinter para upload e download dos ficheiros convertidos. O cliente deteta automaticamente o tipo de ficheiro devolvido (ex: `.zip` para conversão de PDF/DOCX para PNG) e sugere o nome correto ao guardar.
- **Dispatcher**: Serviço Flask que recebe pedidos do cliente, descobre o microserviço adequado via Consul e encaminha o pedido. Suporta pós-processamento opcional com OpenCL.
- **Microserviços**:
  - `service_text`: Converte ficheiros `.docx` para `.pdf`, `.pdf` para `.docx`, `.docx`/`.pdf` para `.png` (cada página como imagem, processamento paralelo com até 5 threads, resultado em `.zip`).
  - `service_image`: Converte imagens entre `.jpg`, `.png` e `.gif`, com suporte a pós-processamento OpenCL.
- **Consul**: Descoberta dinâmica de serviços.
- **Logs**: Todos os serviços registam logs detalhadas em ficheiros dedicados.

---

## 🚀 Funcionalidades implementadas

- **Conversão de ficheiros DOCX ↔ PDF, PDF ↔ DOCX, PDF/DOCX → PNG (multi-página, multi-thread, ZIP)**
- **Conversão de imagens entre JPG, PNG e GIF**
- **Processamento paralelo (máx. 5 threads) para conversão de páginas em PNG**
- **Resultado de conversão PDF/DOCX → PNG é sempre um ficheiro ZIP com todas as páginas numeradas**
- **Aceleração opcional com OpenCL (se disponível)**
- **Deteção automática do sistema operativo para escolher entre Word/docx2pdf (Windows) ou LibreOffice (Linux/Docker)**
- **Interface gráfica moderna (CustomTkinter)**
- **Cliente deteta extensão correta do ficheiro devolvido e sugere nome adequado ao guardar**
- **Comunicação segura via HTTPS (certificados self-signed)**
- **Autenticação básica em todos os endpoints**
- **Logs detalhados por serviço**
- **Volumes Docker para desenvolvimento rápido sem rebuilds**
- **Limpeza automática de ficheiros temporários**

---

## 🏃‍♂️ Como correr o projeto

### 1. Pré-requisitos

- Python 3.8+
- Docker (para Consul e serviços)
- Pipenv ou venv (recomendado)
- [Consul](https://www.consul.io/) (pode ser via Docker)
- [Poppler](https://github.com/oschwartz10612/poppler-windows/releases/) (para PDF→PNG)
- (Opcional) LibreOffice (para DOCX→PDF em Linux/Docker)

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Gerar certificados self-signed

```bash
mkdir certs
openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt -days 365 -nodes -subj "/CN=localhost"
```

### 4. Correr tudo com Docker Compose

```bash
docker-compose up --build
```

> **Nota:** O código dos serviços e dispatcher está montado como volume, pelo que qualquer alteração ao código é refletida imediatamente sem rebuild.

### 5. Correr o cliente

```bash
python client/app.py
```

---

## 🖥️ Como usar

1. Abre o cliente (`client/app.py`).
2. Seleciona o ficheiro e o formato de destino.
3. Clica em "Converter".
4. O ficheiro convertido será guardado onde escolheres, com a extensão correta (ex: `.zip` para PDF/DOCX→PNG).

---

## ⚙️ Detalhes técnicos e requisitos

### Conversão PDF/DOCX → PNG

- Cada página é processada em paralelo (máx. 5 threads).
- Todas as imagens são guardadas como PNG numerados (`page_001.png`, `page_002.png`, ...).
- O resultado é sempre um ficheiro ZIP com todas as imagens.
- O cliente deteta e sugere automaticamente a extensão `.zip` ao guardar.

### Conversão DOCX → PDF

- Em Windows: usa Microsoft Word via docx2pdf.
- Em Linux/Docker: usa LibreOffice em modo headless.

### OpenCL

- Se disponível, pode ser usado para pós-processamento de imagens (ex: inversão de cores).
- O código deteta automaticamente se OpenCL está disponível e usa-o apenas se possível.

### Volumes Docker

- O código-fonte dos serviços e dispatcher está montado como volume (`./services/service_text:/app`, etc.), permitindo desenvolvimento rápido sem rebuilds.

---

## 📂 Estrutura de Pastas

```
conv-dist/
├── client/
│   └── app.py
├── dispatcher/
│   └── dispatcher.py
├── services/
│   ├── service_text/
│   │   └── service.py
│   └── service_image/
│       └── service.py
├── certs/
├── logs/
│   ├── service-logs/
│   ├── client-logs.txt
│   └── dispatcher-logs.txt
├── docker-compose.yml
├── requirements.txt
├── .env
└── README.md
```

---

## ⚠️ Notas importantes

- Para conversão de **PDF/DOCX para PNG** é necessário instalar o [Poppler](https://github.com/oschwartz10612/poppler-windows/releases/) e garantir que o executável está no `PATH`.
- Para conversão de **DOCX para PDF** em Linux/Docker, é necessário instalar o LibreOffice.
- O cliente deteta automaticamente o tipo de ficheiro devolvido e sugere a extensão correta ao guardar.
- Os logs detalhados de cada serviço estão na pasta `logs/`.
- Para produção, recomenda-se usar certificados válidos e um WSGI server (ex: gunicorn).

---

## 📄 Licença

Este projeto é open-source e está licenciado sob a licença [MIT](https://opensource.org/licenses/MIT).  
Desenvolvido como parte de um trabalho acadêmico para a faculdade.

