# Architecture

This project is a modular monolith. `app/api` owns HTTP concerns, `app/services`
owns query orchestration, and `app/integrations` owns Vanna, LLM and MySQL adapters.
The UI never accesses MySQL or LLM credentials directly.

Runtime Chroma data is excluded from Git. The current local store remains at
`chroma_ai_analytics` for compatibility; deployment sets `CHROMA_PATH` to a
mounted storage volume such as `storage/chroma_ai_analytics`.
