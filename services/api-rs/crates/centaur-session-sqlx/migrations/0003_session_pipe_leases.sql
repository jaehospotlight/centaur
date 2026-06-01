alter table sessions
    add column if not exists pipe_owner_id text,
    add column if not exists pipe_lease_expires_at timestamptz;

create index if not exists sessions_pipe_lease_expires_idx
    on sessions (pipe_lease_expires_at)
    where pipe_owner_id is not null;
