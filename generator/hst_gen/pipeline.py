"""Runs the stages in order. Each stage is deterministic, so later stages rebuild earlier ones in memory."""
from pathlib import Path

import pandas as pd

from .companies import build_companies
from .demand import build_demand
from .people import build_employees
from .promos import build_promos
from .trips import build_trips


def run_stage2(cfg: dict, seed: int | None = None) -> dict:
    seed = cfg["seed"] if seed is None else seed
    long, cal, shares = build_demand(cfg, seed)
    employee, history, emp_stats = build_employees(cfg, seed)
    company, company_hidden = build_companies(cfg, seed)
    promo = build_promos(cfg, seed, cal, long)
    trips = build_trips(cfg, seed, cal, long)
    return {"long": long, "cal": cal, "shares": shares, "employee": employee, "employee_history": history,
            "emp_stats": emp_stats, "company": company, "company_hidden": company_hidden,
            "promo": promo, "trip": trips}


def export_tables(tables: dict, out: Path, names: list[str]):
    """Write schema CSVs (columns starting with _ are hidden helpers and go to hidden/)."""
    out = Path(out)
    (out / "hidden").mkdir(parents=True, exist_ok=True)
    for name in names:
        df: pd.DataFrame = tables[name]
        visible = [c for c in df.columns if not c.startswith("_")]
        df[visible].to_csv(out / f"{name}.csv", index=False)
        hidden = [c for c in df.columns if c.startswith("_")]
        if hidden:
            df[["id"] + hidden].to_csv(out / "hidden" / f"{name}_hidden.csv", index=False)
    tables["company_hidden"].to_csv(out / "hidden" / "company_hidden.csv", index=False)
