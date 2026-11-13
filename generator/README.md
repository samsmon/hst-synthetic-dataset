# Generator

Builds the synthetic dataset described in `../docs/design.md`. Output goes to `../output/` (ignored by git).

## Setup

```
pip install -r requirements.txt
```

## Run

```
python -m hst_gen demand --out ../output          # stage 1
python -m hst_gen demand --seed 7 --tickets 200000
python -m pytest tests -q
```

A fixed seed gives the same output every time. Each module draws from its own random stream (`hst_gen/rng.py`), so changing one module does not shift the numbers of another. All tunable numbers live in `config.yaml`.

## Stages

| # | Stage | Status |
|---|---|---|
| 1 | `daycal.py`, `demand.py`: daily tickets per route, group share per month | done |
| 2 | people, promos, trips | planned |
| 3 | tickets and group bookings | planned |
| 4 | FCC cards, refunds, bank statement | planned |
| 5 | anomalies and answer keys | planned |
| 6 | export, validation, load | planned |
| 7 | full run of 1,000,000 tickets | planned |

## Stage 1 output

- `stage1_demand.csv`: one row per day and route with `tickets`, `group_tickets`, `individual_tickets`.
- `stage1_summary.md`: yearly totals, COVID phases, group share, Lebaran windows, weekday profile.
- `stage1_demand.svg`: tickets per month and group share per month.
