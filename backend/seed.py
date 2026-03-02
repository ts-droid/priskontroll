import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.db import engine


def seed_data() -> None:
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                create table if not exists internal_customers (
                  id text primary key,
                  external_id text not null unique,
                  name text not null,
                  country_code text not null,
                  created_at timestamp not null default current_timestamp,
                  updated_at timestamp not null default current_timestamp
                )
                """
            )
        )
        conn.execute(
            text(
                """
                create table if not exists authorized_reseller_domains (
                  id text primary key,
                  customer_id text,
                  customer_external_id text,
                  customer_name text,
                  domain text not null unique,
                  active boolean not null default 1,
                  created_at timestamp not null default current_timestamp,
                  updated_at timestamp not null default current_timestamp
                )
                """
            )
        )

        customers = [
            ("C1", "Proffsmagasinet", "SE", "proffsmagasinet.se"),
            ("C2", "Bygghemma", "SE", "bygghemma.se"),
            ("C3", "Bauhaus", "SE", "bauhaus.se"),
            ("C4", "Jula", "SE", "jula.se"),
            ("C5", "Hornbach", "SE", "hornbach.se"),
        ]
        for ext_id, name, country, domain in customers:
            cid = str(uuid.uuid4())
            conn.execute(
                text(
                    """
                    insert into internal_customers (id, external_id, name, country_code)
                    values (:id, :external_id, :name, :country_code)
                    on conflict(external_id) do update set
                      name = excluded.name,
                      country_code = excluded.country_code,
                      updated_at = current_timestamp
                    """
                ),
                {"id": cid, "external_id": ext_id, "name": name, "country_code": country},
            )
            conn.execute(
                text(
                    """
                    insert into authorized_reseller_domains (id, customer_external_id, customer_name, domain, active, updated_at)
                    values (:id, :customer_external_id, :customer_name, :domain, 1, :updated_at)
                    on conflict(domain) do update set
                      customer_external_id = excluded.customer_external_id,
                      customer_name = excluded.customer_name,
                      active = excluded.active,
                      updated_at = excluded.updated_at
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "customer_external_id": ext_id,
                    "customer_name": name,
                    "domain": domain.lower(),
                    "updated_at": now,
                },
            )

    print("Seed data injected.")


if __name__ == "__main__":
    seed_data()
