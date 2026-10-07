# Handoff: NotebookLM REST API

Start with `ONBOARD.md` for the current state and next work, then `AGENTS.md` for the API map and development rules. `README.md` is the user guide; `/openapi.json` is the generated API schema.

Continue the `BinDK/notebooklm-rest-api` fork for Dokploy. User authorized commit/push to their fork only; never push upstream `origin`.

## Git
- Checkout: `/Users/MAC/git/jemmia/notebooklm-api`, branch `master`.
- Fork remote: `binkd` (`git@github.com:BinDK/notebooklm-rest-api.git`). Verify remote before pushing; only push `binkd master`.

## Auth state
The user uploaded a fresh Cookie Editor export from Chrome; the setup page reported “Session verified. 4 notebooks available.” A subsequent live read returned 200 with four notebooks from both `/setup/api/sources/notebooks` and `/v1/notebooks`. No custom extension is needed. Never print cookie values. Auth persists in Podman/Docker volume `notebooklm_data` at `/data/notebooklm`. Local host port is 8001; Compose is running.

## Implementation
- `setup_portal.py`: Cookie Editor instructions, file upload or pasted JSON with shared verification; removed extension download route.
- `source_portal.py`: multi-URL form, clear inputs, destructive clear-all-sources, continuation notebook when account source count reaches its limit or an add returns a source-limit error.
- `app.py`: installs source portal.
- `README.md`: updated setup/source manager docs.
- The unused `browser_extension/` helper was removed.

The installed `notebooklm-py` has `sources.add_url(...)`, which handles URL and YouTube sources; it does not expose `add_youtube`. Syntax parsed successfully. Isolated HTTP smoke checks passed for paste validation, continuation notebooks, and deleting all sources.

## Live state after local Compose verification

Compose was rebuilt and started on host port 8001, preserving the volume. `/health`, `/setup`, and `/setup/sources` returned 200. The earlier Zen export later hit `CSRF token not found in HTML`; a fresh Chrome export resolved this in the latest live check. `/setup/api/sources/notebooks` returns a clear 502 if authentication fails again. Keep `notebooklm_data`; never kill the unrelated port-8000 process. The source manager's add and delete actions have isolated checks but were not run against the user's real notebooks.

All shell commands must be prefixed with `rtk` per `/Users/MAC/.codex/RTK.md`.
