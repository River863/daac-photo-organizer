create extension if not exists pgcrypto;

create table if not exists public.photo_batches (
  id uuid primary key default gen_random_uuid(),
  event_name text,
  suggested_category text not null check (suggested_category in ('Open Houses','Community Events','Environmental & Community Projects','Outreach & Partnerships','Social Media','Other / Needs Sorting')),
  approved_category text check (approved_category in ('Open Houses','Community Events','Environmental & Community Projects','Outreach & Partnerships','Social Media','Other / Needs Sorting')),
  notes text,
  uploader_name text,
  uploader_email text,
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  created_at timestamptz not null default now(),
  reviewed_at timestamptz
);

create table if not exists public.photos (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references public.photo_batches(id) on delete cascade,
  storage_path text not null unique,
  original_name text not null,
  mime_type text,
  file_size bigint,
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  gallery_visible boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists photo_batches_status_created_idx on public.photo_batches(status, created_at desc);
create index if not exists photos_batch_idx on public.photos(batch_id);
create index if not exists photos_gallery_idx on public.photos(gallery_visible, created_at desc);
alter table public.photo_batches enable row level security;
alter table public.photos enable row level security;
revoke all on public.photo_batches from anon, authenticated;
revoke all on public.photos from anon, authenticated;

insert into storage.buckets (id,name,public,file_size_limit,allowed_mime_types)
values ('daac-photos','daac-photos',true,26214400,array['image/jpeg','image/png','image/webp','image/heic','image/heif'])
on conflict (id) do update set public=excluded.public,file_size_limit=excluded.file_size_limit,allowed_mime_types=excluded.allowed_mime_types;

drop policy if exists "public approved gallery photos" on storage.objects;
create policy "public approved gallery photos" on storage.objects for select to anon, authenticated
using (bucket_id='daac-photos' and (storage.foldername(name))[1]='approved');

