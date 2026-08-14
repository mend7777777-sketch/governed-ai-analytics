# Governed AI Analytics

An application-layer AI analytics platform that converts natural-language questions into governed read-only SQL. It combines Vanna, ChromaDB, MySQL, FastAPI, and Streamlit, with local IAM and data-governance controls.

## Architecture

```text
Streamlit UI -> FastAPI -> Text2SQL service -> Vanna + ChromaDB -> MySQL
                    |                |
                    |                +-> read-only SQL validation
                    +-> IAM, metadata governance, audit logs
```

## Capabilities

- Natural-language Text2SQL over a MySQL star schema.
- RAG knowledge for DDL, metric definitions, business terms, and SQL examples.
- Read-only SQL validation, published-table controls, query auditing, and result limits.
- Metadata registration, approval, rejection, and revocation workflows.
- Local users, departments, positions, roles, permissions, and data-access policies.
- JWT access/refresh tokens, logout, login lockout, and IAM audit records.
- Streamlit pages for analytics, governance, knowledge, and system management.

## Local Run

1. Create `.env` from `.env.example` and set MySQL, OpenAI-compatible API, and `JWT_SECRET` values.
2. Execute the versioned SQL files in `scripts/migrations/` in order.
3. Start the API:

```powershell
D:\conda-envs\eagle39\python.exe -m uvicorn run_api:app --host 127.0.0.1 --port 8010
```

4. Start the UI:

```powershell
D:\conda-envs\eagle39\python.exe .\run_streamlit.py
```

Open `http://127.0.0.1:8501`.

## Tests

```powershell
D:\conda-envs\eagle39\python.exe -m pytest -q
```

The current suite covers SQL safety, JWT permissions, and FastAPI HTTP contracts.

## Docker Compose

Docker configuration is included in `docker-compose.yml`. See [docs/docker.md](docs/docker.md). The configuration has not been runtime-verified in this repository because Docker Desktop is not installed on the development machine.

## Security Notes

Do not commit `.env`, API keys, database passwords, JWT secrets, Chroma data, logs, or local IDE settings. These paths are excluded by `.gitignore`.
