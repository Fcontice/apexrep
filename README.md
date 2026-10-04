# ApexRep

Apex Legends stats tracker. The build spec is [apexrep.md](apexrep.md).

- `backend/`: one Python package (`apexrep`) with the FastAPI app and the polling worker.
- `frontend/`: Next.js app.
- `migrations/`: plain SQL, applied in filename order by `apexrep-migrate`.

## Run everything in Docker

```
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend health: http://localhost:8000/api/health
- Postgres: `localhost:5433` (user, password and database are all `apexrep`)

## Run the apps outside Docker

Copy `.env.example` to `.env`, then:

```
docker compose up -d db
cd backend
uv run apexrep-migrate
uv run uvicorn apexrep.api.app:app --reload
uv run apexrep-worker
```

```
cd frontend
npm run dev
```

## Checks

```
cd backend
uv run ruff check . ; uv run ruff format --check . ; uv run mypy ; uv run pytest
```

```
cd frontend
npm run lint ; npm run typecheck ; npm run format:check
```
