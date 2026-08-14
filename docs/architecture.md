# Architecture

This project is a modular monolith. `app/api` owns HTTP concerns, `app/services`
owns query orchestration, and `app/integrations` owns Vanna, LLM and MySQL adapters.
The UI never accesses MySQL or LLM credentials directly.

Application-owned MySQL operations use a bounded lazy connection pool. Set
`DB_POOL_SIZE` per API worker and configure connection/read/write timeouts.
Text2SQL execution also applies a server-side `MAX_RESULT_ROWS + 1` limit so a
large result set is not fully materialized before the API truncates it.

SQL is parsed with `sqlglot` when installed (it is included in
`requirements-app.txt`). The compatibility path is intentionally conservative
and should be replaced by the AST path in deployed environments.

Runtime Chroma data is excluded from Git. The current local store remains at
`chroma_ai_analytics` for compatibility; deployment sets `CHROMA_PATH` to a
mounted storage volume such as `storage/chroma_ai_analytics`.
