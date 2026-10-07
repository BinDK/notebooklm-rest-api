from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from notebooklm import NotebookLMClient, RPCError
from pydantic import BaseModel


SOURCE_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NotebookLM sources</title><style>
:root{color-scheme:light;font:16px system-ui,sans-serif}body{max-width:960px;margin:32px auto;padding:0 18px;color:#172033}h1{margin-bottom:6px}.muted{color:#536174}.card{border:1px solid #d8dee8;border-radius:12px;padding:20px;margin:18px 0}.row{display:flex;gap:10px;margin:10px 0}input,select{font:inherit;padding:10px;border:1px solid #cbd5e1;border-radius:8px}input{flex:1;min-width:0}button,.button{font:inherit;border:0;border-radius:8px;padding:10px 15px;background:#175cd3;color:#fff;cursor:pointer;text-decoration:none}button.secondary{background:#e8eef8;color:#172033}button.danger{background:#b42318}button:disabled{opacity:.55;cursor:wait}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}#message{white-space:pre-wrap;min-height:24px}.small{font-size:.9rem}.tweak{position:fixed;right:12px;bottom:12px;background:#fff;border:1px solid #d8dee8;padding:8px 12px;border-radius:10px;box-shadow:0 2px 12px #0002}
</style></head><body>
<h1>NotebookLM sources</h1><p class="muted">Add several URL or YouTube sources. If NotebookLM says a notebook is full, the remaining URLs continue in a new notebook.</p>
<section class="card"><label for="notebook"><strong>Notebook</strong></label><div class="row"><select id="notebook" style="flex:1"></select><input id="new-title" placeholder="Or create a notebook by title"></div><p class="small muted">Choose an existing notebook or enter a title to create a new one for these sources.</p></section>
<section class="card"><h2>URLs</h2><div id="urls"></div><div class="actions"><button class="secondary" id="add-row">Add another URL</button><button class="secondary" id="clear-inputs">Clear inputs</button><button id="submit">Add all sources</button></div><p id="message" role="status"></p></section>
<section class="card"><h2>Clear a notebook</h2><p class="muted">Delete every source from the selected notebook.</p><button class="danger" id="delete-all">Delete all sources in selected notebook</button></section>
<aside class="tweak"><label><input type="checkbox" id="compact"> Compact spacing</label></aside>
<script>
const $=s=>document.querySelector(s), select=$('#notebook'), urls=$('#urls'), msg=$('#message'), submit=$('#submit');
async function api(path,opts={}){const r=await fetch(path,{cache:'no-store',...opts});const b=await r.json().catch(()=>({}));if(!r.ok)throw Error(b.detail||`Request failed (${r.status})`);return b}
function addRow(value=''){const row=document.createElement('div');row.className='row';const input=document.createElement('input');input.type='url';input.placeholder='https://…';input.value=value;input.required=true;const remove=document.createElement('button');remove.className='secondary';remove.textContent='Remove';remove.onclick=()=>{row.remove();if(!urls.children.length)addRow()};row.append(input,remove);urls.append(row)}
async function load(){try{const d=await api('/setup/api/sources/notebooks');select.replaceChildren(...d.items.map(n=>{const o=document.createElement('option');o.value=n.id;o.textContent=n.title||n.id;return o}));if(!d.items.length)msg.textContent='No notebooks found. Enter a title to create one.'}catch(e){msg.textContent=e.message}}
$('#add-row').onclick=()=>addRow();$('#clear-inputs').onclick=()=>{urls.replaceChildren();addRow();$('#new-title').value='';msg.textContent='Inputs cleared.'};addRow();load();
submit.onclick=async()=>{const values=[...urls.querySelectorAll('input')].map(i=>i.value.trim()).filter(Boolean),title=$('#new-title').value.trim();if(!values.length){msg.textContent='Add at least one URL.';return}if(!select.value&&!title){msg.textContent='Select a notebook or enter a new notebook title.';return}submit.disabled=true;msg.textContent='Adding sources…';try{const d=await api('/setup/api/sources/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({notebook_id:title?null:select.value||null,title,urls:values})});msg.textContent=`Added ${d.added.length} of ${values.length} source(s).`+(d.continuation_notebooks.length?`\nContinued in ${d.continuation_notebooks.map(n=>n.title).join(', ')}.`:'')+(d.errors.length?`\nFailed: ${d.errors.map(x=>x.url+': '+x.error).join('\n')}`:'');await load();if(d.last_notebook_id)select.value=d.last_notebook_id;if(!d.errors.length){urls.replaceChildren();addRow();$('#new-title').value=''}else{urls.replaceChildren();d.errors.forEach(x=>addRow(x.url))}}catch(e){msg.textContent=e.message}finally{submit.disabled=false}};
$('#delete-all').onclick=async()=>{if(!select.value)return msg.textContent='Choose a notebook first.';if(!confirm('Delete every source from this notebook? This cannot be undone.'))return;const button=$('#delete-all');button.disabled=true;try{const d=await api(`/setup/api/notebooks/${encodeURIComponent(select.value)}/sources`,{method:'DELETE'});msg.textContent=`Deleted ${d.deleted_count} source(s).`}catch(e){msg.textContent=e.message}finally{button.disabled=false}};
$('#compact').onchange=e=>document.body.style.zoom=e.target.checked?'0.85':'1';
</script></body></html>"""


class AddSourcesRequest(BaseModel):
    notebook_id: str | None = None
    title: str = ''
    urls: list[str]


def _dump(value):
    return value.model_dump() if hasattr(value, 'model_dump') else vars(value)


def _is_source_limit(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in (
        'source limit', 'maximum number of sources', 'too many sources',
        'notebook is full', 'notebook full', 'source quota', 'max sources',
    ))


async def _add(client: NotebookLMClient, notebook_id: str, url: str):
    return await client.sources.add_url(notebook_id, url, wait=True)


def install_source_portal(app: FastAPI, storage_path: str) -> None:
    router = APIRouter()

    @router.get('/setup/sources', response_class=HTMLResponse)
    async def source_page():
        return HTMLResponse(SOURCE_PAGE)

    @router.get('/setup/api/sources/notebooks')
    async def source_notebooks():
        client = await NotebookLMClient.from_storage(storage_path)
        async with client:
            try:
                items = await client.notebooks.list()
                return {'ok': True, 'items': [_dump(item) for item in items]}
            except RPCError as error:
                raise HTTPException(status_code=502, detail=str(error).splitlines()[0][:240]) from error

    @router.post('/setup/api/sources/add')
    async def add_sources(req: AddSourcesRequest):
        urls = [url.strip() for url in req.urls if url.strip()]
        if not urls:
            raise HTTPException(status_code=400, detail='Provide at least one URL')
        if any(urlsplit(url).scheme not in {'http', 'https'} or not urlsplit(url).hostname for url in urls):
            raise HTTPException(status_code=400, detail='Each source must be an http or https URL')
        client = await NotebookLMClient.from_storage(storage_path)
        added, errors, continuations = [], [], []
        async with client:
            notebook_id = req.notebook_id
            if not notebook_id:
                if not req.title.strip():
                    raise HTTPException(status_code=400, detail='Select a notebook or provide a title')
                notebook = await client.notebooks.create(req.title.strip())
                notebook_id = getattr(notebook, 'id', None) or _dump(notebook).get('id')
            for url in urls:
                try:
                    source = await _add(client, notebook_id, url)
                    added.append({'url': url, 'notebook_id': notebook_id, 'source': _dump(source)})
                except RPCError as error:
                    if not _is_source_limit(error):
                        errors.append({'url': url, 'error': str(error).splitlines()[0][:240]})
                        continue
                    try:
                        title = (req.title.strip() or 'NotebookLM sources') + f' (continued {len(continuations)+1})'
                        notebook = await client.notebooks.create(title)
                        notebook_id = getattr(notebook, 'id', None) or _dump(notebook).get('id')
                        continuations.append({'id': notebook_id, 'title': title})
                        source = await _add(client, notebook_id, url)
                        added.append({'url': url, 'notebook_id': notebook_id, 'source': _dump(source)})
                    except Exception as retry_error:
                        errors.append({'url': url, 'error': str(retry_error).splitlines()[0][:240]})
            return {'ok': not errors, 'added': added, 'errors': errors,
                    'continuation_notebooks': continuations, 'last_notebook_id': notebook_id}

    @router.delete('/setup/api/notebooks/{notebook_id}/sources')
    async def clear_notebook_sources(notebook_id: str):
        client = await NotebookLMClient.from_storage(storage_path)
        async with client:
            try:
                sources = await client.sources.list(notebook_id)
                deleted = 0
                failures = []
                for source in sources:
                    source_data = _dump(source)
                    source_id = source_data.get('id') or source_data.get('source_id')
                    if not source_id:
                        failures.append('A listed source did not include an ID')
                        continue
                    try:
                        if await client.sources.delete(notebook_id, source_id):
                            deleted += 1
                    except RPCError as error:
                        failures.append(str(error).splitlines()[0][:200])
                return {'ok': not failures, 'deleted_count': deleted, 'errors': failures}
            except RPCError as error:
                raise HTTPException(status_code=502, detail=str(error).splitlines()[0][:240]) from error

    app.include_router(router)
