# Local Runbook

1. Load mock data: `python scripts/generate_mock_data.py --reset`
2. Train knowledge: `python scripts/train_knowledge.py`
3. Start API: `python -m uvicorn run_api:app --host 127.0.0.1 --port 8010`
4. Start UI: `python run_streamlit.py`

Existing databases must execute `scripts/migrations/012_auth_hardening.sql`
before restarting the API after the authentication hardening release. This
adds token-version state, password lifecycle metadata, and the
`auth_rate_limits` table. The self-service endpoint is
`POST /api/auth/change-password`; administrators can use
`POST /api/iam/users/{username}/reset-password`.

Use `.env` for local credentials. Do not commit it. Logs are written to `logs/app.log`.

For production, set `MYSQL_SSL_DISABLED=false` only after configuring the
server certificate trust chain. Tune `DB_POOL_SIZE` to the number of API
workers and database capacity; requests wait up to
`DB_POOL_ACQUIRE_TIMEOUT_SECONDS` for a connection.
