# Design

Rules the generator must follow. Table meanings are in [tables.md](tables.md), renames in [column-mapping.md](column-mapping.md), DDL in `sql/`.

## Scope and honesty

- Fictional operator running since 2020. Not real operational figures.
- Every person, NIK, NIP, bank account and company is generated. IDs use a fake structure and must never pass as real.
- People and company names are Indonesian (locale `id_ID`). All column names, values and messages are English.

## Volume

| Entity | Rows |
|---|---|
| tickets | 1,000,000 |
| group bookings (10 to 80 passengers) | 20,000 to 30,000 |
| bank statement lines | 40,000 to 60,000 |
| customers | 150,000 to 250,000 |
| frequent cards | 30,000 to 50,000 |
| employees | 300 to 500 |

## Demand model

```
daily volume per route = baseline x yearly trend x seasonality x event effect x noise
```

Daily counts are drawn first (negative binomial around the mean), then expanded into bookings and ticket rows. This keeps the series realistic and the totals exact.

| Factor | Rule |
|---|---|
| Yearly trend | Slow growth after the COVID recovery |
| Weekly | Friday to Sunday higher |
| COVID phases | `pre` until Feb 2020; `lockdown` Mar to Dec 2020 (about 10 to 20 percent of baseline); `restrictions` Jan to Sep 2021 with near zero during the 2021 mudik ban and Delta wave (Jul 2021); `recovery` Oct 2021 to Dec 2022; `normal` from 2023 |
| Lebaran | Peak in H-7 to H+7. Dates: 2020-05-24, 2021-05-13, 2022-05-02, 2023-04-22, 2024-04-10, 2025-03-31 |
| Christmas and New Year | Peak from 20 Dec to 3 Jan |
| School holidays | Moderate rise, stronger for school groups |
| Noise | Multiplicative, so peaks never repeat identically |

## Pricing and discount

```
total_price = base_price - discount_amount + tax_amount     (tax on the discounted price)
```

- `base_price` depends on route, seat class and a small crowd uplift in peak windows.
- Discount percent combines three parts and is capped:
  1. **Demand part:** crowded days get small discounts, quiet days get large ones.
  2. **Group tier:** larger groups get more (10 to 19: low, 20 to 49: medium, 50 and above: high).
  3. **Promo:** one anniversary week per year (fictional company, date chosen freely and different each year), plus seasonal campaigns in low periods.
- Tickets bought with a frequent card carry a loyalty promo.
- Every campaign used is a row in `promo`, so each discount can be explained.

## Employees and ticket issuing

- About 300 to 500 employees across five departments and 15 positions. Staff are hired and leave between 2019 and 2025, with more staff at the busy stations (Halim, Tegalluar).
- Each employee has a `nip`, a home station and a supervisor (self-reference up to the manager level).
- Sales channels decide who issues a ticket:

| Channel | `issued_by_employee_id` | `issue_station_id` |
|---|---|---|
| counter, group desk, FCC desk (staffed) | required | the employee's station |
| agent portal, app, website (self service) | NULL | NULL |

- Group bookings get `created_by_employee_id` (sales staff) and, once classified, `verified_by_employee_id` (finance verification staff).
- Cards get `registered_by_employee_id`, and each redemption gets `redeemed_by_employee_id`.

## Customers

| Segment | Behaviour |
|---|---|
| `commuter` | Travels often, usually on one route, holds a frequent card and re-registers after expiry or empty quota |
| `occasional` | A few trips per year, tends to travel in peak periods |
| `one_time` | One trip, for example an event or a group tour |

Churn is built by letting some commuters stop travelling.

## Frequent card rules

- Type G: quota 10, 60 days. Type S: quota 6, 30 days.
- A redemption is valid only while quota remains and the card is not expired. `remaining_quota` never goes below 0.
- The card route matches the route of its redeemed tickets.
- `fcc_redemption.order_id` equals the ticket `order_id`.

## Group booking and payments

- A booking has one company, one route, a document date, and one or more departure dates.
- The sum of its ticket prices equals `total_amount`; `discount_amount` is the sum of ticket discounts.
- Payment pattern per booking: single full transfer, deposit plus final payment, or instalments.
- Statement messages mention the booking number or company name. Some are abbreviated or typo prone.
- Payment lag follows the company type. Some companies pay late consistently.

## Anomalies (about 1 to 3 percent, labelled in `anomaly_label`)

| Type | What is injected |
|---|---|
| `underpayment` | Paid total smaller than the booking total |
| `overpayment` | Paid total larger than the booking total |
| `duplicate_payment` | Same transfer twice |
| `name_mismatch` | Sender name does not match the company |
| `duplicate_ticket` | Same passenger and departure twice |
| `date_outlier` | Purchase very close to departure with a large discount |
| `inactive_issuer` | Ticket issued by an employee outside the employment dates (rare, labelled) |

## Validation checks the generator must pass

1. Ticket rows equal the target count and all dates fall in 2020 to 2025.
2. `total_price = base_price - discount_amount + tax_amount` for every ticket (also a DB check).
3. For every non-anomalous booking: ticket prices sum to `total_amount`, and paid amount equals `total_amount`.
4. No card exceeds its quota or is redeemed after expiry.
5. Daily volume shows the expected shape: low in 2020 and 2021, peaks in Lebaran and year-end windows.
6. Average discount is lower in peak windows than in quiet windows.
7. Staffed-channel tickets have an issuing employee who was employed on the purchase date and works at the issue station; self-service tickets have none (except labelled anomalies).
8. A fixed seed gives the same output twice.

## Load plan

1. Generate CSV per table into `output/` (ignored by git).
2. Run `sql/01_oltp.sql` and `sql/03_reference_data.sql`, then load the remaining OLTP tables in dependency order: employee, company, customer, fcc_card, group_booking and detail, ticket_sales, fcc_redemption, bank_statement, group_booking_payment, anomaly_label.
3. Run `sql/02_dwh.sql`, then build dimensions and facts from OLTP.
4. Refresh the materialized views.
5. Final target: shared PostgreSQL server, schemas `oltp` and `dwh`.
