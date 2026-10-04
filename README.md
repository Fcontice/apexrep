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

The frontend needs `BACKEND_URL` and `INTERNAL_TOKEN` in `frontend/.env.local`; the token must match the backend's `INTERNAL_TOKEN` in `.env`.

## API types

The frontend's API types are generated from the backend's OpenAPI schema. After changing a route or response model:

```
cd backend
uv run apexrep-export-openapi
cd ../frontend
npm run gen:api
```

## Checks

```
cd backend
uv run ruff check . ; uv run ruff format --check . ; uv run mypy ; uv run pytest
```

The player service tests run against the Docker Postgres in a separate `apexrep_test` database, and are skipped if it is not running (`docker compose up -d db`).

```
cd frontend
npm run lint ; npm run typecheck ; npm run format:check
```
