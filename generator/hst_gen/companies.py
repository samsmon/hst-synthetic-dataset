"""Stage 2b: fictional companies that book group trips."""
from datetime import timedelta

import numpy as np
import pandas as pd

from . import rng as rnglib
from .names import CITIES, company_name


def build_companies(cfg: dict, seed: int):
    """Returns (company, company_hidden). The hidden table holds booking activity and payment habits."""
    rng = rnglib.stream(seed, "people.companies")
    c = cfg["companies"]
    n = c["count"]
    kinds = list(c["type_share"])
    kind = rng.choice(kinds, size=n, p=np.array(list(c["type_share"].values())))
    cities, cw = list(CITIES), np.array(list(CITIES.values()))
    city = rng.choice(cities, size=n, p=cw / cw.sum())

    start, end = (pd.Timestamp(d).date() for d in c["joined_range"])
    frac = rng.beta(1.2, 2.0, size=n)                 # more companies join early
    joined = [start + timedelta(days=int(f * (end - start).days)) for f in frac]

    names, seen = [], set()
    for k, ct in zip(kind, city):
        name = company_name(rng, k, ct)
        base, suffix = name, 2
        while name in seen:
            name = f"{base} {suffix}"
            suffix += 1
        seen.add(name)
        names.append(name)

    order = np.argsort(joined, kind="stable")
    company = pd.DataFrame({
        "id": np.arange(1, n + 1), "company_code": [f"C{i:05d}" for i in range(1, n + 1)],
        "name": np.array(names)[order], "type": kind[order], "city": city[order],
        "joined_date": np.array(joined, dtype=object)[order],
    })
    base_late = np.array([c["late_probability"][k] for k in company["type"]])
    hidden = pd.DataFrame({
        "company_id": company["id"],
        "activity_weight": rng.lognormal(0.0, c["activity_sigma"], size=n),
        "late_probability": np.clip(base_late + rng.normal(0, 0.08, size=n), 0.02, 0.85),
        "mean_pay_lag_days": np.array([c["mean_pay_lag_days"][k] for k in company["type"]]) * rng.uniform(0.6, 1.5, size=n),
    })
    return company, hidden
