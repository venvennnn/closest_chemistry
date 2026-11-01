-- Closest Chemistry private bucket and owner-scoped policies.
-- Run in the Supabase SQL editor after creating the project.
-- The API uses the service role and still enforces owner_id in application code.

insert into storage.buckets (id, name, public)
values ('closest-chemistry-private', 'closest-chemistry-private', false)
on conflict (id) do nothing;

-- Frontend never reads the bucket directly; signed access goes through the API.
-- These policies exist so a leaked anon key cannot list other tenants' objects.

create policy "no anon listing"
on storage.objects for select
to anon
using (false);

create policy "no anon writes"
on storage.objects for insert
to anon
with check (false);
