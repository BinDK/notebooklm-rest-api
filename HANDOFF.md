# Handoff: NotebookLM REST API

Continue the `BinDK/notebooklm-rest-api` fork for Dokploy. User authorized commit/push to their fork only; never push upstream `origin`.

## Git
- Checkout: `/Users/MAC/git/jemmia/notebooklm-api`, branch `master`.
- Fork remote: `binkd` (`git@github.com:BinDK/notebooklm-rest-api.git`). Verify remote before pushing; only push `binkd master`.

## Auth state
Cookie Editor export works; no custom extension needed. `/Users/MAC/Downloads/zen notebook.json` uploaded successfully, and `/setup/api/check` passed (4 notebooks). Never print cookie values. Auth persists in Podman/Docker volume `notebooklm_data` at `/data/notebooklm`. Local host port is 8001. User has currently run `podman compose down`; do not assume app is running.

## Implementation
- `setup_portal.py`: Cookie Editor instructions, file upload or pasted JSON with shared verification; removed extension download route.
- `source_portal.py`: multi-URL form, clear inputs, destructive clear-all-sources, continuation notebook when account source count reaches its limit or an add returns a source-limit error.
- `app.py`: installs source portal.
- `README.md`: updated setup/source manager docs.
- The unused `browser_extension/` helper was removed.

The installed `notebooklm-py` has `sources.add_url(...)`, which handles URL and YouTube sources; it does not expose `add_youtube`. Syntax parsed successfully. Isolated HTTP smoke checks passed for paste validation, continuation notebooks, and deleting all sources.

## Live state after local Compose verification

Compose was rebuilt and started on host port 8001, preserving the volume. `/health`, `/setup`, and `/setup/sources` returned 200. The saved session file is present, but `/setup/api/check` returned 502: `CSRF token not found in HTML. Final URL: https://notebook.google.com/`. The in-app renewal failed with the same error, and re-uploading the previous Cookie Editor export failed verification without replacing the saved session. `/setup/api/sources/notebooks` now returns a clear 502 instead of 500 when auth fails. The source-manager actions cannot be tried against NotebookLM until its session works again. The [upstream troubleshooting page](https://github.com/teng-lin/notebooklm-py/blob/main/docs/troubleshooting.md) describes this exact CSRF error as potentially a page/extraction change; don't assume cookie expiry solely from this message.

Next: obtain a fresh Cookie Editor export from a currently working signed-in NotebookLM browser, paste or upload it at `/setup`, then use **Check connection**. If it still gives this CSRF error, inspect upstream notebooklm-py issues or page changes before changing the authentication model. Do not log, commit, or share cookie values. Keep `notebooklm_data`; never kill the unrelated port-8000 process.

All shell commands must be prefixed with `rtk` per `/Users/MAC/.codex/RTK.md`.
