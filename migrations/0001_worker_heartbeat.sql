create table worker_heartbeat (
  id      int primary key default 1 check (id = 1),
  beat_at timestamptz not null
);
