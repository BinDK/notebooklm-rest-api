# NotebookLM REST API: agent guide

Read this before changing the API. `README.md` is the user guide; `HANDOFF.md` records the latest operational state. FastAPI serves the exact request/response schema at `/openapi.json` and an interactive reference at `/docs`.

## Project map

- `app.py`: `/v1` REST API, request models, API-key middleware, and library error mapping.
- `setup_portal.py`: Basic Auth middleware, Cookie Editor JSON file/paste setup, session renewal and connection check.
- `source_portal.py`: Basic Auth source manager, multiple URL inputs, account-limit lookup, continuation notebooks, and clearing sources.
- `docker-compose.yml`: local/Dokploy container configuration and persistent auth volume.
- `requirements.txt`: pinned `notebooklm-py` version. Its APIs are the source of truth when changing calls into NotebookLM.

## Authentication and routes

- `/health` is unauthenticated and only reports that the process is running.
- `/v1/*` requires `X-API-Key: <NOTEBOOKLM_REST_API_KEY>`. A missing server key returns 503; a wrong client key returns 401.
- `/setup`, `/setup/sources`, and `/setup/api/*` use HTTP Basic Auth from `NOTEBOOKLM_SETUP_USERNAME` and `NOTEBOOKLM_SETUP_PASSWORD`. Mutating `/setup/api/*` calls also require a same-origin `Origin` header. These are operator routes, not the integration API.
- Session JSON is stored at `NOTEBOOKLM_STORAGE_PATH` (Compose: `/data/notebooklm/profiles/default/storage_state.json`) in the persistent `notebooklm_data` volume. Never print, commit, or send cookie values in chat or logs.

## REST API map

| Area | Main routes |
| --- | --- |
| Notebooks | `GET/POST /v1/notebooks`, `GET/DELETE /v1/notebooks/{notebook_id}`, `PATCH /v1/notebooks/{notebook_id}/rename`, summary and description GET routes |
| Sources | `GET /v1/notebooks/{notebook_id}/sources`, POST `.../sources/url`, `.../sources/youtube`, `.../sources/text`, `.../sources/file`; GET fulltext/guide and DELETE individual source |
| Chat | `POST /v1/notebooks/{notebook_id}/chat/ask` with `{"question":"..."}` |
| Artifacts | List, generate, poll task, and download under `/v1/notebooks/{notebook_id}/artifacts` |

Use `/openapi.json` for all fields and response shapes. The current chat route passes only notebook ID and question to `notebooklm-py`; it has no caller/user ID or separate conversation mapping. Do not assume chats from different sales users are isolated by this API.

## Source manager behavior

`POST /setup/api/sources/add` accepts `{"notebook_id":"existing-id","urls":["https://..."]}` or `{"title":"New notebook","urls":[...]}`. URLs are added sequentially through `client.sources.add_url(..., wait=True)`, which also handles YouTube links in the installed library. The manager reads `client.settings.get_account_limits().source_limit` when available; it creates a continuation notebook when the selected one is full. A recognized source-limit RPC error is the fallback. The response reports each added URL, errors, continuation notebooks, and the last notebook ID. The limit path has isolated smoke checks but has not been exercised against a real full notebook.

`DELETE /setup/api/notebooks/{notebook_id}/sources` deletes every source in the selected notebook. The UI confirms this before calling the route. “Clear inputs” only resets the browser form.

## Local work

- Checkout: `/Users/MAC/git/jemmia/notebooklm-api`, branch `master`.
- Compose host port: `8001`; container port: `8000`. Run `rtk podman compose up --build -d` from the checkout. Keep the auth volume when restarting.
- On this host, prefix shell commands with `rtk` per `/Users/MAC/.codex/RTK.md`.
- Push only to the user's `binkd` remote (`BinDK/notebooklm-rest-api`); never push to upstream `origin`. Verify remotes before pushing.
- After changing auth or source behavior, check the setup connection and `GET /v1/notebooks` with the configured API key. Avoid mutating real notebooks merely to test.
