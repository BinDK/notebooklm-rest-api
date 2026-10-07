from __future__ import annotations

import asyncio
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

from fastapi import APIRouter, FastAPI, File, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from notebooklm import NotebookLMClient
from starlette.staticfiles import StaticFiles
from websockets.asyncio.client import connect as websocket_connect


MAX_UPLOAD_BYTES = 2 * 1024 * 1024
NOVNC_ROOT = Path('/usr/share/novnc')
SETUP_USERNAME = os.environ.get('NOTEBOOKLM_SETUP_USERNAME', '')
SETUP_PASSWORD = os.environ.get('NOTEBOOKLM_SETUP_PASSWORD', '')
REMOTE_BROWSER_ENABLED = os.environ.get('NOTEBOOKLM_REMOTE_BROWSER_ENABLED') == '1'

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
  <title>NotebookLM sign-in</title>
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
    iframe { width: 100%; height: 620px; border: 1px solid #c7cfda; border-radius: 8px; background: #111; }
    input[type=file] { display: block; margin: 10px 0; max-width: 100%; }
    code { overflow-wrap: anywhere; }
  </style>
</head>
<body>
  <h1>NotebookLM access</h1>
  <p class="muted">Sign in, renew, or upload a session file. Google credentials are entered only on Google's page.</p>
  <section class="card">
    <h2>Session status</h2>
    <div id="status">Checking…</div>
    <p id="message" role="status"></p>
    <div class="actions">
      <button id="login">Sign in with Google</button>
      <button class="secondary" id="renew">Renew session now</button>
      <button class="secondary" id="check">Check connection</button>
    </div>
  </section>
  <section class="card" id="browser-card">
    <h2>Google sign-in browser</h2>
    <p class="muted">After starting sign-in, complete it in the browser below and wait for the NotebookLM home page.</p>
    __REMOTE_BROWSER_CONTENT__
  </section>
  <section class="card">
    <h2>Upload a session file</h2>
    <p class="muted">Choose your own <code>storage_state.json</code>. The file is validated before it replaces the active session and is stored with owner-only permissions.</p>
    <form id="upload-form">
      <input type="file" id="storage-file" name="file" accept="application/json,.json" required>
      <button type="submit">Upload and verify</button>
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
    if (result.remote_browser_enabled && result.operation === 'login running') {
      messageBox.textContent = 'Complete Google sign-in in the browser below; this page will keep checking.';
    }
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
document.getElementById('login').addEventListener('click', () => start('/setup/api/login', 'Starting Google sign-in'));
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


def _start_auth_action(storage_path: Path, action: str) -> dict:
    global _auth_process, _auth_action, _auth_started_at, _auth_log_handle
    with _process_lock:
        if _auth_process is not None and _auth_process.poll() is None:
            raise HTTPException(status_code=409, detail='An authentication operation is already running')
        storage_path.parent.mkdir(parents=True, exist_ok=True)
        log_path = Path(tempfile.gettempdir()) / 'notebooklm-setup-auth.log'
        log_handle = log_path.open('w', encoding='utf-8')
        os.chmod(log_path, 0o600)
        if action == 'login':
            command = ['python', 'setup_browser_login.py', '--storage', str(storage_path)]
        else:
            command = ['notebooklm', '--storage', str(storage_path), 'auth', 'refresh', '--verify']
        environment = os.environ.copy()
        if REMOTE_BROWSER_ENABLED:
            environment['DISPLAY'] = environment.get('DISPLAY', ':99')
        try:
            _auth_process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=environment,
            )
        except OSError as error:
            log_handle.close()
            raise HTTPException(status_code=503, detail=f'Could not start NotebookLM auth command: {error}') from error
        _auth_log_handle = log_handle
        _auth_action = action
        _auth_started_at = time.time()
    return {'ok': True, 'message': f'{action.capitalize()} started. Complete it in the browser or wait for renewal.'}


async def _check_storage(storage_path: Path) -> int:
    client = await NotebookLMClient.from_storage(str(storage_path))
    async with client:
        notebooks = await client.notebooks.list()
    return len(notebooks)


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
            if request.url.path == '/setup/api/upload':
                content_length = request.headers.get('content-length')
                if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_BYTES + 65536:
                    return JSONResponse(status_code=413, content={'detail': 'Session file exceeds 2 MiB'})
        return await call_next(request)

    @router.get('/')
    async def home():
        return RedirectResponse('/setup', status_code=307)

    @router.get('/setup', response_class=HTMLResponse)
    async def setup_page():
        if REMOTE_BROWSER_ENABLED and NOVNC_ROOT.is_dir():
            browser = '<iframe title="Google sign-in browser" src="/setup/vnc/vnc.html?autoconnect=1&amp;resize=scale&amp;path=setup/vnc/websockify"></iframe>'
        else:
            browser = '<p class="muted">The browser will open on this machine. Complete Google sign-in in that browser window.</p>'
        return HTMLResponse(SETUP_PAGE.replace('__REMOTE_BROWSER_CONTENT__', browser))

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
        result.update({'auth_file': exists, 'modified': modified, 'size_bytes': size, 'remote_browser_enabled': REMOTE_BROWSER_ENABLED})
        return result

    @router.post('/setup/api/login')
    async def start_login():
        if REMOTE_BROWSER_ENABLED and not NOVNC_ROOT.is_dir():
            raise HTTPException(status_code=503, detail='Remote browser UI is unavailable in this image')
        return _start_auth_action(resolved_storage_path, 'login')

    @router.post('/setup/api/renew')
    async def renew_session():
        if not resolved_storage_path.is_file():
            raise HTTPException(status_code=404, detail='No session file yet; sign in or upload one first')
        return _start_auth_action(resolved_storage_path, 'renew')

    @router.post('/setup/api/check')
    async def check_session():
        if not resolved_storage_path.is_file():
            raise HTTPException(status_code=404, detail='No session file yet; sign in or upload one first')
        try:
            count = await _check_storage(resolved_storage_path)
        except Exception as error:
            message = str(error).splitlines()[0][:240] or type(error).__name__
            raise HTTPException(status_code=502, detail=f'NotebookLM check failed: {message}') from error
        return {'ok': True, 'notebook_count': count}

    @router.post('/setup/api/upload')
    async def upload_session(file: UploadFile = File(...)):
        if _operation_status().get('operation', '').endswith(' running'):
            raise HTTPException(status_code=409, detail='Wait for the active authentication operation to finish')
        raw = await file.read(MAX_UPLOAD_BYTES + 1)
        await file.close()
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail='Session file exceeds 2 MiB')
        try:
            state = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HTTPException(status_code=400, detail='Upload must be a valid JSON storage_state file') from error
        cookies = state.get('cookies') if isinstance(state, dict) else None
        if not isinstance(cookies, list) or not cookies or any(not isinstance(cookie, dict) for cookie in cookies):
            raise HTTPException(status_code=400, detail='Storage file must contain a non-empty cookies array')
        resolved_storage_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='wb', dir=resolved_storage_path.parent, prefix='.storage_state-', delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                os.chmod(temp_path, 0o600)
                temp_file.write(raw)
            count = await _check_storage(temp_path)
            os.replace(temp_path, resolved_storage_path)
            os.chmod(resolved_storage_path, 0o600)
        except Exception as error:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            message = str(error).splitlines()[0][:240] or type(error).__name__
            raise HTTPException(status_code=400, detail=f'Upload was not installed because verification failed: {message}') from error
        return {'ok': True, 'notebook_count': count}

    @router.websocket('/setup/vnc/{path:path}')
    async def vnc_websocket(websocket: WebSocket, path: str):
        if path.rsplit('/', 1)[-1] != 'websockify':
            await websocket.close(code=4404)
            return
        if not SETUP_USERNAME or not SETUP_PASSWORD:
            await websocket.close(code=1013)
            return
        if not _credentials_valid(websocket.headers.get('authorization')):
            await websocket.close(code=4401)
            return
        origin = websocket.headers.get('origin', '')
        host = websocket.headers.get('host', '').lower()
        if not origin or urlsplit(origin).netloc.lower() != host:
            await websocket.close(code=4403)
            return
        try:
            upstream = await websocket_connect('ws://127.0.0.1:6080/websockify', max_size=None)
        except Exception:
            await websocket.close(code=1013)
            return
        await websocket.accept()

        async def browser_to_vnc():
            while True:
                message = await websocket.receive()
                if message['type'] == 'websocket.disconnect':
                    return
                if message.get('bytes') is not None:
                    await upstream.send(message['bytes'])
                elif message.get('text') is not None:
                    await upstream.send(message['text'])

        async def vnc_to_browser():
            async for message in upstream:
                if isinstance(message, bytes):
                    await websocket.send_bytes(message)
                else:
                    await websocket.send_text(message)

        tasks = [asyncio.create_task(browser_to_vnc()), asyncio.create_task(vnc_to_browser())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await upstream.close()
            try:
                await websocket.close()
            except Exception:
                pass

    app.include_router(router)
    if NOVNC_ROOT.is_dir():
        app.mount('/setup/vnc', StaticFiles(directory=str(NOVNC_ROOT), html=True), name='novnc')
