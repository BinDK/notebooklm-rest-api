# Handoff: NotebookLM REST API

Continue the `BinDK/notebooklm-rest-api` fork for Dokploy. User authorized commit/push to their fork only; never push upstream `origin`.

## Git
- Checkout: `/Users/MAC/git/jemmia/notebooklm-api`, branch `master`.
- Fork remote: `binkd` (`git@github.com:BinDK/notebooklm-rest-api.git`). Verify remote before pushing; only push `binkd master`.

## Auth state
Cookie Editor export works; no custom extension needed. `/Users/MAC/Downloads/zen notebook.json` uploaded successfully, and `/setup/api/check` passed (4 notebooks). Never print cookie values. Auth persists in Podman/Docker volume `notebooklm_data` at `/data/notebooklm`. Local host port is 8001. User has currently run `podman compose down`; do not assume app is running.

## Implementation
- `setup_portal.py`: Cookie Editor instructions, file upload or pasted JSON with shared verification; removed extension download route.
- `source_portal.py`: multi-URL form, clear inputs, destructive clear-all-sources, continuation notebook after source-limit error.
- `app.py`: installs source portal.
- `README.md`: updated setup/source manager docs.
- The unused `browser_extension/` helper was removed.

The installed `notebooklm-py` has `sources.add_url(...)`, which handles URL and YouTube sources; it does not expose `add_youtube`. Source-capacity error wording may need adjustment after a real limit is observed. Syntax parsed successfully. Isolated HTTP smoke checks passed for paste validation, continuation notebooks, and deleting all sources. User currently has Compose down; run `rtk podman compose up --build -d` from repo when appropriate. UIs: `http://127.0.0.1:8001/setup` and `/setup/sources`. Keep volume; never kill unrelated port-8000 process.

All shell commands must be prefixed with `rtk` per `/Users/MAC/.codex/RTK.md`.
