# cdp web

FastAPI backend (`web/api/`) + Vite/React frontend (`web/frontend/`), with a
typed API client (`web/client/`) generated from the backend's OpenAPI schema.

## Install

From the repo root:

```bash
# Backend: installs cdp + FastAPI/uvicorn/etc (see pyproject.toml's `web` extra)
pip install -e ".[web]"

# Frontend: pulls in @cdp/web-client via the `file:../client` link
cd web/frontend
npm install
```

## Run (development)

Two processes, in separate terminals:

```bash
# 1. Backend -- serves the API on :8000
uvicorn web.api.app:app --reload --port 8000
```

On startup this prints a mutation token to stdout:

```
cdp web: mutation token (send as X-CDP-Web-Token): <token>
```

Copy it into the frontend when prompted (needed only for `POST /api/run` and
`POST /api/refresh`; every other route is read-only). Pin it instead with
`CDP_WEB_TOKEN=<token>` if you want a stable value across restarts.

```bash
# 2. Frontend -- serves the UI on :5173, proxies /api to :8000
cd web/frontend
npm run dev
```

Open http://localhost:5173.

By default the backend resolves the repo/state dir via `CDP_STORE` ->
`.cdp.toml` -> the repo registry -> `cwd/.cdp`. Point it at a specific store
with:

```bash
CDP_STORE=/path/to/repo/.cdp uvicorn web.api.app:app --reload --port 8000
```

## Regenerating the typed client

After changing a route or Pydantic model in `web/api/`:

```bash
cd web/client
npm run generate
```

This re-emits `web/openapi.json` and `web/client/schema.ts` from the live
`FastAPI` app object -- don't hand-edit `schema.ts`.

## Tests

```bash
# Backend
pytest web/tests

# Frontend
cd web/frontend
npm test
```
