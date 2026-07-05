-- 標準作業辞書シードの投入
-- 前提: 0001_init.sql 適用済み。task_types_seed.csv が同梱。
--
-- 使い方 (psql):
--   \cd docs/sodat/schema
--   psql "$DATABASE_URL" -f load_seed.sql
--
-- process 列は CSV では ';' 区切り文字列。staging 経由で text[] に変換して投入する。

begin;
set search_path = sodat, public;

create temporary table _seed_staging (
  task_type_id       text,
  base               text,
  task_name          text,
  crop               text,
  process            text,   -- ';' 区切りの生文字列
  spot_aptitude      text,
  qualification_note text
) on commit drop;

-- CSV を staging へ (パスは実行ディレクトリからの相対)
\copy _seed_staging from '../task_types_seed.csv' with (format csv, header true)

insert into task_types
  (task_type_id, base, task_name, crop, process, spot_aptitude, qualification_note)
select
  task_type_id,
  base,
  task_name,
  crop,
  case when coalesce(process,'') = '' then '{}'::text[]
       else string_to_array(process, ';') end,
  spot_aptitude,
  coalesce(qualification_note,'')
from _seed_staging
on conflict (task_type_id) do update set
  base               = excluded.base,
  task_name          = excluded.task_name,
  crop               = excluded.crop,
  process            = excluded.process,
  spot_aptitude      = excluded.spot_aptitude,
  qualification_note = excluded.qualification_note;

-- 投入確認
do $$
declare n int;
begin
  select count(*) into n from task_types;
  raise notice 'task_types rows: %', n;   -- 期待値: 65
end $$;

commit;
