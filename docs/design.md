# Design

Rules the generator must follow. Table meanings are in [tables.md](tables.md), column details in [data-dictionary.md](data-dictionary.md), renames in [column-mapping.md](column-mapping.md), ML task definitions in [ml-targets.md](ml-targets.md), DDL in `sql/`.

## Scope and honesty

- Fictional operator running since 2020, deliberately smaller than any real railway. Not real operational figures.
- Every person, NIK, NIP, bank account and company is generated. Indonesian ID numbers start with `99`, so they never match a real NIK (enforced by a CHECK).
- People and company names are Indonesian (locale `id_ID`). All column names, values and messages are English.

## Volume

| Entity | Rows |
|---|---|
| tickets (`ticket_sales`, all channels) | about 10.8 million. 2022 to 2025 average 200,000 per month (months between 150,000 and 235,000); 2020 and 2021 are far lower (about 36,000 and 63,000 per month) because of COVID and the opening |
| group tickets | 15 to 35 percent of tickets per month, about 2.7 million in total |
| group bookings (20 to 100 passengers) | 55,000 to 85,000 |
| trips | 35,000 to 55,000 |
| bank statement lines | 120,000 to 250,000 |
| customers | 1,200,000 to 2,400,000 |
| frequent cards | 250,000 to 450,000 |
| employees | 400 to 600 over the period (about 420 active at the end of 2025) |

## Group share and group size

- For every month draw a group share from a uniform 15 to 35 percent. That month's group tickets are the share times the month's ticket total; the rest are individual tickets (counter, FCC, agent, app, website).
- A group booking has at least 20 passengers. Sizes are skewed: most 20 to 40, a tail up to 100 for schools and corporates.
- Group tickets are packed into bookings until the month's group total is reached.

## Demand model

```
daily volume per route = baseline x yearly trend x seasonality x event effect x noise
```

Daily counts are drawn first (negative binomial around the mean), then split into group and individual tickets and expanded into rows.

| Factor | Rule |
|---|---|
| Yearly trend | Slow growth (2 percent a year) from 2022, once the network is mature |
| Weekly | Friday to Sunday higher |
| COVID phases (table `covid_phase`) | `pre` until Feb 2020; `lockdown` Mar to Dec 2020 (about 10 to 20 percent of baseline); `restrictions` Jan to Sep 2021 with near zero during the 2021 mudik ban and Delta wave (Jul 2021); `recovery` Oct 2021 to Dec 2022 (volume is back to the mature level by April 2022); `normal` from 2023 |
| Lebaran | Peak in H-7 to H+7. Dates in `calendar_event` |
| Christmas and New Year | Peak from 20 Dec to 3 Jan |
| School holidays | Moderate rise, stronger for school groups |
| Noise | Multiplicative, so peaks never repeat identically |

## Trips and capacity

- `trip` rows are scheduled to match demand: more runs in peak days, fewer during lockdown (about 20 to 30 runs a day from 2022). Seat capacity is 300, 450 or 600 per run.
- Target load factor is 40 to 90 percent in normal periods. Demand is capped by capacity, so a sold-out peak day pushes some demand to neighbouring days.
- A ticket belongs to one trip. Its direction must match the order of its stations (Halim towards Tegalluar is `to_bandung`). `departure_date` equals the trip `service_date`.

## Routes, fares and price

- `route_segment` lists the allowed station pairs; a ticket's `route_id` comes from its origin and destination pair (a composite foreign key enforces it). Padalarang to Tegalluar is not sold.
- `fare` holds the base price per route and seat class, with two versions: 2020 to 2022 and from 2023.
- `base_price` is the fare price, plus a peak uplift (up to 15 percent) in crowded windows, rounded to Rp 1,000.
- Tax is not modelled and is assumed to be inside the fare. A small `service_fee_amount` depends on the channel: counter, group desk and FCC desk 0, app and website 2,500, agent portal 5,000.

```
total_price = base_price - discount_amount + service_fee_amount
```

## Discount

Discount percent is capped at 40 and has three parts:

1. **Demand part:** crowded days get small discounts, quiet days get large ones.
2. **Group tier:** 20 to 29 passengers low, 30 to 59 medium, 60 and above high.
3. **Promo:** see below. Promos do not stack; the best of "demand plus tier" and the qualifying promo wins. `promo_id` is set only when the promo wins.

Peak windows (Lebaran, year end) have no monthly deals, so discounts there stay small.

## Promos

Created by the generator, not seeded. Modelled on a real-style offer such as "February Deals: 20 percent off all group trips, minimum 20 passengers".

| Type | Rule |
|---|---|
| `monthly_deal` | 0 to 2 per month (at least one in about 70 percent of months). Name `HST <Month> Deals`. Applies to group (50 percent), all (30 percent) or individual (20 percent). Discount 5 to 30 percent in steps of 5 (group deals 10 to 25). Window 7 to 31 days from a random start. A fifth of deals are limited to one route |
| `anniversary` | One week per year, any date, applies to all, 15 to 25 percent |
| `seasonal` | Extra campaigns in low seasons |
| `loyalty` | Applies to card (FCC) redemptions |
| minimum passengers | Group deals use `min_pax` of 20, 30 or 50, never below 20 (a CHECK enforces it) |

A group booking qualifies when its `document_date` is inside the window, its passenger count reaches `min_pax`, and the route matches when the promo is route-specific. The booking stores `promo_id`, and all its tickets carry the same one.

## Ticket status and refunds

- Statuses: `issued` (future departure), `used` (past, not cancelled), `cancelled`, `refunded`.
- Cancelled about 2 to 4 percent normally. During the 2020 lockdown refunds jump to 15 to 25 percent of tickets bought before March.
- Each refund gets a `refund` row: no fee for `schedule_change`, 25 percent fee for `customer_request`. Refund payouts also show as debit lines in the bank statement.

## Employees and ticket issuing

- About 300 to 500 employees across five departments and 15 positions. Staff are hired and leave between 2019 and 2025, with more staff at the busy stations (Halim, Tegalluar).
- `employee_history` records every promotion and transfer. The `employee` row matches the latest history row.
- Sales channels decide who issues a ticket:

| Channel | `issued_by_employee_id` | `issue_station_id` |
|---|---|---|
| counter, group desk, FCC desk (staffed) | required | the employee's station on that date |
| agent portal, app, website (self service) | NULL | NULL |

- Group bookings get `created_by_employee_id` (sales staff) and, once classified, `verified_by_employee_id` (verification staff).
- Cards get `registered_by_employee_id`, each redemption `redeemed_by_employee_id`, each refund `processed_by_employee_id`.

## Customers

| Segment (generator only, in `oltp_truth.customer_truth`) | Behaviour |
|---|---|
| `commuter` | Travels often, usually on one route, holds a frequent card and re-registers after expiry or empty quota |
| `occasional` | A few trips per year, tends to travel in peak periods |
| `one_time` | One trip, for example an event |

Churn is built by letting some commuters stop travelling; the stop date is stored as `churn_date`. Anyone who needs a segment must derive it from ticket behaviour and never read `customer_truth`.

## Frequent card rules

- Type G: quota 10, 60 days. Type S: quota 6, 30 days.
- A redemption is valid only while quota remains and the card is not expired. `remaining_quota` never goes below 0.
- The ticket route equals the card route.
- `fcc_redemption.order_id` equals the ticket `order_id`. Owner name, ID number and contact are read from `customer`.

## Group booking, classification and payments

- A booking has one company, one route, a document date, a payment due date and one or more departure dates. `period` is the month of the first departure.
- Bookings from the last 60 days of the dataset, plus 1 to 2 percent of older ones, stay `pending`: their tickets show `group_booking_id` NULL. The real link is in `oltp_truth.ticket_group_truth`.
- The sum of a booking's ticket prices equals `total_amount`; `discount_amount` is the sum of ticket discounts.
- Payment pattern per booking: single full transfer, deposit plus final payment, or instalments. One transfer can also pay several bookings of the same company (`oltp_truth.group_booking_payment.allocated_amount`).
- Payment lag follows the company type. Some companies pay late consistently. A booking is late when fully paid after `payment_due_date`.
- Statement messages mention the booking number or company name. Some are abbreviated or misspelled.
- The statement also holds unrelated lines: daily gateway settlement for online sales (`SETTLE`), monthly bank fee (`FEE`) and interest (`INT`), refund payouts (`REFUND`). Balances are a running total per account.

## Anomalies (about 1 to 3 percent, labelled in `oltp_truth.anomaly_label`)

| Type | What is injected |
|---|---|
| `underpayment` | Paid total smaller than the booking total |
| `overpayment` | Paid total larger than the booking total |
| `duplicate_payment` | Same transfer twice |
| `name_mismatch` | Sender name does not match the company |
| `duplicate_ticket` | Same passenger and departure twice |
| `date_outlier` | Purchase very close to departure with a large discount |
| `inactive_issuer` | Ticket issued by an employee outside the employment dates (rare) |

## Validation checks the generator must pass

1. Ticket rows equal the total, the 2022 to 2025 monthly average is within 3 percent of 200,000, and all dates fall in 2020 to 2025.
2. Monthly group share is between 15 and 35 percent, and every booking has at least 20 passengers.
3. `total_price = base_price - discount_amount + service_fee_amount` for every ticket (also a DB check).
4. For every non-anomalous booking: ticket prices sum to `total_amount`, and allocated payments sum to `total_amount`.
5. No card exceeds its quota or is redeemed after expiry; the ticket route equals the card route.
6. Daily volume shows the expected shape: low in 2020 and 2021, peaks in Lebaran and year-end windows.
7. Average discount is lower in peak windows than in quiet windows; no monthly deal overlaps a peak window.
8. Every group promo has `min_pax` of at least 20 and every promoted booking meets it.
9. Tickets per trip never exceed `seat_capacity`, and the trip direction matches the station order.
10. Staffed-channel tickets have an issuing employee who was employed on the purchase date and worked at the issue station; self-service tickets have none (except labelled anomalies).
11. Bank balances are continuous per account, and refunded tickets have a refund row.
12. A fixed seed gives the same output twice.

## Load plan

1. Generate CSV per table into `output/` (ignored by git).
2. Run `sql/01_oltp.sql`, `sql/02_oltp_truth.sql`, `sql/03_reference_data.sql` and `sql/04_comments.sql`.
3. Load the OLTP tables in dependency order: employee, employee_history, company, customer, fcc_card, promo, group_booking and detail, trip, ticket_sales, refund, fcc_redemption, bank_statement.
4. Load the answer keys into `oltp_truth`: customer_truth, ticket_group_truth, group_booking_payment, anomaly_label.
5. Rebuild `docs/data-dictionary.md` with `scripts/build_dictionary.py`.
6. Final target: shared PostgreSQL server, schemas `oltp` and `oltp_truth`. Downstream pipelines read `oltp` only.
