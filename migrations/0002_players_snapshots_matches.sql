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
