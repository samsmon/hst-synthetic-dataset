# Design

Rules the generator must follow. Table meanings are in [tables.md](tables.md), DDL is in `sql/`.

## Scope and honesty

- Fictional operator running since 2020. Not real operational figures.
- Every name, NIK, bank account and company is generated. NIKs use a fake structure and must never pass as real IDs.

## Volume

| Entity | Rows |
|---|---|
| tickets | 1,000,000 |
| BAK (groups of 10 to 80 passengers) | 20,000 to 30,000 |
| bank statement lines | 40,000 to 60,000 |
| customers | 150,000 to 250,000 |
| frequent cards | 30,000 to 50,000 |

## Demand model

```
daily volume per route = baseline x yearly trend x seasonality x event effect x noise
```

Daily counts are drawn first (negative binomial around the mean), then expanded into BAK groups and ticket rows. This keeps the series realistic and the totals exact.

| Factor | Rule |
|---|---|
| Yearly trend | Slow growth after the COVID recovery |
| Weekly | Friday to Sunday higher |
| COVID phases | `pre` until Feb 2020; `lockdown` Mar 2020 to Dec 2020 (about 10 to 20 percent of baseline); `ppkm` Jan to Sep 2021 with near zero during the 2021 mudik ban and Delta wave (Jul 2021); `recovery` Oct 2021 to Dec 2022; `normal` from 2023 |
| Lebaran | Peak in H-7 to H+7. Dates: 2020-05-24, 2021-05-13, 2022-05-02, 2023-04-22, 2024-04-10, 2025-03-31 |
| Christmas and New Year | Peak from 20 Dec to 3 Jan |
| School holidays | Moderate rise, stronger for school groups |
| Noise | Multiplicative, so peaks never repeat identically |

## Pricing and discount

```
net = base_price - discount_amount + tax        (tax is a percent of the discounted price)
```

- `base_price` depends on route, seat class and a small crowd uplift in peak windows.
- Discount percent combines three parts and is capped:
  1. **Demand part:** crowded days get small discounts, quiet days get large ones.
  2. **Group tier:** larger groups get more (for example 10 to 19: low, 20 to 49: medium, 50 and above: high).
  3. **Promo:** one anniversary week per year (a fictional company, date chosen freely and different each year), plus seasonal campaigns in low periods.
- Tickets bought with a frequent card carry a loyalty promo.
- `promo` rows record every campaign used so each discount can be explained.

## Customers

| Segment | Behaviour |
|---|---|
| `komuter` | Travels often, usually on one route, holds a frequent card and re-registers after expiry or empty quota |
| `sesekali` | A few trips per year, tends to travel in peak periods |
| `sekali` | One trip, for example an event or a group tour |

Segments are fixed per person for the base data. Churn is built by letting some commuters stop travelling.

## Frequent card rules

- Type G: quota 10, 60 days. Type S: quota 6, 30 days.
- A redeem is valid only while quota remains and the card is not expired. `kuota` never goes below 0.
- Route code of the card (`01`, `02`, `03`) matches the ticket route of its redeems.
- `fcc_redeem.id_pesanan` equals the ticket `order_no`.

## Group booking and payments

- A BAK has one company, one route, a document date, and one or more departure dates.
- The sum of its ticket prices equals `total_nilai`. `total_diskon` is the sum of ticket discounts.
- Payment pattern per BAK: single full transfer, or deposit plus final payment, or instalments.
- Statement messages mention the BAK number or company name. Some are abbreviated or typo prone.
- Payment lag follows the company type. Some companies pay late consistently.

## Anomalies (about 1 to 3 percent, labelled in `label_anomali`)

| Kind | What is injected |
|---|---|
| `underpayment` | Paid total smaller than the BAK total |
| `overpayment` | Paid total larger than the BAK total |
| `duplicate_payment` | Same transfer twice |
| `name_mismatch` | Sender name does not match the company |
| `duplicate_ticket` | Same passenger and departure twice |
| `date_outlier` | Purchase very close to departure with a large discount |

## Validation checks the generator must pass

1. Ticket rows equal the target count and all dates fall in 2020 to 2025.
2. `after_tax_price = base_price - discount_amount + tax` for every ticket (also a DB check).
3. For every non-anomalous BAK: sum of ticket prices equals `total_nilai`, and paid amount equals `total_nilai`.
4. No card exceeds its quota or is redeemed after expiry.
5. Daily volume shows the expected shape: low in 2020 and 2021, peaks in Lebaran and year-end windows.
6. Average discount is lower in peak windows than in quiet windows.
7. A fixed seed gives the same output twice.

## Load plan

1. Generate CSV per table into `output/` (ignored by git).
2. Run `sql/01_oltp.sql`, then load OLTP tables in dependency order.
3. Run `sql/02_dwh.sql`, then build dimensions and facts from OLTP.
4. Refresh `mv_daily_route_demand`.
5. Final target: shared PostgreSQL server, schemas `oltp` and `dwh`.
