# Apex Legends Stats Tracker — Build Spec

Oct 4, 2026 · @frank

## Overview

Build a web app where anyone can look up an Apex Legends player by platform and name, see current stats and rank, and turn on tracking for that player so the app builds a match history over time. There is no official Apex stats API, so the app reads the unofficial Apex Legends Status (ALS) API and derives history itself by snapshotting players and diffing the numbers.

MVP goals:

1. Player lookup by platform + name, resolved to a stable UID.
2. Player profile page: level, rank (BR), selected legend, its equipped trackers.
3. Tracking: any visitor can turn it on for a player (the player does not opt in themselves); a background worker then snapshots tracked players on a schedule.
4. Derived match history and simple trend charts from those snapshots.
5. Clean shareable URLs, like `/pc/<name>` redirecting to `/player/pc/<uid>`.

Out of scope for MVP: user accounts, Switch lookups by name, leaderboards, ads, browser extension.

Ads are planned after the MVP. That drives two choices below: player pages are server-rendered so search engines and ad reviewers see real content, and commercial use has to be cleared with ALS before ads go live.

## Data source

All player data comes from the [Apex Legends Status API](https://apexlegendsapi.com/) at `https://api.apexlegendsstatus.com`. Base rate limit is 5 requests per second across all endpoints, one key per project.

| Endpoint | Use in app | Params |
| --- | --- | --- |
| `GET /bridge` | Player stats, and name resolution | `uid` + `platform` (polling and refresh) or `player` + `platform` (resolving a name; the response carries the UID); also `merge`, `removeMerged` |
| `GET /nametouid` | Not used | On 2026-10-04 it failed for PC names that `/bridge?player=` resolved, so names are resolved through `/bridge` |
| `GET /maprotation` | Map rotation widget | `version=2` |
| `GET /predator` | Predator RP threshold | none |
| `GET /servers` | Server status | none |

Auth: send the key as an `Authorization` header. Read `X-Current-Rate` from responses.

Constraints the build must respect:

- PC players are looked up by their EA/Origin name, even if they play on Steam. A SteamID cannot be mapped to an EA UID.
- For a Steam player the response's `global.name` is the Steam display name, not the EA ID, and it cannot be used for lookup. Confirmed 2026-10-04: EA ID `xXfrankX` returns `name: "vinyasaflowTTV"`, and looking up `vinyasaflowTTV` is a 404. The EA ID is unrelated to the Steam name; the player finds it at ea.com by signing in with Steam.
- `realtime` (online, in game) is not reliable: it reported the same player offline while they were in the game. Do not build on it.
- Each tracker entry has a `global` flag. `true` means an account-wide tracker (for example Career Kills) that stays the same whichever legend is selected; `false` means it belongs to the selected legend.
- Live stats only cover the currently selected legend and the trackers equipped on it, and that list can be empty. Everything shown is partial. The response also carries `legends.all` (trackers ALS last saw on each other legend) and `total` (sums across legends); the MVP does not use them, but they are kept in `raw`.
- `global.level` restarts from 1 when a player prestiges; `global.levelPrestige` counts the prestiges. Level is only comparable together with prestige.
- Match history, leaderboard, and legacy history endpoints are closed to new users. Do not depend on them.
- Error codes: 400 retry later, 403 bad key, 404 player not found, 405 upstream error, 410 bad platform, 429 rate limited, 500 internal error. One known client library reports the API can return 200 instead of 429 when limited, so validate response bodies. Confirmed on 2026-10-04: `/nametouid` answers an unknown PC name with HTTP 200 and `{"Error": "Player not found. Please try again (err origin lookup)"}`, so errors must be detected from the body, not the status.
- Show a clickable link labelled "Data provided by Apex Legends Status" to apexlegendsstatus.com on every page that shows API data.
- Usage is fair-use only and keys can be suspended without notice ([usage rules](https://apexlegendsapi.com/usage-rules)). Cache aggressively.
- The `/bridge` field names used below are not in the public docs; they were confirmed against a response recorded on 2026-10-04 (`backend/tests/fixtures/als/bridge_ok.json`). The UID arrives as a string.

- Commercial use: the usage rules do not mention it either way. Before putting ads on the site, ask ALS on their Discord for permission; the same channel is how the rate limit gets raised, and that limit is what caps tracked players.

Fallback, not in MVP: [Tracker Network API](https://apex.tracker.gg/site-api), 30 requests per 60 seconds, non-commercial only, so it is not usable once the site carries ads.

## EA content policy and monetisation

Context from Frank's read of EA's content policy (Oct 2026). It has not been re-checked against EA's policy page here; confirm it before launch.

What the policy allows:

- Fans can use EA game content for personal projects, including fan sites, without asking.
- Passive banner ads on a fan site are allowed.
- Selling the content is not allowed. That includes putting the site or its content behind a paywall such as Patreon.

What that means for this site:

- Free site with banner ads: fine.
- Paid "Pro" tier (like CSRep's "Remove Ads" upgrade): likely conflicts with the no-paywall rule. Get EA's written permission first, through the licensing contact on their content-permission page, before launching any paid feature.
- Disclaimer: any page showing game content states that the site is not endorsed by or affiliated with EA or its licensors. It goes in the footer.
- Branding: the name and logo must not look official. No EA or Respawn logos. Legend art and icons count as game content, so the rules above apply to them.
- No mixing with other brands: EA says not to combine its game content with third-party products, services or brands, so no sponsor tie-ins built around Apex assets.

The data does not come from EA. The Apex Legends Status fair-use terms and attribution requirement (see Data source) are what govern data access, and the Tracker Network fallback is non-commercial only.

## Architecture and stack

&#91;embedded content: system architecture · 5 components\]

The browser only talks to the Next.js app. Next.js renders pages on the server and forwards `/api/*` calls to the FastAPI backend, which is the only thing that talks to ALS. The backend and the worker share one ALS client class and one Postgres database. They are separate processes, so each gets its own slice of the ALS rate budget (see Backend API routes, Rules).

| Layer | Choice |
| --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic v2, httpx (async), asyncpg or SQLAlchemy 2 async; one uvicorn process |
| Worker | Same Python package as the backend, run as a separate asyncio process (second entrypoint) |
| Database | Neon Postgres (Launch plan), plain SQL migrations in `migrations/` |
| Frontend | Next.js 16 (App Router), React, TypeScript, TanStack Query, Recharts, Tailwind v4 |
| Hosting (suggested) | Frontend on Vercel; backend and worker on Railway or Fly.io |
| Domain | `apexrep.xyz` (the frontend's `SITE_URL`, used for canonical and Open Graph URLs) |

Database notes:

- Create the Neon project in the same region as the backend and worker.
- Connect with Neon's pooled connection string (the `-pooler` host). It is PgBouncer in transaction mode, so disable prepared statements (`statement_cache_size=0` in asyncpg) and use only transaction-scoped advisory locks.
- The worker queries every 30 seconds, so the compute never idles; turn scale-to-zero off rather than rely on it.
- Local development uses Docker Postgres. A Neon branch per feature branch is optional for testing against real data.

## URL scheme and player resolution

UIDs are the canonical key; names are only an entry point because players rename.

| URL | Behavior |
| --- | --- |
| `/` | Search box: platform select + name input |
| `/{platform}/{name}` | Resolve on the server, then temporary redirect (307) to the canonical URL |
| `/player/{platform}/{uid}` | Canonical profile page |
| `/player/{platform}/{uid}/matches` | Derived match history |

`platform` in URLs is lowercase `pc`, `ps`, `xbox`, mapped to API values `PC`, `PS4`, `X1`.

These are Next.js server routes:

- The `/{platform}/{name}` route returns a 404 page unless `platform` is `pc`, `ps` or `xbox`.
- Names are URL-encoded in links and decoded before the API call (names can contain spaces and other reserved characters).
- The redirect is temporary, not permanent, because a name can later belong to a different player.

Resolution flow for `/{platform}/{name}` (the route calls `/api/resolve`, which does steps 1 to 4):

1. Normalize the name (trim, case-insensitive compare).
2. Check `player_aliases` for a cached match newer than 24 hours. Hit: return it.
3. Miss: call `/bridge?player=...`. Not found: remember the miss in memory for 5 minutes so repeat lookups do not spend quota, and return 404. The page renders "player not found" with a hint that PC uses the EA name, not the Steam name.
4. Upsert `players` and `player_aliases` (the alias is the name the visitor typed, which ALS just resolved, not the display name in the response), store the response as the player's first snapshot (so the profile page that follows needs no second ALS call), return `{ uid, platform, name }`; the route redirects to `/player/{platform}/{uid}`.

Profile page load (server-rendered, calling `GET /api/players/{platform}/{uid}`):

1. Read the latest snapshot for the UID and set `last_viewed_at`.
2. If `last_polled_at` is older than 5 minutes and the backend's ALS budget has room, run `ingest_snapshot` (see Polling worker), then render.
3. If the API fails or the budget is used up, render the cached snapshot with a "last updated" timestamp (`last_polled_at`).
4. Requests from known crawler user agents get the cached snapshot only: they never trigger an ALS call and do not update `last_viewed_at`, so crawlers cannot spend quota or keep tracking alive.

## Data model

Five Postgres tables. Snapshots are stored only when something changed, and keep the raw API response for a limited time so new stats can be extracted later without refetching.

```sql
create table players (
  uid             text not null,
  platform        text not null check (platform in ('PC','PS4','X1')),
  current_name    text not null,
  is_tracked      boolean not null default false,
  tracked_since   timestamptz,
  last_polled_at  timestamptz,
  next_poll_at    timestamptz,
  unchanged_polls int not null default 0,
  not_found_count int not null default 0,
  last_viewed_at  timestamptz,
  created_at      timestamptz not null default now(),
  primary key (uid, platform)
);
create index on players (next_poll_at) where is_tracked;

create table player_aliases (
  platform     text not null,
  name_lower   text not null,
  uid          text not null,
  resolved_at  timestamptz not null default now(),
  primary key (platform, name_lower),
  foreign key (uid, platform) references players (uid, platform)
);

create table snapshots (
  id             bigserial primary key,
  uid            text not null,
  platform       text not null,
  taken_at       timestamptz not null default now(),
  level          int,
  level_prestige int not null default 0,
  level_progress int,
  rank_name      text,
  rank_div       int,
  rank_score     int,
  selected_legend text,
  trackers       jsonb not null default '{}',
  raw            jsonb,
  foreign key (uid, platform) references players (uid, platform)
);
create index on snapshots (uid, platform, taken_at desc);

create table matches (
  id              bigserial primary key,
  uid             text not null,
  platform        text not null,
  kind            text not null default 'match' check (kind in ('match','session_gap')),
  detected_at     timestamptz not null,
  prev_snapshot_id bigint not null references snapshots (id),
  next_snapshot_id bigint not null references snapshots (id),
  legend          text,
  level_progress_delta int,
  rank_score_delta int,
  tracker_deltas  jsonb not null default '{}',
  unique (prev_snapshot_id, next_snapshot_id),
  foreign key (uid, platform) references players (uid, platform)
);
create index on matches (uid, platform, detected_at desc, id desc);

create table worker_heartbeat (
  id      int primary key default 1 check (id = 1),
  beat_at timestamptz not null
);
```

`trackers` is a flat map of tracker key to value for the selected legend, for example `{"kills": 1520, "damage": 402311}`, built with `merge` and `removeMerged` so event trackers collapse into base keys.

Access: only the backend and worker reach the database, over `DATABASE_URL`. Leave Neon's Data API off.

Storage budget. Three responses measured on 2026-10-04 were 9 KB, 14 KB and 22 KB; most of that is `legends.all`. Storing a snapshot on every poll would be 200 players × 360 polls a day = 72,000 rows a day, about 1 to 1.6 GB a day before Postgres compression, almost all of it duplicates. So:

- A snapshot row is inserted only when `level`, `level_prestige`, `level_progress`, the rank fields, `selected_legend` or `trackers` differ from the player's latest snapshot. An unchanged poll only updates `players`.
- `raw` is set to null on snapshots older than 30 days (config). At an assumed 20 changed snapshots per player per day, that is 200 × 20 × 30 = 120,000 rows holding raw JSON, about 1.7 to 2.6 GB before compression. Neon's Launch plan bills storage by the GB with no cap, so this is a running cost, not a limit.
- The change rate is still an assumption. Measure it in the first week of tracking, then adjust the retention window.

## Polling worker and match derivation

A separate worker process polls tracked players, every 4 minutes while they are active and every 15 minutes while idle, and records a match when a poll shows progress since the last stored snapshot.

Both the worker and the profile page load go through one function, `ingest_snapshot(uid, platform)`:

1. Call `/bridge?uid=...&platform=...&merge=1&removeMerged=1`.
2. Open a transaction and take `pg_advisory_xact_lock` on a hash of platform + UID, so two writers cannot diff against the same previous snapshot.
3. Compare the response with the player's latest snapshot. If it changed, insert a snapshot and run match detection.
4. Update `players`: `last_polled_at`, `current_name` from the response, reset `not_found_count`. `current_name` is a display name only; it never creates or changes an alias, because for Steam players it is not a name ALS can resolve.

The backend also holds an in-process lock per player around `ingest_snapshot`, so concurrent loads of one profile make one ALS call.

Worker loop, every 30 seconds:

1. Write `worker_heartbeat`.
2. Untrack players whose `last_viewed_at` is older than 14 days.
3. Select tracked players where `next_poll_at` is null or in the past, oldest first.
4. Push them through the worker's rate limiter (3 requests per second) and run `ingest_snapshot` for each.
5. Set `next_poll_at`: 4 minutes ahead after a changed poll (and reset `unchanged_polls`); after 5 unchanged polls in a row, 15 minutes ahead.
6. On 429 or a rate-limit body, back off exponentially for that batch. On 404, increment `not_found_count` and untrack the player at 3 in a row, with a log line.

Rate budget: 200 tracked players all active at a 4-minute interval is 200 / 240 s = 0.83 requests per second, well under the worker's 3 per second.

Match detection rules, comparing the latest stored snapshot A to the new snapshot B:

- A match happened if level progress increased, or if the legend is unchanged and any tracker present in both A and B increased. Level progress is compared as the triple (`level_prestige`, `level`, `level_progress`), in that order, because `level` restarts at each prestige; `level_progress` is the API's `toNextLevelPercent`.
- A `rank_score` change on its own is not a match (split and season resets move it). When a match is detected, record `rank_score_delta` alongside it.
- `level_progress_delta` = (B.level − A.level) × 100 + (B.level_progress − A.level_progress), in percentage points, or null when `level_prestige` changed between A and B. There is no XP figure in the API, so XP itself cannot be stored.
- If `selected_legend` is the same in A and B, `tracker_deltas` = B minus A for keys present in both, positive deltas only. Trackers can be re-equipped without a legend swap, so keys in only one snapshot are ignored.
- If the legend changed, record the match with `legend = B.selected_legend` and empty `tracker_deltas`; deltas across a legend swap are not trustworthy. Possible refinement for Phase 4: trackers flagged `global` in the response are account-wide, so their deltas would still be valid across a swap.
- Several games can land inside one polling window. Treat one detected row as "one or more matches" and label it that way in the UI.
- Session gap: if the player's previous successful poll (`last_polled_at` before this one) was more than 30 minutes ago, insert the row with `kind = 'session_gap'` and null deltas instead of a match. Gap rows are only written for tracked players; for an untracked player, who is only polled when someone views the page, every visit would otherwise produce one. The gap is measured from the last poll, not from A, because A can be hours old for a player who was idle.
- Known limitation: level progress is a whole percent, so a short match that earns little XP on a legend with no moving tracker is missed.
- Known limitation: a player at the level cap (level 500 on the last prestige tier) earns no more level progress, so their matches are only detected through tracker changes.

All thresholds (poll intervals, rate caps, gap window, tracking expiry, raw retention) live in config, not code. The idle poll interval must stay below the gap window.

## Backend API routes

The FastAPI backend is the only thing that talks to ALS; the API key never reaches the browser. The browser never calls the backend directly: Next.js server components call it, and a catch-all Next.js route handler (`app/api/[...path]/route.ts`) forwards browser `/api/*` calls to it.

| Method | Route | Returns |
| --- | --- | --- |
| GET | `/api/resolve?platform=pc&name=X` | `{ uid, platform, name }` or 404 |
| GET | `/api/players/{platform}/{uid}` | Latest snapshot as `PlayerProfile`, refreshed if last polled more than 5 min ago |
| GET | `/api/players/{platform}/{uid}/history?days=30` | Snapshot series for charts (level, rank\_score, tracker values); `days` capped at 90 |
| GET | `/api/players/{platform}/{uid}/matches?limit=50&before=cursor` | Derived matches, newest first, cursor-paginated on `(detected_at, id)` |
| POST | `/api/players/{platform}/{uid}/track` | Starts tracking; idempotent; 409 when the cap is full |
| GET | `/api/meta/maps` | Cached map rotation, refreshed every 60 s |
| GET | `/api/meta/predator` | Cached Predator thresholds, refreshed every 15 min |
| GET | `/api/health` | DB + last worker heartbeat |

Rules:

- Pydantic models for every request and response; generate TypeScript types from the OpenAPI schema.
- One `AlsClient` class wraps every ALS call: rate limiter, retries, typed errors (`PlayerNotFound`, `RateLimited`, `UpstreamError`).
- The rate limiter is in-process, so the 5 per second ALS limit is split by config: worker 3 per second, backend 1.5 per second. This only holds with a single backend process; a Postgres-backed token bucket is the upgrade if the backend ever scales out.
- Every call from Next.js carries a shared internal token header and the visitor's IP and user agent. The backend rejects requests without the token (except `/api/health`), so it needs no CORS and cannot be called around the frontend.
- Basic per-IP rate limiting on `/api/resolve` and `/track`, keyed on the forwarded visitor IP, so the public site cannot burn the ALS quota.
- A profile refresh never waits on the ALS budget: if the backend's slice is used up, serve the cached snapshot.
- Cap tracked players with a config value (start at 200) so polling stays under the rate budget.
- There is no public untrack route: without accounts, anyone could untrack anyone. Tracking ends on its own after 14 days without a profile view. When the cap is full, a new track request evicts the least recently viewed tracked player if its last view is more than 24 hours old; otherwise it returns 409.
- Snapshots are change-only, so a 30-day history series is hundreds of points. If a series exceeds 2,000 points, return the last value per hour instead.

## Frontend pages

Next.js 16 App Router with TypeScript. Pages are server components that fetch from the backend; the track button, tabs and charts are client components using TanStack Query and Recharts. Tailwind v4 for styling.

| Page | Contents |
| --- | --- |
| Home `/` | Platform toggle (PC, PlayStation, Xbox), name search, map rotation card, Predator thresholds card |
| Resolve `/{platform}/{name}` | Server redirect to the profile; not-found page explaining PC uses the EA ID, that it differs from the Steam name, and how to find it (ea.com, sign in with Steam, Account Settings) |
| Profile `/player/{platform}/{uid}` | Header (name, platform, level, rank badge + RP), selected legend with its trackers, "Track this player" button, last-updated time |
| Trends tab | Line charts of level and rank score over time; one chart per tracker key with data |
| Matches tab `/player/{platform}/{uid}/matches` | Table: time, legend, level progress delta, rank score delta, tracker deltas; rows labelled "1+ matches"; `session_gap` rows shown as a divider ("untracked activity") |

UI rules:

- Every page with API data shows the "Data provided by Apex Legends Status" link in the footer.
- The footer on every page also carries the EA disclaimer: not endorsed by or affiliated with EA or its licensors. No EA or Respawn logos anywhere.
- A short note on the profile explains stats only cover equipped trackers on the selected legend.
- Tracking state is visible: untracked profiles show a call to action, tracked ones show "tracking since" and that tracking stops after 14 days without a visit.
- Mobile-first layout; profile header and charts must work at 375 px wide.
- Profile pages render name, level, rank and trackers in the server HTML, with a per-player title, description and Open Graph tags from `generateMetadata`.
- `sitemap.xml` lists tracked players' canonical URLs; `/{platform}/{name}` URLs are not indexed.

## Build phases and acceptance criteria

Build in this order; each phase ends with working, tested code and its own commits.

1. **Scaffold.** Monorepo with `backend/` (one Python package, API and worker entrypoints), `frontend/` (Next.js), `migrations/`. Docker Compose for local Postgres. `.env.example` with `ALS_API_KEY`, `DATABASE_URL`, `BACKEND_URL`, the internal token, worker config.
   - Done when: `docker compose up` starts the DB and both apps; `/api/health` returns ok.
2. **ALS client.** Record one real `/bridge` response as a fixture first, and correct the field names and the storage estimate in this spec from it. Then `AlsClient` with rate limiter, typed errors, and a parser from the `/bridge` response to a typed `PlayerSnapshot`.
   - Done when: unit tests pass against recorded JSON fixtures, including a rate-limited 200 body and a 404.
3. **Resolve + profile.** Migrations, `/api/resolve`, `/api/players/...`, `ingest_snapshot`, the Next.js API forwarder, Home and Profile pages.
   - Done when: searching a real PC EA name lands on `/player/pc/{uid}` with stats; the stats are in the page's server HTML (view source); a second load within 5 minutes makes no ALS call; two simultaneous loads make one.
4. **Tracking worker.** Track route, the polling loop, change-only snapshot storage, match detection, tracking expiry.
   - Done when: tests on snapshot pairs cover same legend, legend swap, tracker re-equip, level-up wrap, rank-only change, no change, and session gap; a tracked test account gains match rows after playing.
5. **History UI.** History and matches routes, Trends and Matches tabs. Also the Home page's map rotation and Predator cards with their `/api/meta/*` routes, deferred from Phase 3.
   - Done when: charts render from at least two days of snapshots; matches paginate.
6. **Hardening.** Per-IP limits, tracked-player cap and eviction, raw retention job, crawler handling, sitemap and metadata, attribution and EA disclaimer footer, error states, deploy config (Neon pooled connection string, internal token on both hosts).

Conventions:

- Python 3.12, explicit type hints everywhere, `ruff` + `mypy --strict`, `pytest`.
- TypeScript `strict: true`, no `any`, ESLint + Prettier.
- Conventional commits (`feat:`, `fix:`, `chore:`, `test:`, `refactor:`), one logical change per commit.
- Never commit the API key; never call ALS from the browser.
- No live ALS calls in tests; use recorded fixtures.
