-- SODAT R8 データ基盤 Phase 0: 初期スキーマ
-- 対象: PostgreSQL 14+ / Supabase
-- 設計: docs/sodat-r8-architecture.md（イベントログ中核・タスク中心）
--
-- 3 層構造:
--   第0層 task_types  … 標準作業辞書（マスタ・版管理）
--   第1層 事実ストリーム … 追記専用。2 時刻(event_time / recorded_at)。UPDATE/DELETE しない
--   第2層 派生ビュー   … 第1層から計算。いつでも作り直せる
--
-- 内部モジュール間は直接 API を持たず、すべてこのスキーマ経由で連携する。

begin;

create schema if not exists sodat;
set search_path = sodat, public;

-- ============================================================
-- 第0層: 標準作業辞書（マスタ）
-- ============================================================
-- task_type_id は例外なく `<base>.<crop>`。作目で技能・適性が違うタスクを取り違えないため。
-- 作目をまたぐ技能移転(束ね)は辞書に焼き込まず、マッチング層で base 単位に判定する。

create table task_types (
  task_type_id        text primary key,                 -- 例: teishoku.veg
  base                text not null,                    -- ドット前。束ねキー（ID から導出可能だが明示保持）
  task_name           text not null,                    -- 表示名（辞書の作目慣用表記）
  crop                text not null check (crop in ('veg','fruit','tea','common')),
  process             text[] not null default '{}',     -- 工程（複数値可。例: 圃場巡回は2工程に出現）
  spot_aptitude       text not null check (spot_aptitude in ('◎','○','△','−')),
  qualification_note  text not null default '',
  -- 適性の来歴・客観接地（docs/sodat/aptitude-rubric.md）
  aptitude_basis      text not null default 'skill'
                        check (aptitude_basis in ('danger','qualification','skill','experience','training','routine')),
  danger_category     text not null default ''
                        check (danger_category in ('','machine','height','anoxia','pesticide','livestock')),
  required_qual       text not null default '',          -- 必須資格（マッチングの資格ゲート）
  -- 標準作業時間（②タスク提案の工数・必要人数の客観化）
  std_work_time_min   numeric,                            -- 分/10a・1回当たりの目安。NULL=未接地
  std_work_time_src   text not null default '',           -- 典拠（e-Stat 品目別経営統計 等）
  dictionary_version  text not null default 'r7-2026-03',
  check (task_type_id = base || '.' || crop)
);

create index task_types_base_idx on task_types (base);
create index task_types_crop_idx on task_types (crop);

-- 初期シードの投入は docs/sodat/schema/load_seed.sql を参照
-- (task_types_seed.csv を staging 経由で流し込む)

-- ============================================================
-- 第1層: 事実ストリーム（追記専用 / 2 時刻）
-- ============================================================
-- 規約:
--   event_time   … 事象が実際に起きた時刻（作業実施・観測）
--   recorded_at  … システムに記録された時刻（default now()）
--   これらの表に対する UPDATE / DELETE はガバナンス上禁止（追記のみ）。

-- 作業実績（TPOCast から取り込み）: ① スキル導出の素材
create table work_records (
  id            bigint generated always as identity primary key,
  worker_id     text not null,
  task_type_id  text not null references task_types(task_type_id),
  farm_id       text,
  quantity      numeric,
  quality       text,
  event_time    timestamptz not null,
  recorded_at   timestamptz not null default now(),
  source        text not null default 'tpocast',
  dict_version  text not null default 'r7-2026-03'      -- 分類時の辞書版
);
create index work_records_worker_task_idx on work_records (worker_id, task_type_id);

-- 栽培・育成状況（栽培実証システム / TPOCast）: ② タスク提案の素材
create table cultivation_observations (
  id            bigint generated always as identity primary key,
  farm_id       text not null,
  plot_id       text,
  crop          text not null check (crop in ('veg','fruit','tea')),
  growth_stage  text,
  metrics       jsonb not null default '{}',            -- センサ値・観察値
  event_time    timestamptz not null,
  recorded_at   timestamptz not null default now(),
  source        text not null default 'cultivation'
);
create index cultivation_obs_farm_idx on cultivation_observations (farm_id, event_time);

-- 応募者プロフィール事実（資格・免許など入力事実）
create table worker_profile_events (
  id            bigint generated always as identity primary key,
  worker_id     text not null,
  attribute     text not null,                          -- 例: license.tractor
  value         text,
  valid_until   date,                                   -- 失効日（あれば）
  event_time    timestamptz not null,
  recorded_at   timestamptz not null default now()
);
create index worker_profile_worker_idx on worker_profile_events (worker_id);

-- 応募者の対応可能時間
create table worker_availability (
  id             bigint generated always as identity primary key,
  worker_id      text not null,
  available_from timestamptz not null,
  available_to   timestamptz not null,
  area           text,
  recorded_at    timestamptz not null default now()
);
create index worker_availability_worker_idx on worker_availability (worker_id, available_from);

-- 農家の人材確保リクエスト（需要）
create table task_requests (
  id             bigint generated always as identity primary key,
  farm_id        text not null,
  task_type_id   text not null references task_types(task_type_id),
  timing_from    timestamptz,
  timing_to      timestamptz,
  estimated_effort numeric,                             -- 想定工数
  headcount      int not null default 1,
  status         text not null default 'open'
                   check (status in ('open','matching','filled','cancelled')),
  event_time     timestamptz not null default now(),
  recorded_at    timestamptz not null default now()
);
create index task_requests_task_idx on task_requests (task_type_id, status);

-- マッチング結果・応答（AI Engine が書き、UI が応答を追記）
create table match_results (
  id            bigint generated always as identity primary key,
  request_id    bigint not null references task_requests(id),
  worker_id     text not null,
  score         numeric,
  status        text not null default 'proposed'
                  check (status in ('proposed','accepted','declined','expired')),
  event_time    timestamptz not null default now(),
  recorded_at   timestamptz not null default now()
);
create index match_results_request_idx on match_results (request_id);
create index match_results_worker_idx on match_results (worker_id);

-- ============================================================
-- 第2層: 派生ビュー（第1層から計算。読み取り面）
-- ============================================================

-- ① スキル導出: (worker, task_type) ごとの実績集計。
--    習熟度の閾値ルールは今後具体化するため、現段階は集計値を提示。
create view worker_skills as
select
  worker_id,
  task_type_id,
  count(*)                as work_count,
  sum(coalesce(quantity,0)) as total_quantity,
  max(event_time)         as last_worked_at
from work_records
group by worker_id, task_type_id;

-- 束ね（マッチング時のみ）を SQL で具現化した面:
--   base 単位で作目横断に実績を合算。作目非依存タスク(◎軽作業等)の技能移転に使う。
--   「どの base を束ねてよいか」はマッチング層の判断。ここは素材を提供するだけ。
create view worker_skills_by_base as
select
  w.worker_id,
  t.base,
  count(*)                as work_count,
  count(distinct t.crop)  as crops_covered,
  max(w.event_time)       as last_worked_at
from work_records w
join task_types t on t.task_type_id = w.task_type_id
group by w.worker_id, t.base;

-- 資格・免許の現在状態（失効判定込み）
create view worker_qualifications as
select distinct on (worker_id, attribute)
  worker_id, attribute, value, valid_until, event_time
from worker_profile_events
order by worker_id, attribute, event_time desc;

-- ② タスク提案は cultivation_observations × task_types から AI Engine が生成する。
--    導出ルール(観測→タスク)が未定義のため Phase 0 では出力先テーブルのみ用意する。
create table task_proposals (
  id            bigint generated always as identity primary key,
  farm_id       text not null,
  task_type_id  text not null references task_types(task_type_id),
  proposed_timing_from timestamptz,
  proposed_timing_to   timestamptz,
  estimated_effort     numeric,
  suggested_headcount  int,
  basis         jsonb not null default '{}',            -- 根拠(どの観測から導いたか)
  generated_at  timestamptz not null default now()
);
create index task_proposals_farm_idx on task_proposals (farm_id);

-- ============================================================
-- データガバナンス(4.3.2) の土台メモ
-- ============================================================
-- Supabase では以下を Phase 後半で有効化する:
--   * 各表に Row Level Security を有効化し、所有権(農家/ワーカー)に基づく read/write を定義
--   * 第1層は追記のみ (INSERT 許可、UPDATE/DELETE 拒否) をポリシーで強制
--   * 個人情報を含む worker_* 表はアクセス目的を限定
-- 監査・再現性は 2 時刻 + dict_version により担保される。

commit;
