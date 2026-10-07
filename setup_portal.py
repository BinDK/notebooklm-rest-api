from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from notebooklm import NotebookLMClient
from pydantic import BaseModel


MAX_UPLOAD_BYTES = 2 * 1024 * 1024
SETUP_USERNAME = os.environ.get('NOTEBOOKLM_SETUP_USERNAME', '')
SETUP_PASSWORD = os.environ.get('NOTEBOOKLM_SETUP_PASSWORD', '')

_process_lock = threading.Lock()
_auth_process: subprocess.Popen | None = None
_auth_action: str | None = None
_auth_started_at: float | None = None
_auth_log_handle = None


SETUP_PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NotebookLM session setup</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, sans-serif; }
    body { max-width: 920px; margin: 36px auto; padding: 0 20px; color: #172033; }
    h1 { margin-bottom: 8px; }
    .muted { color: #536174; }
    .card { border: 1px solid #d8dee8; border-radius: 12px; padding: 18px; margin: 18px 0; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0; }
    button, .button { border: 0; border-radius: 8px; padding: 10px 15px; background: #175cd3; color: white; font: inherit; cursor: pointer; text-decoration: none; }
    button.secondary { background: #e8eef8; color: #172033; }
    button:disabled { opacity: .55; cursor: wait; }
    #status { font-weight: 600; }
    #message { min-height: 24px; white-space: pre-wrap; }
    input[type=file] { display: block; margin: 10px 0; max-width: 100%; }
    textarea { box-sizing: border-box; display: block; width: 100%; min-height: 150px; margin: 10px 0; padding: 12px; border: 1px solid #cbd5e1; border-radius: 8px; font: 14px ui-monospace, monospace; }
    code { overflow-wrap: anywhere; }
    ol { padding-left: 22px; }
    li { margin: 8px 0; }
  </style>
</head>
<body>
  <h1>NotebookLM access</h1>
  <p class="muted">Create or renew the NotebookLM session used by this service.</p>
  <section class="card">
    <h2>Session status</h2>
    <div id="status">Checking…</div>
    <p id="message" role="status"></p>
    <div class="actions">
      <button class="secondary" id="renew">Renew session now</button>
      <button class="secondary" id="check">Check connection</button>
    </div>
  </section>
  <section class="card">
    <h2>Set up a new session</h2>
    <ol>
      <li>In your signed-in browser, use Cookie Editor to export cookies for Google and NotebookLM.</li>
      <li>Upload the Cookie Editor JSON below. The service converts and verifies it before saving.</li>
    </ol>
    <p><a href="/setup/sources">Open source manager</a> after your session is ready.</p>
    <form id="upload-form">
      <input type="file" id="storage-file" name="file" accept="application/json,.json" required>
      <button type="submit">Upload and verify</button>
    </form>
    <p class="muted">Or paste the exported JSON here:</p>
    <form id="paste-form">
      <textarea id="storage-json" aria-label="Cookie Editor JSON" placeholder="Paste your Cookie Editor JSON"></textarea>
      <button type="submit">Paste and verify</button>
    </form>
  </section>
<script>
const statusBox = document.getElementById('status');
const messageBox = document.getElementById('message');
const buttons = [...document.querySelectorAll('button')];
async function call(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', ...options});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || 'Request failed (' + response.status + ')');
  return body;
}
async function refreshStatus() {
  try {
    const result = await call('/setup/api/status');
    statusBox.textContent = result.auth_file
      ? 'Session file present' + (result.modified ? ' · updated ' + result.modified : '')
      : 'No session file yet';
    if (result.operation) statusBox.textContent += ' · ' + result.operation;
  } catch (error) {
    statusBox.textContent = 'Status unavailable';
    messageBox.textContent = error.message;
  }
}
async function start(path, label) {
  buttons.forEach(button => button.disabled = true);
  messageBox.textContent = label + '…';
  try {
    const result = await call(path, {method: 'POST'});
    messageBox.textContent = result.message;
  } catch (error) {
    messageBox.textContent = error.message;
  } finally {
    buttons.forEach(button => button.disabled = false);
    await refreshStatus();
  }
}
document.getElementById('renew').addEventListener('click', () => start('/setup/api/renew', 'Refreshing NotebookLM session'));
document.getElementById('check').addEventListener('click', async () => {
  messageBox.textContent = 'Checking NotebookLM…';
  try {
    const result = await call('/setup/api/check', {method: 'POST'});
    messageBox.textContent = 'Connection works. ' + result.notebook_count + ' notebooks available.';
  } catch (error) {
    messageBox.textContent = error.message;
  }
  await refreshStatus();
});
document.getElementById('upload-form').addEventListener('submit', async event => {
  event.preventDefault();
  const file = document.getElementById('storage-file').files[0];
  if (!file) return;
  const form = new FormData(); form.append('file', file);
  buttons.forEach(button => button.disabled = true);
  messageBox.textContent = 'Uploading and verifying session…';
  try {
    const result = await call('/setup/api/upload', {method: 'POST', body: form});
    messageBox.textContent = 'Session verified. ' + result.notebook_count + ' notebooks available.';
    document.getElementById('upload-form').reset();
  } catch (error) {
    messageBox.textContent = error.message;
  } finally {
    buttons.forEach(button => button.disabled = false);
    await refreshStatus();
  }
});
document.getElementById('paste-form').addEventListener('submit', async event => {
  event.preventDefault();
  const raw = document.getElementById('storage-json').value.trim();
  if (!raw) { messageBox.textContent = 'Paste the exported JSON first.'; return; }
  buttons.forEach(button => button.disabled = true);
  messageBox.textContent = 'Verifying pasted session…';
  try {
    const result = await call('/setup/api/paste', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({content: raw})});
    messageBox.textContent = 'Session verified. ' + result.notebook_count + ' notebooks available.';
    document.getElementById('paste-form').reset();
  } catch (error) {
    messageBox.textContent = error.message;
  } finally {
    buttons.forEach(button => button.disabled = false);
    await refreshStatus();
  }
});
refreshStatus();
setInterval(refreshStatus, 3000);
</script>
</body>
</html>"""


def _credentials_valid(authorization: str | None) -> bool:
    if not SETUP_USERNAME or not SETUP_PASSWORD or not authorization:
        return False
    scheme, separator, encoded = authorization.partition(' ')
    if not separator or scheme.lower() != 'basic':
        return False
    try:
        decoded = base64.b64decode(encoded, validate=True).decode('utf-8')
    except (ValueError, UnicodeDecodeError):
        return False
    username, separator, password = decoded.partition(':')
    return bool(
        separator
        and secrets.compare_digest(username, SETUP_USERNAME)
        and secrets.compare_digest(password, SETUP_PASSWORD)
    )


def _basic_challenge() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={'detail': 'Setup credentials required'},
        headers={'WWW-Authenticate': 'Basic realm="NotebookLM setup", charset="UTF-8"'},
    )


def _operation_status() -> dict:
    with _process_lock:
        process = _auth_process
        action = _auth_action
        started = _auth_started_at
        return_code = process.poll() if process else None
    if process is None:
        operation = None
    elif return_code is None:
        operation = f'{action} running'
    elif return_code == 0:
        operation = f'{action} complete'
    else:
        operation = f'{action} failed (exit {return_code})'
    return {'operation': operation, 'started_at': started}


def _start_renew_action(storage_path: Path) -> dict:
    global _auth_process, _auth_action, _auth_started_at, _auth_log_handle
    with _process_lock:
        if _auth_process is not None and _auth_process.poll() is None:
            raise HTTPException(status_code=409, detail='An authentication operation is already running')
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        log_path = Path(tempfile.gettempdir()) / 'notebooklm-setup-auth.log'
        log_handle = log_path.open('w', encoding='utf-8')
        os.chmod(log_path, 0o600)
        command = ['notebooklm', '--storage', str(storage_path), 'auth', 'refresh', '--verify']
        try:
            _auth_process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
        except OSError as error:
            log_handle.close()
            raise HTTPException(status_code=503, detail=f'Could not start NotebookLM auth command: {error}') from error
        _auth_log_handle = log_handle
        _auth_action = 'renew'
        _auth_started_at = time.time()
    return {'ok': True, 'message': 'Session renewal started. Check the connection when it finishes.'}


async def _check_storage(storage_path: Path) -> int:
    client = await NotebookLMClient.from_storage(str(storage_path))
    async with client:
        notebooks = await client.notebooks.list()
    return len(notebooks)


class PastedSession(BaseModel):
    content: str


async def _install_storage(raw: bytes, storage_path: Path) -> dict:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail='Session JSON exceeds 2 MiB')
    operation = _operation_status().get('operation')
    if operation and operation.endswith(' running'):
        raise HTTPException(status_code=409, detail='Wait for the active authentication operation to finish')
    try:
        state = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=400, detail='Session must be valid JSON') from error
    cookies = state if isinstance(state, list) else state.get('cookies') if isinstance(state, dict) else None
    if not isinstance(cookies, list) or not cookies or any(not isinstance(cookie, dict) for cookie in cookies):
        raise HTTPException(status_code=400, detail='JSON must contain a cookies array or be a Cookie Editor cookie list')
    normalized_cookies = []
    for cookie in cookies:
        if not isinstance(cookie.get('name'), str) or not isinstance(cookie.get('value'), str) or not isinstance(cookie.get('domain'), str):
            raise HTTPException(status_code=400, detail='Each cookie must include string name, value, and domain fields')
        normalized = {
            'name': cookie['name'], 'value': cookie['value'], 'domain': cookie['domain'],
            'path': cookie.get('path') or '/', 'httpOnly': bool(cookie.get('httpOnly', False)),
            'secure': bool(cookie.get('secure', False)),
        }
        expires = -1 if cookie.get('session') else cookie.get('expires', cookie.get('expirationDate', -1))
        if isinstance(expires, (int, float)) and not isinstance(expires, bool):
            normalized['expires'] = expires
        same_site = {
            'strict': 'Strict', 'lax': 'Lax', 'no_restriction': 'None',
            'Strict': 'Strict', 'Lax': 'Lax', 'None': 'None',
        }.get(cookie.get('sameSite'))
        if same_site:
            normalized['sameSite'] = same_site
        normalized_cookies.append(normalized)
    state = {'cookies': normalized_cookies, 'origins': state.get('origins', []) if isinstance(state, dict) else []}
    raw = json.dumps(state, separators=(',', ':')).encode('utf-8')
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='wb', dir=storage_path.parent, prefix='.storage_state-', delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            os.chmod(temp_path, 0o600)
            temp_file.write(raw)
        count = await _check_storage(temp_path)
        os.replace(temp_path, storage_path)
        os.chmod(storage_path, 0o600)
    except Exception as error:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        message = str(error).splitlines()[0][:240] or type(error).__name__
        raise HTTPException(status_code=400, detail=f'Session was not installed because verification failed: {message}') from error
    return {'ok': True, 'notebook_count': count}


def install_setup_portal(app: FastAPI, storage_path: str) -> None:
    resolved_storage_path = Path(storage_path).expanduser().resolve()
    router = APIRouter()

    @app.middleware('http')
    async def protect_setup_portal(request: Request, call_next):
        if request.url.path == '/setup' or request.url.path.startswith('/setup/'):
            if not SETUP_USERNAME or not SETUP_PASSWORD:
                return JSONResponse(status_code=503, content={'detail': 'Setup Basic Auth is not configured'})
            if not _credentials_valid(request.headers.get('authorization')):
                return _basic_challenge()
            if request.url.path.startswith('/setup/api/') and request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
                origin = request.headers.get('origin', '')
                request_host = request.headers.get('host', '').lower()
                if not origin or urlsplit(origin).netloc.lower() != request_host:
                    return JSONResponse(status_code=403, content={'detail': 'Same-origin request required'})
            if request.url.path in {'/setup/api/upload', '/setup/api/paste'}:
                content_length = request.headers.get('content-length')
                if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES + 65536:
                    return JSONResponse(status_code=413, content={'detail': 'Session JSON exceeds 2 MiB'})
        return await call_next(request)

    @router.get('/')
    async def home():
        return RedirectResponse('/setup', status_code=307)

    @router.get('/setup', response_class=HTMLResponse)
    async def setup_page():
        return HTMLResponse(SETUP_PAGE)

    @router.get('/setup/api/status')
    async def setup_status():
        exists = resolved_storage_path.is_file()
        modified = None
        size = None
        if exists:
            metadata = resolved_storage_path.stat()
            modified = datetime.fromtimestamp(metadata.st_mtime, timezone.utc).isoformat(timespec='seconds')
            size = metadata.st_size
        result = _operation_status()
        result.update({'auth_file': exists, 'modified': modified, 'size_bytes': size})
        return result

    @router.post('/setup/api/renew')
    async def renew_session():
        if not resolved_storage_path.is_file():
            raise HTTPException(status_code=404, detail='No session file yet; upload one first')
        return _start_renew_action(resolved_storage_path)

    @router.post('/setup/api/check')
    async def check_session():
        if not resolved_storage_path.is_file():
            raise HTTPException(status_code=404, detail='No session file yet; upload one first')
        try:
            count = await _check_storage(resolved_storage_path)
        except Exception as error:
            message = str(error).splitlines()[0][:240] or type(error).__name__
            raise HTTPException(status_code=502, detail=f'NotebookLM check failed: {message}') from error
        return {'ok': True, 'notebook_count': count}

    @router.post('/setup/api/upload')
    async def upload_session(file: UploadFile = File(...)):
        raw = await file.read(MAX_UPLOAD_BYTES + 1)
        await file.close()
        return await _install_storage(raw, resolved_storage_path)

    @router.post('/setup/api/paste')
    async def paste_session(body: PastedSession):
        return await _install_storage(body.content.encode('utf-8'), resolved_storage_path)

    app.include_router(router)
