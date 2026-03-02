# Connector Interface Specification

Detta kontrakt standardiserar hur nya källor (Shopify, WooCommerce, CSV, REST, GraphQL) ansluts till plattformen.

## Connector livscykel

1. `validateConfig`: verifiera att anslutning kan göras.
2. `pullProducts`: hämta produkter (grunddata).
3. `pullPrices`: hämta pris/lager/frakt (snapshot-data).
4. `pushPrices` (valfritt): skriv tillbaka pris till extern kanal.
5. `health`: snabb status för övervakning.

## Krav

- Idempotens: samma externa rekord ska inte skapa dubbletter.
- Incremental sync: stöd `since`-timestamp.
- Tydlig felklassning: `auth`, `rate_limit`, `temporary`, `fatal`.
- Normalisering: connector returnerar canonical fields enligt nedan.

## Canonical modeller

```ts
export type Currency = "SEK" | "EUR" | "USD" | string;

export interface CanonicalProduct {
  externalId: string;
  sku?: string;
  ean?: string;
  name: string;
  category?: string;
  cost?: number;
  currency?: Currency;
  attributes?: Record<string, unknown>;
}

export interface CanonicalPriceSnapshot {
  externalProductId: string;
  competitorName?: string;
  price: number;
  shipping?: number;
  inStock?: boolean;
  promoText?: string;
  currency: Currency;
  capturedAt: string; // ISO-8601
}
```

## Interface

```ts
export interface ConnectorConfig {
  sourceId: string;
  name: string;
  type: "shopify" | "woocommerce" | "csv" | "rest" | "graphql";
  baseUrl?: string;
  credentialsRef?: string; // resolves secret outside connector
  settings?: Record<string, unknown>;
}

export interface PullContext {
  runId: string;
  mode: "full" | "incremental";
  since?: string; // ISO-8601
  pageSize?: number;
}

export interface PullResult<T> {
  records: T[];
  nextCursor?: string;
  stats: {
    fetched: number;
    accepted: number;
    rejected: number;
  };
}

export interface PushPriceCommand {
  externalProductId: string;
  newPrice: number;
  currency: string;
  reason: string;
}

export interface PushResult {
  externalProductId: string;
  status: "applied" | "skipped" | "failed";
  message?: string;
}

export type ConnectorErrorCode = "auth" | "rate_limit" | "temporary" | "fatal";

export class ConnectorError extends Error {
  constructor(
    message: string,
    public code: ConnectorErrorCode,
    public retryAfterSeconds?: number
  ) {
    super(message);
  }
}

export interface SourceConnector {
  readonly type: ConnectorConfig["type"];

  validateConfig(config: ConnectorConfig): Promise<void>;
  health(config: ConnectorConfig): Promise<{ ok: boolean; details?: string }>;

  pullProducts(
    config: ConnectorConfig,
    ctx: PullContext,
    cursor?: string
  ): Promise<PullResult<CanonicalProduct>>;

  pullPrices(
    config: ConnectorConfig,
    ctx: PullContext,
    cursor?: string
  ): Promise<PullResult<CanonicalPriceSnapshot>>;

  pushPrices?(
    config: ConnectorConfig,
    commands: PushPriceCommand[]
  ): Promise<PushResult[]>;
}
```

## Runtime-kontrakt i plattformen

1. Worker skapar `source_sync_runs` med status `running`.
2. Connector kör pull i pages/cursors och skriver till `source_records`.
3. Normalizer mappar till `products` och `competitor_prices`.
4. Vid fel:
   - `auth`/`fatal` => markera run `failed`, pausa source vid policy.
   - `temporary`/`rate_limit` => retry med backoff.
5. Slutför med `status=success` och stats.

## Minsta testkrav per connector

1. `validateConfig` failar på trasig credential.
2. Full sync + incremental sync med `since`.
3. Dedupe av samma `externalId`.
4. Rate limit-fel returnerar `ConnectorError(code="rate_limit")`.
5. Mapping test: minst ett fixture-record till canonical format.

