-- Apply only after choosing a Supabase project and setting server secrets.
create table if not exists public.bolot_testeo_events (
  game_id uuid not null,
  seq integer not null check (seq >= 0),
  hand_index integer not null check (hand_index >= 0),
  actor integer not null check (actor between 0 and 3),
  actor_kind text not null check (actor_kind in ('human','ai')),
  phase text not null,
  observation jsonb not null,
  action jsonb not null,
  result jsonb not null,
  created_at timestamptz not null default now(),
  primary key (game_id, seq)
);
alter table public.bolot_testeo_events enable row level security;
-- No anon/authenticated policies. Only the server-side service role may insert/read.
revoke all on public.bolot_testeo_events from anon, authenticated;

