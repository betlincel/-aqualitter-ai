-- Run manually in this project's Supabase SQL Editor as the project owner.
-- A fresh citizen_reports table is required. If it already exists, STOP and
-- inspect/migrate it explicitly; do not drop user data to re-run this script.
-- No key or credential belongs in this file. Transactional DDL, no report data.
begin;

create table public.citizen_reports (
    id uuid primary key default gen_random_uuid(),
    photo_path text not null unique,
    note text not null default '' check (char_length(note) <= 1000),
    latitude double precision not null check (latitude between -90 and 90),
    longitude double precision not null check (longitude between -180 and 180),
    accuracy_m double precision check (accuracy_m between 0 and 40000000),
    captured_at timestamptz not null check (isfinite(captured_at)),
    location_source text not null check (location_source in ('browser_geolocation', 'manual_map')),
    status text not null default 'pending_review'
        check (status in ('pending_review', 'approved', 'rejected')),
    created_at timestamptz not null default now(),
    constraint citizen_reports_photo_matches_id check (photo_path = id::text || '/photo.jpg'),
    constraint citizen_reports_accuracy_source check (
        (location_source = 'browser_geolocation' and accuracy_m is not null)
        or (location_source = 'manual_map' and accuracy_m is null)
    )
);

alter table public.citizen_reports enable row level security;
alter table public.citizen_reports force row level security;
revoke all on public.citizen_reports from public, anon, authenticated;
grant insert (id, photo_path, note, latitude, longitude, accuracy_m,
              captured_at, location_source, status) on public.citizen_reports to anon;

create policy citizen_reports_anon_insert on public.citizen_reports
    for insert to anon with check (status = 'pending_review');
-- No SELECT, UPDATE or DELETE grants/policies for citizens.
-- Owner/admin moderation is performed from the dashboard, outside this prototype.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('citizen-reports', 'citizen-reports', false, 5242880, array['image/jpeg'])
on conflict (id) do update set public = false, file_size_limit = 5242880,
    allowed_mime_types = array['image/jpeg'];

-- Upload only new UUID/photo.jpg objects. No upsert, overwriting or public reads.
create policy citizen_reports_photo_insert on storage.objects for insert to anon
with check (bucket_id = 'citizen-reports'
    and name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/photo[.]jpg$');

-- Restrictive guards ensure any unrelated, broad existing storage policies cannot
-- accidentally grant public access to this bucket. Other buckets keep their policies.
create policy citizen_reports_photo_insert_guard on storage.objects as restrictive
for insert to anon, authenticated with check (
    bucket_id <> 'citizen-reports'
    or (auth.role() = 'anon' and name ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/photo[.]jpg$')
);
create policy citizen_reports_photo_read_guard on storage.objects as restrictive
for select to anon, authenticated using (bucket_id <> 'citizen-reports');
create policy citizen_reports_photo_update_guard on storage.objects as restrictive
for update to anon, authenticated using (bucket_id <> 'citizen-reports')
with check (bucket_id <> 'citizen-reports');
create policy citizen_reports_photo_delete_guard on storage.objects as restrictive
for delete to anon, authenticated using (bucket_id <> 'citizen-reports');

commit;
