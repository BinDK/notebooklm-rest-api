# 📘 notebooklm-rest-api

[![Discord chat](https://img.shields.io/discord/359930650330923008?logo=discord)](https://discord.gg/SjHtURQKBc?utm_source=catswords)

> A REST API wrapper for Google NotebookLM powered by `notebooklm-py`

`notebooklm-rest-api` exposes the functionality of
[`teng-lin/notebooklm-py`](https://github.com/teng-lin/notebooklm-py)
as a clean, production-ready REST API service.

For maintainers and AI agents, start with [`AGENTS.md`](AGENTS.md); it maps the code, authentication rules, routes, and current integration limits. The running service exposes its exact schema at `/openapi.json` and interactive API docs at `/docs`.

It allows you to manage Notebooks, add sources, perform Q&A, generate artifacts, and download outputs via HTTP.

---

## 🚀 Features

### 📂 Notebook Management

* Create notebook
* List notebooks
* Get notebook details
* Rename notebook
* Delete notebook
* Get summary
* Get description

### 📄 Source Management

* Add URL source
* Add YouTube source
* Add raw text
* Upload file
* Get full text
* Get source guide
* Delete source

### 💬 Chat API

* Ask questions based on notebook context

### 🎨 Artifact Generation

* Audio
* Video
* Report
* Quiz
* Flashcards
* Slide deck
* Infographic
* Data table
* Mind map
* Task polling support
* File download support

### 🔐 API Key Protection

---

## 🧱 Architecture

```
Client (REST)
    ↓
FastAPI
    ↓
notebooklm-py
    ↓
NotebookLM (Web API)
```

---

## 📦 Requirements

* Python 3.10+
* NotebookLM account
* First-time login using `notebooklm login`

---

## ⚙️ Installation

### 1️⃣ Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

### 2️⃣ Install dependencies

```bash
pip install -r requirements.txt
```

### 3️⃣ Authenticate (one-time setup)

```bash
notebooklm login
```

With `notebooklm-py` 0.8.x, authentication is stored in the default profile at:

```
~/.notebooklm/profiles/default/storage_state.json
```

For the Docker Compose volume, place it at
`/data/notebooklm/profiles/default/storage_state.json`.

You can override it with:

```bash
export NOTEBOOKLM_STORAGE_PATH=/path/to/storage_state.json
```

---

## 🖥️ Setup and renewal portal

The `/setup` page uses HTTP Basic Auth configured with `NOTEBOOKLM_SETUP_USERNAME` and `NOTEBOOKLM_SETUP_PASSWORD`. Sign in to NotebookLM in your regular browser, export Google/NotebookLM cookies as JSON with Cookie Editor, then upload the file or paste its JSON into the textarea. The portal converts it to Playwright storage state and verifies it before replacing the active session. No custom browser extension is required. **Renew session now** refreshes an existing session; **Check connection** confirms it works. The session file is stored in the persistent auth volume.

After the session is verified, open `/setup/sources` to add several URL/YouTube sources to a selected notebook, or create a notebook and add them together. Adds run sequentially. The portal reads the account's source limit when available and creates a continuation notebook before the next add when the selected one is full. It also reacts to a source-limit error if the limit lookup is unavailable. **Clear inputs** only empties the current form; the separately labeled delete-all action removes sources from the selected notebook after browser confirmation.

Configure `NOTEBOOKLM_REST_API_KEY`, `NOTEBOOKLM_SETUP_USERNAME`, and `NOTEBOOKLM_SETUP_PASSWORD` in the Dokploy environment. Attach the HTTPS domain to the container port `8000`. For local Compose, set `PORT` to the desired host port (defaults to `8001`); it binds to localhost only. Keep the auth volume persistent and do not commit either the API key or Google auth file.

## ▶️ Run Server

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Swagger UI:

```
http://localhost:8000/docs
```

---

## 🔐 API Key Protection

The `/v1` routes require an API key. They return `503` if it is not configured.
Set the same key in the server environment and send it with every API request:

```bash
export NOTEBOOKLM_REST_API_KEY=your-secret-key
```

Send header:

```
X-API-Key: your-secret-key
```

---

## 📚 API Examples

### List Notebooks

```bash
GET /v1/notebooks
```

---

### Create Notebook

```bash
POST /v1/notebooks
{
  "title": "My Research"
}
```

---

### Add URL Source

```bash
POST /v1/notebooks/{notebook_id}/sources/url
{
  "url": "https://example.com",
  "wait": true
}
```

---

### Ask Question

```bash
POST /v1/notebooks/{notebook_id}/chat/ask
{
  "question": "Summarize the key insights"
}
```

---

### Generate Quiz

```bash
POST /v1/notebooks/{notebook_id}/artifacts/generate
{
  "type": "quiz",
  "options": {}
}
```

---

### Poll Task

```bash
GET /v1/notebooks/{notebook_id}/artifacts/tasks/{task_id}
```

---

### Download Artifact

```bash
GET /v1/notebooks/{notebook_id}/artifacts/download?type=quiz&output_format=json
```

---

## 🌍 Environment Variables

| Variable                | Description                |
| ----------------------- | -------------------------- |
| NOTEBOOKLM_STORAGE_PATH | Explicit path to storage_state.json |
| NOTEBOOKLM_AUTH_JSON    | Inject auth JSON directly  |
| NOTEBOOKLM_HOME         | Base notebooklm directory  |
| NOTEBOOKLM_REST_API_KEY | REST API protection key    |

---

## 🐳 Docker Example

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## ⚠️ Disclaimer

This project is **not an official Google NotebookLM API**.

It relies on `notebooklm-py`, which automates NotebookLM web interactions.
Behavior may change if Google updates internal APIs.

Please review applicable terms before production use.

---

## 📜 License

MIT License

---

## 🤝 Contributing

Pull requests and issues are welcome.
