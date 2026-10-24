-- CareCompass Supabase schema (idempotent). Run in the Supabase SQL editor.
-- The backend uses the service-role key (bypasses RLS) and filters by user_id itself.

create table if not exists public.caregivers (
  id            text primary key,
  name          text not null,
  role          text,
  qualification text,
  languages     text[] default '{}',
  rating        numeric default 4.0,
  phone         text,
  lat           double precision,
  lng           double precision,
  services      text[] default '{}',
  free_from     time,
  free_to       time
);

create table if not exists public.chat_sessions (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null,
  language      text,
  first_message text,
  input_mode    text default 'text',
  care_type     text,
  urgency       text,
  emergency     boolean default false,
  red_flags     text[] default '{}',
  reasoning     text,
  status        text default 'needs_info',
  created_at    timestamptz default now(),
  updated_at    timestamptz default now()
);

create table if not exists public.chat_steps (
  id         uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  step_index int not null,
  kind       text not null,
  payload    jsonb default '{}',
  created_at timestamptz default now(),
  unique (session_id, step_index)
);

create table if not exists public.bookings (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null,
  session_id    uuid references public.chat_sessions(id) on delete set null,
  caregiver_id  text references public.caregivers(id),
  care_type     text,
  patient_name  text not null default 'Myself',
  relation      text,
  contact_phone text,
  address       text,
  start_time    timestamptz not null,
  end_time      timestamptz not null,
  status        text default 'confirmed',
  reason        text,
  created_at    timestamptz default now(),
  cancelled_at  timestamptz
);

-- Prevent double-booking: unique per (caregiver, start_time) while active.
create unique index if not exists bookings_no_double_book
  on public.bookings (caregiver_id, start_time)
  where status in ('confirmed', 'pending');

create index if not exists chat_sessions_user_created
  on public.chat_sessions (user_id, created_at desc);

create index if not exists bookings_user_start
  on public.bookings (user_id, start_time);

create index if not exists chat_steps_session_idx
  on public.chat_steps (session_id, step_index);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------

alter table public.caregivers    enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.chat_steps    enable row level security;
alter table public.bookings      enable row level security;

-- caregivers: any authenticated user may read.
drop policy if exists caregivers_read on public.caregivers;
create policy caregivers_read on public.caregivers
  for select to authenticated using (true);

-- chat_sessions: an authenticated user can select/delete their own rows.
drop policy if exists chat_sessions_own on public.chat_sessions;
create policy chat_sessions_own on public.chat_sessions
  for select to authenticated using (auth.uid() = user_id);
drop policy if exists chat_sessions_own_delete on public.chat_sessions;
create policy chat_sessions_own_delete on public.chat_sessions
  for delete to authenticated using (auth.uid() = user_id);

-- chat_steps: via the parent session.
drop policy if exists chat_steps_own on public.chat_steps;
create policy chat_steps_own on public.chat_steps
  for select to authenticated
  using (exists (select 1 from public.chat_sessions s where s.id = session_id and s.user_id = auth.uid()));
drop policy if exists chat_steps_own_delete on public.chat_steps;
create policy chat_steps_own_delete on public.chat_steps
  for delete to authenticated
  using (exists (select 1 from public.chat_sessions s where s.id = session_id and s.user_id = auth.uid()));

-- bookings: an authenticated user can select/delete their own rows.
drop policy if exists bookings_own on public.bookings;
create policy bookings_own on public.bookings
  for select to authenticated using (auth.uid() = user_id);
drop policy if exists bookings_own_delete on public.bookings;
create policy bookings_own_delete on public.bookings
  for delete to authenticated using (auth.uid() = user_id);
