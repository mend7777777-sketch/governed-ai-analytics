# Connect Vanna to MySQL

## 1. Install dependencies

Activate the virtual environment, then install Vanna together with its MySQL, Chroma, and OpenAI optional dependencies:

```powershell
pip install --upgrade "vanna[chromadb,openai,mysql]" python-dotenv mysql-connector-python
```

The demo intentionally uses Vanna 2's compatibility imports:
`vanna.legacy.chromadb` and `vanna.legacy.openai`.

## 2. Configure secrets

Copy `.env.example` as `.env` in this same directory and replace each placeholder. Do not put real credentials in source code.

For a third-party relay, `OPENAI_BASE_URL` must be the provider's documented
OpenAI-compatible API root, commonly ending in `/v1`; it must not be its web
site, console, or chat page.

The configured MySQL account should have `SELECT` permission only after mock data has been loaded.

## 3. Train once

```powershell
python .\scripts\legacy\vanna_mysql_demo.py --train
```

This writes the learned DDL, metric definitions, and four SQL examples to `storage/chroma_ai_analytics`.

## 4. Ask a question

```powershell
python .\scripts\legacy\vanna_mysql_demo.py --question "2025年12月哪个品类退款率最高？"
python .\scripts\legacy\vanna_mysql_demo.py --question "2025年11月华东各省GMV是多少？"
```

For questions that require Vanna to run an intermediate discovery query, use the
following flag only with non-sensitive mock data. It permits the intermediate
result to be included in the LLM prompt:

```powershell
python .\scripts\legacy\vanna_mysql_demo.py --question "2025年连续3个月下单的用户数是多少？" --allow-llm-to-see-data
```

The script prints generated SQL and the actual MySQL result. It does not yet enforce SQL security. Add a `sqlglot` validation layer before exposing this to users or a web UI.
