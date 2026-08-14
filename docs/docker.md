# Docker Compose

Install Docker Desktop, then copy `.env.docker.example` to `.env` and set the required passwords, API key, JWT secret, and initial administrator password.

```bash
docker compose up -d --build
```

Open `http://localhost:8501` for the UI and `http://localhost:8010/docs` for the API. The first startup generates mock warehouse data and then initializes governance, IAM, data-access, and knowledge metadata.

Use `INITIAL_ADMIN_USERNAME` and `INITIAL_ADMIN_PASSWORD` to log in after the first startup. The account is created only for a new MySQL volume.

```bash
docker compose down
docker compose down -v  # deletes all MySQL and Chroma data
```
