-- Lets the hourly raw-retention cleanup find old snapshots that still hold a raw
-- response without scanning the whole table.
create index on snapshots (taken_at) where raw is not null;
