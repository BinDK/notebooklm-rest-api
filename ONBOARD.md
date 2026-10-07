# Start here: NotebookLM API

This file is for the next AI working on this repository. Read it before acting; then use `AGENTS.md` for code and API conventions, `HANDOFF.md` for the latest operational state, and `README.md` for user setup. The running FastAPI service exposes exact schemas at `/openapi.json` and `/docs`.

## Current state

- Repo: `/Users/MAC/git/jemmia/notebooklm-api`, branch `master`. The user's fork is remote `binkd` (`BinDK/notebooklm-rest-api`). Upstream `origin` is reference only; never push there.
- Local Podman Compose serves `http://127.0.0.1:8001` and persists auth in the `notebooklm_data` volume. Do not remove that volume or interfere with the unrelated process on port 8000.
- The user signed in with Chrome and uploaded a fresh Cookie Editor export. The setup portal verified the session. Subsequent read-only calls to the source manager and `GET /v1/notebooks` both returned four notebooks.
- `/setup` is for session maintenance; `/setup/sources` is the operator source manager; `/v1/*` is the integration API protected by `X-API-Key`.
- Never display, log, commit, or paste Cookie Editor JSON, auth files, Basic Auth credentials, or API keys into chat.

## What is implemented

1. `app.py` provides notebook, source, chat, and artifact routes. See `/openapi.json` for payloads and `/docs` for interactive exploration.
2. `setup_portal.py` accepts a Cookie Editor JSON file or pasted JSON. It verifies NotebookLM access before replacing the saved session.
3. `source_portal.py` accepts multiple URL or YouTube sources, clears browser inputs, and offers a confirmed delete-all-sources action. It reads the account source limit and creates a continuation notebook when necessary.
4. The installed `notebooklm-py` uses `sources.add_url` for both ordinary and YouTube URLs. The old `/v1/.../sources/youtube` route was corrected to call it.

## Next work, in order

1. Ask what the user wants next. Likely next tasks are Dokploy deployment or integrating the sales app; neither has been completed here. Use the existing `master` branch on the user's fork as the starting point.
2. For Dokploy: configure the three required secrets (`NOTEBOOKLM_REST_API_KEY`, `NOTEBOOKLM_SETUP_USERNAME`, `NOTEBOOKLM_SETUP_PASSWORD`), attach HTTPS to container port 8000, and retain the auth volume. Verify `/health`, then complete `/setup` and a read-only `/v1/notebooks` call. The local host port 8001 is a Mac-only Compose mapping.
3. For source manager changes: preserve the rule that an upload or paste never replaces working auth until verification succeeds. The multi-source and delete flows have isolated HTTP checks; do not add or delete sources in a real notebook merely to test. A disposable notebook or explicit user instruction is needed for live mutation checks.
4. For sales app integration: the current `POST /v1/notebooks/{id}/chat/ask` sends only a question and notebook ID. It has no per-sales-user conversation ID or isolation. Design that mapping explicitly before sending many users' last-50 lead conversations through one notebook.

## Working rules

- On this host, prefix shell commands with `rtk` (`/Users/MAC/.codex/RTK.md`).
- Check `git status` and `git remote -v` before editing or pushing. Preserve user changes. Push only to `binkd` when the user has authorized the work; previous turns authorized this fork only.
- Keep the final report honest about what was checked live and what was only checked with mocks. Refer to the actual files and endpoints, not assumptions about NotebookLM behavior.
