# hst-synthetic-dataset

Synthetic ticketing dataset for a fictional high-speed train (HST) operator, built for machine learning and data warehouse / BI practice. All people, companies, bank accounts and IDs are generated. Nothing here is real operational data.

> Status: design done (docs and DDL). Generator not written yet.

## Goals

- About 1,000,000 ticket rows (`ticket_sales`) between 2020 and 2025.
- Demand that follows real-world patterns: COVID collapse and recovery, Lebaran peaks, Christmas and New Year, school holidays, weekends.
- Pricing and discounts that react to demand: crowded periods get small discounts, quiet periods get larger ones, groups get tiered discounts, and one fictional company anniversary promo runs each year.
- Repeat customers (commuters, occasional, one-time) so churn and frequency can be modelled.
- Employees with position, NIP and home station, linked to the tickets they issue, the bookings they handle and the cards they register.
- Two layers: an operational schema (OLTP) and a star schema (DWH), both for PostgreSQL.
- Everything is in English (tables, columns, values, messages). Only generated person and company names are Indonesian.

The timeline is fictional: the operator is assumed to run since 2020. Do not present the data as real figures of any actual railway.

## Source schemas

The operational layer extends two existing Laravel apps. Source-to-new names are in [docs/column-mapping.md](docs/column-mapping.md).

| Source | Tables | Role |
|---|---|---|
| group-ticket verification app | `dokumen_bak`, `dokumen_bak_detail`, `data_ticketsales`, `dokumen_rekeningkoran` | group bookings, tickets, bank statement |
| frequent card admin app | `maindata` (cards), `subdata` (redemptions) | frequent customer card (FCC) and quota redemption |

New in this dataset: `employee`, `position`, `department`, `station` (richer), `sales_channel`, `company`, `customer`, `promo`, plus the answer-key tables `group_booking_payment` and `anomaly_label`.

## Entity relations

```mermaid
erDiagram
    company ||--o{ group_booking : "books"
    group_booking ||--o{ group_booking_detail : "departure dates"
    group_booking ||--o{ ticket_sales : "group_booking_id"
    group_booking ||--o{ group_booking_payment : "paid by"
    bank_statement ||--o| group_booking_payment : "matched to"
    customer ||--o{ fcc_card : "owns"
    fcc_card ||--o{ fcc_redemption : "card_id"
    fcc_redemption ||--|| ticket_sales : "order_id"
    customer ||--o{ ticket_sales : "travels"
    employee ||--o{ ticket_sales : "issued_by"
    employee ||--o{ group_booking : "created / verified"
    employee ||--o{ fcc_card : "registered_by"
    employee ||--o{ fcc_redemption : "redeemed_by"
    employee }o--|| position : "has"
    position }o--|| department : "in"
    employee }o--o| station : "home station"
    station ||--o{ ticket_sales : "origin / destination / issue"
    sales_channel ||--o{ ticket_sales : "sold via"
    promo ||--o{ ticket_sales : "applied"
    route ||--o{ group_booking : "route"
    route ||--o{ fcc_card : "route"
```

Reading guide: a group booking groups tickets and is paid through one or more bank statement lines. A card redemption produces a ticket with the same `order_id`. Staffed channels record the issuing employee and station; self-service channels leave them empty.

## Frequent card rules (from the source app)

| Type | Quota | Validity |
|---|---|---|
| G | 10 | 60 days |
| S | 6 | 30 days |

Route codes: `01` Jakarta to Bandung, `02` Jakarta to Karawang, `03` Karawang to Bandung. A redemption is only valid while quota remains and the card is not expired.

## Demand model

```
daily volume = baseline x yearly trend x seasonality x event effect x noise
```

Lebaran dates used: 2020-05-24, 2021-05-13, 2022-05-02, 2023-04-22, 2024-04-10, 2025-03-31.

## Planned size

| Entity | Approx. rows |
|---|---|
| tickets | 1,000,000 |
| group bookings | 20,000 to 30,000 |
| bank statement lines | 40,000 to 60,000 |
| customers | 150,000 to 250,000 |
| frequent cards | 30,000 to 50,000 |
| employees | 300 to 500 |

## ML and BI targets

- Daily demand per route.
- Discount amount.
- Customer churn and visit frequency.
- Late or short payment of a group booking.
- Sales workload and performance per employee.
- Injected anomalies (underpayment, duplicates, name mismatch), marked in `anomaly_label`.

## Output

- PostgreSQL DDL and `.sql` load scripts.
- `.csv` per table.
- Target: shared PostgreSQL server, schemas `oltp` and `dwh`.

## Roadmap

1. Design document and PostgreSQL DDL (OLTP and DWH). Done: see [docs/design.md](docs/design.md), [docs/tables.md](docs/tables.md), [docs/column-mapping.md](docs/column-mapping.md) and `sql/`.
2. Python generator with a fixed random seed, so runs are reproducible.
3. Validation checks (quota, expiry, payment totals against booking totals).
4. Load into the shared PostgreSQL server.

## License

MIT, see [LICENSE](LICENSE).
