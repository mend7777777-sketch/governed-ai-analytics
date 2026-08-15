# Local Runbook

1. Load mock data: `python scripts/generate_mock_data.py --reset`
2. Train knowledge: `python scripts/train_knowledge.py`
3. Start API: `python -m uvicorn run_api:app --host 127.0.0.1 --port 8010`
4. Start UI: `python run_streamlit.py`

Existing databases must execute `scripts/migrations/012_auth_hardening.sql`
and then `scripts/migrations/013_productization.sql` before restarting the API
after the current release. `013` adds knowledge versions, metric definitions,
query history, and field governance state. The self-service endpoint is
`POST /api/auth/change-password`; administrators can use
`POST /api/iam/users/{username}/reset-password`.

Use `/api/ready` for deployment readiness checks. Every response includes an
`X-Request-ID` header, which should be propagated into centralized logs.

Use `.env` for local credentials. Do not commit it. Logs are written to `logs/app.log`.

For production, set `MYSQL_SSL_DISABLED=false` only after configuring the
server certificate trust chain. Tune `DB_POOL_SIZE` to the number of API
workers and database capacity; requests wait up to
`DB_POOL_ACQUIRE_TIMEOUT_SECONDS` for a connection.
