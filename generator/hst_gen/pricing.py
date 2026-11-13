"""Fares, discounts and money rounding for stage 3 (all functions work on arrays)."""
import numpy as np

CLASS_INDEX = {"economy": 0, "premium": 1, "business": 2, "first": 3}


def fare_lookup(fares, route: np.ndarray, cls: np.ndarray, dates: np.ndarray):
    """Fare id and base price for route ids, seat classes (strings) and sale dates (datetime64[D])."""
    fid = np.zeros(len(route), dtype=np.int64)
    price = np.zeros(len(route), dtype=np.int64)
    for (r, c), g in fares.groupby(["route_id", "seat_class"]):
        m = (route == r) & (cls == c)
        if not m.any():
            continue
        g = g.sort_values("valid_from")
        starts = g["valid_from"].to_numpy().astype("datetime64[D]")
        pos = np.clip(np.searchsorted(starts, dates[m], side="right") - 1, 0, len(g) - 1)
        fid[m] = g["id"].to_numpy()[pos]
        price[m] = g["base_price"].to_numpy()[pos]
    return fid, price


def demand_discount_pct(load: np.ndarray, cfg: dict) -> np.ndarray:
    d = cfg["stage3"]["pricing"]["demand_discount"]
    return np.clip((d["reference_load"] - load) * d["pct_per_load_point"], 0.0, d["max_pct"])


def peak_uplift(load: np.ndarray, cfg: dict) -> np.ndarray:
    u = cfg["stage3"]["pricing"]["peak_uplift"]
    return np.clip((load - u["from_load"]) / (u["full_at_load"] - u["from_load"]), 0.0, 1.0) * u["max"]


def step_discount(values: np.ndarray, steps) -> np.ndarray:
    """steps = [[threshold, pct], ...]: the pct of the highest threshold the value reaches, else 0."""
    out = np.zeros(len(values))
    for threshold, pct in sorted(steps):
        out = np.where(values >= threshold, pct, out)
    return out


def round_price(x: np.ndarray, unit: int = 1000) -> np.ndarray:
    return (np.round(x / unit) * unit).astype(np.int64)


def discount_amount(base: np.ndarray, pct: np.ndarray) -> np.ndarray:
    return (np.round(base * pct / 100.0 / 100.0) * 100).astype(np.int64)
