FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements-app.txt ./
RUN pip install --upgrade pip && pip install -r requirements-app.txt uvicorn

COPY app ./app
COPY ui ./ui
COPY scripts ./scripts
COPY run_api.py run_streamlit.py pyproject.toml ./

RUN mkdir -p /app/storage/chroma_ai_analytics /app/logs

EXPOSE 8010

CMD ["uvicorn", "run_api:app", "--host", "0.0.0.0", "--port", "8010"]
