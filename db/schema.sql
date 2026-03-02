-- Core schema for priskontroll platform (PostgreSQL 15+)
create extension if not exists pgcrypto;

create table if not exists products (
  id uuid primary key default gen_random_uuid(),
  sku text not null unique,
  ean text,
  name text not null,
  category text,
  cost numeric(12,2),
  current_price numeric(12,2) not null check (current_price >= 0),
  currency char(3) not null default 'SEK',
  min_price numeric(12,2) not null check (min_price >= 0),
  max_price numeric(12,2) not null check (max_price >= min_price),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists competitors (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  domain text,
  marketplace text,
  created_at timestamptz not null default now()
);

create table if not exists reseller_targets (
  id uuid primary key default gen_random_uuid(),
  competitor_id uuid references competitors(id) on delete set null,
  name text not null,
  country_code char(2) not null,
  priority_rank integer not null check (priority_rank > 0),
  annual_revenue numeric(14,2),
  revenue_change_pct numeric(8,2),
  strategy text not null check (strategy in ('direct_scrape','search_then_scrape','feed','manual')),
  domain text,
  search_queries jsonb not null default '[]'::jsonb,
  crawl_frequency_minutes integer not null default 360 check (crawl_frequency_minutes > 0),
  enabled boolean not null default true,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (name, country_code)
);

create table if not exists product_matches (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  competitor_id uuid not null references competitors(id) on delete cascade,
  competitor_sku text,
  competitor_ean text,
  competitor_url text,
  confidence numeric(4,3) check (confidence >= 0 and confidence <= 1),
  match_source text not null default 'manual', -- manual|ean|sku|fuzzy
  active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (product_id, competitor_id, competitor_sku)
);

create table if not exists source_connections (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  source_type text not null check (source_type in ('shopify','woocommerce','csv','rest','graphql')),
  base_url text,
  auth_secret_ref text, -- reference to secret storage key
  status text not null default 'active' check (status in ('active','paused','error')),
  settings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists source_sync_runs (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references source_connections(id) on delete cascade,
  mode text not null default 'incremental' check (mode in ('full','incremental')),
  status text not null check (status in ('running','success','failed')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  stats jsonb not null default '{}'::jsonb,
  error_message text
);

create table if not exists offer_capture_runs (
  id uuid primary key default gen_random_uuid(),
  reseller_target_id uuid not null references reseller_targets(id) on delete cascade,
  source_id uuid references source_connections(id) on delete set null,
  mode text not null default 'incremental' check (mode in ('full','incremental')),
  status text not null check (status in ('running','success','failed')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  discovered_urls integer not null default 0,
  offers_found integer not null default 0,
  stats jsonb not null default '{}'::jsonb,
  error_message text
);

create table if not exists source_records (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references source_connections(id) on delete cascade,
  external_id text not null,
  record_type text not null, -- product|price|inventory
  payload jsonb not null,
  ingested_at timestamptz not null default now(),
  unique (source_id, external_id, record_type)
);

create table if not exists competitor_prices (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  competitor_id uuid not null references competitors(id) on delete cascade,
  source_id uuid references source_connections(id) on delete set null,
  price numeric(12,2) not null check (price >= 0),
  shipping numeric(12,2) not null default 0 check (shipping >= 0),
  in_stock boolean not null default true,
  promo_text text,
  currency char(3) not null default 'SEK',
  captured_at timestamptz not null default now()
);

create table if not exists rrp_policies (
  id uuid primary key default gen_random_uuid(),
  brand text not null,
  market text not null, -- e.g. SE, NO, DK
  currency char(3) not null default 'SEK',
  min_price numeric(12,2) not null check (min_price >= 0),
  advisory_price numeric(12,2),
  valid_from timestamptz not null default now(),
  valid_to timestamptz,
  status text not null default 'active' check (status in ('active','expired','draft')),
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (valid_to is null or valid_to > valid_from)
);

create table if not exists reseller_offers (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  competitor_id uuid not null references competitors(id) on delete cascade,
  source_id uuid references source_connections(id) on delete set null,
  market text not null, -- e.g. SE, NO, DK
  base_price numeric(12,2) check (base_price is null or base_price >= 0),
  sale_price numeric(12,2) check (sale_price is null or sale_price >= 0),
  shipping_price numeric(12,2) not null default 0 check (shipping_price >= 0),
  effective_price numeric(12,2) not null check (effective_price >= 0),
  currency char(3) not null default 'SEK',
  in_stock boolean not null default true,
  promo_type text check (promo_type in ('none','campaign','coupon','bundle','clearance')),
  promo_text text,
  offer_url text,
  captured_at timestamptz not null default now()
);

create table if not exists pricing_rules (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  strategy text not null check (strategy in ('match_lowest','second_lowest','cost_plus','fixed','margin_guard')),
  scope jsonb not null default '{}'::jsonb,
  config jsonb not null default '{}'::jsonb,
  priority integer not null default 100,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists price_decisions (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  rule_id uuid not null references pricing_rules(id) on delete cascade,
  old_price numeric(12,2) not null,
  suggested_price numeric(12,2) not null,
  reason text not null,
  status text not null check (status in ('proposed','approved','rejected','applied')),
  created_at timestamptz not null default now(),
  approved_by text,
  approved_at timestamptz,
  applied_at timestamptz
);

create table if not exists price_history (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  decision_id uuid references price_decisions(id) on delete set null,
  old_price numeric(12,2) not null,
  new_price numeric(12,2) not null,
  reason text not null,
  changed_by text not null default 'system',
  changed_at timestamptz not null default now()
);

create table if not exists alerts (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  condition_type text not null check (condition_type in ('competitor_drop_pct','below_floor','sync_failed','large_price_change')),
  threshold numeric(12,4),
  channel text not null check (channel in ('email','slack','webhook')),
  target text not null,
  scope jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists compliance_events (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references products(id) on delete cascade,
  competitor_id uuid not null references competitors(id) on delete cascade,
  offer_id uuid references reseller_offers(id) on delete set null,
  policy_id uuid references rrp_policies(id) on delete set null,
  event_type text not null check (event_type in ('below_map','below_rrp','recovered','unverified')),
  severity text not null check (severity in ('p1','p2','p3')),
  status text not null default 'open' check (status in ('open','in_review','resolved','dismissed')),
  observed_price numeric(12,2) not null check (observed_price >= 0),
  threshold_price numeric(12,2) not null check (threshold_price >= 0),
  deviation_amount numeric(12,2) not null,
  deviation_pct numeric(12,4) not null,
  evidence jsonb not null default '{}'::jsonb, -- url/hash/screenshot ref
  detected_at timestamptz not null default now(),
  resolved_at timestamptz
);

create table if not exists alert_events (
  id uuid primary key default gen_random_uuid(),
  alert_id uuid not null references alerts(id) on delete cascade,
  event_key text not null,
  payload jsonb not null,
  triggered_at timestamptz not null default now(),
  delivered_at timestamptz,
  delivery_status text check (delivery_status in ('pending','sent','failed')),
  unique (alert_id, event_key)
);

create table if not exists cases (
  id uuid primary key default gen_random_uuid(),
  compliance_event_id uuid references compliance_events(id) on delete set null,
  status text not null default 'open' check (status in ('open','contacted','pending_reply','resolved','closed')),
  priority text not null default 'normal' check (priority in ('low','normal','high','critical')),
  owner text,
  contacted_at timestamptz,
  closed_at timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_competitor_prices_product_captured
  on competitor_prices (product_id, captured_at desc);

create index if not exists idx_reseller_targets_rank_enabled
  on reseller_targets (priority_rank, enabled);

create index if not exists idx_reseller_targets_country
  on reseller_targets (country_code, enabled);

create index if not exists idx_offer_capture_runs_target_started
  on offer_capture_runs (reseller_target_id, started_at desc);

create index if not exists idx_rrp_policies_brand_market_status
  on rrp_policies (brand, market, status);

create index if not exists idx_reseller_offers_product_captured
  on reseller_offers (product_id, captured_at desc);

create index if not exists idx_reseller_offers_competitor_captured
  on reseller_offers (competitor_id, captured_at desc);

create index if not exists idx_price_history_product_changed
  on price_history (product_id, changed_at desc);

create index if not exists idx_source_sync_runs_source_started
  on source_sync_runs (source_id, started_at desc);

create index if not exists idx_price_decisions_status_created
  on price_decisions (status, created_at desc);

create index if not exists idx_product_matches_product_active
  on product_matches (product_id, active);

create index if not exists idx_compliance_events_status_detected
  on compliance_events (status, detected_at desc);

create index if not exists idx_compliance_events_product_detected
  on compliance_events (product_id, detected_at desc);

create index if not exists idx_cases_status_priority
  on cases (status, priority, created_at desc);
