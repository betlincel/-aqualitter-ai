-- Read-only setup checks; no citizen rows or photos are selected.
select relrowsecurity as rls_enabled, relforcerowsecurity as rls_forced
from pg_class where oid = 'public.citizen_reports'::regclass;

-- Expected: insert allowed only for submitted columns; read/update/delete false.
select has_column_privilege('anon', 'public.citizen_reports', 'photo_path', 'insert') as can_submit,
       has_table_privilege('anon', 'public.citizen_reports', 'select') as can_list,
       has_table_privilege('anon', 'public.citizen_reports', 'update') as can_update,
       has_table_privilege('anon', 'public.citizen_reports', 'delete') as can_delete;

-- Expected: public=false, file_size_limit=5242880, allowed_mime_types={image/jpeg}.
select id, public, file_size_limit, allowed_mime_types
from storage.buckets where id = 'citizen-reports';

select tablename, policyname, permissive, roles, cmd, qual, with_check
from pg_policies where (schemaname = 'public' and tablename = 'citizen_reports')
or (schemaname = 'storage' and tablename = 'objects' and policyname like 'citizen_reports_%')
order by tablename, policyname;