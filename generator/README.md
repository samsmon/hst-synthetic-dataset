# Generator

Builds the synthetic dataset described in `../docs/design.md`. Output goes to `../output/` (ignored by git).

## Setup

```
pip install -r requirements.txt
```

## Run

```
python -m hst_gen all --tickets 1000000 --out ../output   # full end-to-end run (stages 1-5)
python -m hst_gen demand --out ../output          # stage 1
python -m hst_gen stage2 --out ../output          # stage 2 (runs stage 1 first)
python -m hst_gen stage3 --out ../output          # stage 3: tickets, bookings, customers (about 3 minutes for 10.8 million tickets)
python -m hst_gen stage4 --out ../output          # stage 4: FCC cards, refunds, bank statements and payments
python -m hst_gen stage5 --out ../output          # stage 5: anomalies and answer keys
python scripts/load_db.py                        # stage 6: load schema, copy CSVs, run checks
python -m hst_gen demand --seed 7 --tickets 200000   # small run for development
python -m pytest tests -q
```

The total is calibrated so that the mature years 2022 to 2025 average 200,000 tickets per month (about 10.8 million over 2020 to 2025); `--tickets N` fixes a smaller total for development. A fixed seed gives the same output every time. Each module draws from its own random stream (`hst_gen/rng.py`), so changing one module does not shift the numbers of another. All tunable numbers live in `config.yaml`.

## Stages

| # | Stage | Status |
|---|---|---|
| 1 | `daycal.py`, `demand.py`: daily tickets per route, group share per month | done |
| 2 | `people.py`, `companies.py`, `promos.py`, `trips.py`: employees and history, companies, promos, schedule | done |
| 3 | `ctx.py`, `bookings.py`, `customers.py`, `tickets.py`, `pricing.py`, `staff.py`, `stage3.py`: tickets, group bookings, customers, streamed to CSV month by month | done |
| 4 | `fcc.py`, `refunds.py`, `bank.py`, `stage4.py`, `report4.py`: FCC cards and redemptions, ticket status and refunds, bank statement and booking payments | done |
| 5 | `stage5.py`, `anomalies.py`, `report5.py`: anomalies and answer keys | done |
| 6 | `load_db.py`, `validate_db.py`: export, validation, load into PostgreSQL | done |
| 7 | full run of 1,000,000 tickets | done |

## Stage 1 output

- `stage1_demand.csv`: one row per day and route with `tickets`, `group_tickets`, `individual_tickets`.
- `stage1_summary.md`: yearly totals, COVID phases, group share, Lebaran windows, weekday profile.
- `stage1_demand.svg`: tickets per month and group share per month.
