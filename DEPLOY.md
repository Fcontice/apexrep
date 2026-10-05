# Deploying ApexRep

Status: **written from the code, not yet run.** Nothing has been deployed with these steps. Treat the first deploy as the test, and correct this file as you go.

Three pieces: the database on Neon, the backend and worker on Railway, the frontend on Vercel at `apexrep.xyz`.

## Before going live

- Ask Apex Legends Status on their Discord about running ads (commercial use) and about raising the rate limit. The limit is what caps tracked players.
- Re-check EA's content policy against the notes in `apexrep.md`.

## 1. Database (Neon)

1. Create a project on the Launch plan, in the same region you will use on Railway.
2. In the compute settings, turn scale-to-zero off. The worker queries every 30 seconds, so it would never idle anyway.
3. Copy the **pooled** connection string (the host contains `-pooler`). This is `DATABASE_URL`.

The string can be pasted as Neon gives it. The backend drops the `channel_binding` parameter itself, because the database driver rejects it.

Leave Neon's Data API off. Only the backend and worker connect.

## 2. Backend and worker (Railway)

Both run from the same image, built from `backend/Dockerfile` with the **repo root** as the build context (the image needs `migrations/`).

Create two services from the GitHub repo:

| Setting | API service | Worker service |
| --- | --- | --- |
| Dockerfile path | `backend/Dockerfile` | `backend/Dockerfile` |
| Start command | leave empty (the image starts the API on `$PORT`) | `apexrep-worker` |
| Pre-deploy command | `apexrep-migrate` | none |
| Health check path | `/api/health` | none |
| Public networking | on | off |
| Replicas | 1 | 1 |

Keep the API at **one replica**. The ALS rate limiter, the per-visitor limits and the profile single-flight are all in-process; a second replica would double the ALS call rate.

Variables for both services:

| Variable | Value |
| --- | --- |
| `DATABASE_URL` | the Neon pooled connection string |
| `ALS_API_KEY` | the Apex Legends Status key |
| `INTERNAL_TOKEN` | a long random string; the same value goes on Vercel |

Everything else has a default in `backend/src/apexrep/config.py` (poll intervals, rate budgets, caps, retention). Do not set `EXPOSE_API_DOCS` in production.

Check: `https://<api host>/api/health` returns `"status": "ok"` once the worker has written its first heartbeat. Any other `/api/*` path returns 403 without the token; that is expected.

## 3. Frontend (Vercel)

1. Import the repo, with **Root Directory** set to `frontend`.
2. Variables (Production):

| Variable | Value |
| --- | --- |
| `BACKEND_URL` | the Railway API service's public URL, no trailing slash |
| `INTERNAL_TOKEN` | the same value as on Railway |
| `SITE_URL` | `https://apexrep.xyz` |

3. Add the domain `apexrep.xyz` to the project and point DNS at Vercel as it instructs.

The per-visitor rate limits use the IP the frontend forwards, taken from `x-forwarded-for`. Vercel sets that header itself, so visitors cannot spoof it.

## 4. After the first deploy

- Search for a player and open the profile.
- Track one player; within a minute the worker log on Railway should show `poll run: {"polled":1}`.
- Open `/sitemap.xml` and `/robots.txt`.
- Watch the Neon storage figure for the first week and adjust `RAW_RETENTION_S` if needed; the 30-day estimate in the spec rests on an assumed change rate.
