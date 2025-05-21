# Conversor de Ficheiros Distribuído

Este projeto é uma solução de microserviços para conversão de ficheiros pesados (ex: `.docx` → `.pdf`, `.png` → `.jpg`) de forma escalável, segura e eficiente.  
A arquitetura utiliza Python, Flask, Docker, Consul para service discovery, autenticação básica e HTTPS com certificados self-signed.

---

## 🏗️ Arquitetura

- **Cliente**: Interface gráfica em Tkinter para upload e download dos ficheiros convertidos.
- **Dispatcher**: Serviço Flask que recebe pedidos do cliente, descobre o microserviço adequado via Consul e encaminha o pedido.
- **Microserviços**:
  - `service_text`: Converte ficheiros `.docx` para `.pdf` e vice-versa.
  - `service_image`: Converte imagens entre `.jpg` e `.png`.
- **Consul**: Descoberta dinâmica de serviços.
- **Logs**: Todos os serviços registam logs detalhadas em ficheiros dedicados.

---

## 🚀 Como correr o projeto

### 1. Pré-requisitos

- Python 3.8+
- Docker (para Consul)
- Pipenv ou venv (recomendado)
- [Consul](https://www.consul.io/) (pode ser via Docker)

### 2. Instalar dependências

```bash
pip install -r requirements.txt
```

### 3. Gerar certificados self-signed

```bash
mkdir certs
openssl req -x509 -newkey rsa:4096 -keyout certs/server.key -out certs/server.crt -days 365 -nodes -subj "/CN=localhost"
```

### 4. Correr o Consul

```bash
docker run -d --name consul-server -p 8500:8500 consul:1.15.4 agent -dev -client=0.0.0.0
```

### 5. Correr os serviços

Em terminais separados, corre:

```bash
python services/service_text/service.py
python services/service_image/service.py
python dispatcher/dispatcher.py
python client/app.py
```

---

## 🖥️ Como usar

1. Abre o cliente (`client/app.py`).
2. Seleciona o ficheiro e o formato de destino.
3. Clica em "Converter".
4. O ficheiro convertido será guardado onde escolheres.

---

## 🔒 Segurança

- Toda a comunicação é feita via HTTPS (certificados self-signed).
- Autenticação básica (username e password) em todos os endpoints.

---

## 📂 Estrutura de Pastas

```
conv-dist/
├── client/
├── dispatcher/
├── services/
│   ├── service_text/
│   └── service_image/
├── certs/
├── logs/
│   ├── service-logs/
│   ├── client-logs.txt
│   └── dispatcher-logs.txt
├── docker-compose.yml (opcional)
├── .env
└── README.md
```

---

## 📝 Notas

- Os logs detalhados de cada serviço estão na pasta `logs/`.
- Para correr em produção, recomenda-se usar um WSGI server (ex: gunicorn) e certificados válidos.
- O projeto pode ser facilmente expandido para outros tipos de ficheiros/serviços.

---

## 📄 Licença

Este projeto é open-source e está licenciado sob a licença [MIT](https://opensource.org/licenses/MIT).  
Foi desenvolvido como parte de um trabalho acadêmico para a faculdade.

