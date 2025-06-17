# Conversor de Ficheiros Distribuído

Este projeto é uma solução moderna baseada em microserviços para conversão de ficheiros de texto e imagem de forma escalável, segura e eficiente.  
A arquitetura utiliza Python, Flask, Docker, Consul para service discovery, autenticação básica, HTTPS com certificados self-signed e agora também RabbitMQ para processamento assíncrono.  
Inclui suporte a processamento paralelo (multi-threading), aceleração opcional com OpenCL, e interface gráfica em CustomTkinter.

---

## 🏗️ Arquitetura

- **Cliente**: Interface gráfica em CustomTkinter para upload e download dos ficheiros convertidos. O cliente deteta automaticamente o tipo de ficheiro devolvido (ex: `.zip` para conversão de PDF/DOCX para PNG) e sugere o nome correto ao guardar.
- **Dispatcher**: Serviço Flask que recebe pedidos do cliente, descobre o microserviço adequado via Consul e encaminha o pedido. Agora suporta também pedidos assíncronos via RabbitMQ.
- **Microserviços**:
  - `service_text`: Converte ficheiros `.docx` para `.pdf`, `.pdf` para `.docx`, `.docx`/`.pdf` para `.png` (cada página como imagem, processamento paralelo com até 5 threads, resultado em `.zip`). Consome pedidos da fila RabbitMQ para processamento assíncrono.
  - `service_image`: Converte imagens entre `.jpg`, `.png` e `.gif`, com suporte a pós-processamento OpenCL. Consome pedidos da fila RabbitMQ para processamento assíncrono.
- **RabbitMQ**: Broker de mensagens para processamento assíncrono dos pedidos de conversão.
- **Consul**: Descoberta dinâmica de serviços.
- **Logs**: Todos os serviços registam logs detalhados em ficheiros dedicados.

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
- **Limpeza automática de ficheiros temporários**
- **Processamento assíncrono com RabbitMQ**:  
  - O dispatcher pode enviar pedidos para RabbitMQ (modo assíncrono, usando o parâmetro `async=true`).
  - Os microserviços consomem pedidos das filas (`text_convert_queue` e `image_convert_queue`) e processam-nos em background.
- **Volumes Docker para desenvolvimento**:  
  - O código-fonte dos serviços e dispatcher está montado como volume, permitindo alterações rápidas sem rebuild.

---

## 🏃‍♂️ Como correr o projeto

### 1. Pré-requisitos

- Python 3.8+
- Docker (para Consul, RabbitMQ e serviços)
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

### Como usar o modo assíncrono (RabbitMQ)

- Se quiseres enviar um pedido assíncrono, podes usar o endpoint `/convert` do dispatcher com o parâmetro `async=true` (por exemplo, via Postman ou curl).
- O dispatcher publica o pedido na fila RabbitMQ e devolve imediatamente um 202 Accepted.
- O serviço de destino consome o pedido da fila e processa-o em background (nesta versão de demonstração, o resultado não é devolvido automaticamente ao cliente, mas pode ser guardado ou notificado conforme necessidade futura).

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

### RabbitMQ

- O dispatcher pode enviar pedidos para RabbitMQ (modo assíncrono).
- Os microserviços consomem pedidos das filas e processam-nos em background.
- O ciclo de retry automático garante que os serviços tentam ligar ao RabbitMQ até este estar disponível.

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
- O ciclo de retry automático nos serviços garante ligação ao RabbitMQ mesmo que este demore a arrancar.

---

## 📝 O que foi implementado recentemente (para explicares na apresentação)

- **RabbitMQ**: Adicionado para suportar pedidos assíncronos. O dispatcher pode agora enviar pedidos para RabbitMQ, e os microserviços consomem e processam esses pedidos em background.
- **Volumes Docker para desenvolvimento**: O código-fonte dos serviços e dispatcher está montado como volume, permitindo alterações rápidas sem rebuild.
- **Sistema de logging uniforme**: Todos os serviços usam o mesmo sistema de logging, com logs detalhados e organizados.
- **Retry automático para RabbitMQ**: Os serviços tentam ligar ao RabbitMQ até este estar disponível, evitando falhas ao arrancar.
- **Documentação e exemplos melhorados**: O README foi atualizado para refletir todas estas alterações e facilitar a explicação do funcionamento do sistema.

---

## 📄 Licença

Este projeto é open-source e está licenciado sob a licença [MIT](https://opensource.org/licenses/MIT).  
Desenvolvido como parte de um trabalho acadêmico universitário.

