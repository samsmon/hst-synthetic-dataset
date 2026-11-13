"""Stage 1: daily ticket demand per route and the group / individual split.

expected tickets = level x trend x weekday x events x shared day shock x route share,
scaled so the expectation matches the target, then drawn from a negative binomial
and adjusted so the total is exactly the target.
"""
import numpy as np
import pandas as pd

from . import rng as rnglib
from .daycal import build_calendar

DOW_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def regime_level(cal: pd.DataFrame, knots) -> np.ndarray:
    """Demand level between the knots, interpolated linearly in log space."""
    kx = np.array([pd.Timestamp(d).as_unit("ns").value for d, _ in knots], dtype="float64")
    ky = np.log(np.array([v for _, v in knots], dtype="float64"))
    dx = cal["date"].values.astype("datetime64[ns]").astype("int64").astype("float64")
    return np.exp(np.interp(dx, kx, ky))


def trend_factor(cal: pd.DataFrame, cfg: dict) -> np.ndarray:
    start = pd.Timestamp(cfg["trend"]["start"])
    years = np.maximum((cal["date"] - start).dt.days.values, 0) / 365.0
    return 1.0 + cfg["trend"]["yearly_growth"] * years


def _bump(x, offset, height, width):
    return height * np.exp(-(((x - offset) / width) ** 2))


def event_multiplier(cal: pd.DataFrame, cfg: dict) -> np.ndarray:
    mult = np.ones(len(cal))
    leb = cfg["lebaran"]
    off = cal["lebaran_offset"].values
    in_win = cal["is_lebaran_window"].values
    safe = np.where(np.isnan(off), 0.0, off)
    bump = (_bump(safe, leb["outbound_peak"]["offset"], leb["outbound_peak"]["height"], leb["outbound_peak"]["width"])
            + _bump(safe, leb["return_peak"]["offset"], leb["return_peak"]["height"], leb["return_peak"]["width"]))
    mult *= np.where(in_win, 1.0 + bump, 1.0)
    mult *= np.where((safe == 0) | (safe == 1), np.where(in_win, leb["holiday_dip"], 1.0), 1.0)

    # Year end: distance in days to each peak, taking the nearest year.
    dates = cal["date"]
    for peak in cfg["year_end"]["peaks"]:
        dist = np.full(len(cal), 99.0)
        for yr in range(dates.dt.year.min() - 1, dates.dt.year.max() + 1):
            center = pd.Timestamp(year=yr, month=peak["month"], day=peak["day"])
            dist = np.minimum(dist, np.abs((dates - center).dt.days.values))
        mult *= 1.0 + np.where(cal["is_year_end"].values, _bump(dist, 0, peak["height"], peak["width"]), 0.0)

    mult *= np.where(cal["is_school_holiday"].values, cfg["school_holiday_factor"], 1.0)
    mult *= np.where(cal["is_public_holiday"].values, cfg["public_holiday_factor"], 1.0)
    mult *= cal["restriction_factor"].values
    return mult


def route_shares(cal: pd.DataFrame, cfg: dict, seed: int) -> np.ndarray:
    """Share of each route per day (rows sum to 1), drifting slowly per month."""
    rng = rnglib.stream(seed, "demand.route")
    base = np.array([cfg["routes"]["base_share"][r] for r in sorted(cfg["routes"]["base_share"])])
    month_ids = np.sort(cal["month_id"].unique())
    drift = np.exp(cfg["routes"]["monthly_drift_sigma"] * rng.standard_normal((len(month_ids), len(base))))
    per_month = base * drift
    per_month /= per_month.sum(axis=1, keepdims=True)
    idx = np.searchsorted(month_ids, cal["month_id"].values)
    return per_month[idx]


def expected_tickets(cal: pd.DataFrame, cfg: dict, seed: int) -> np.ndarray:
    """Expected tickets per day and route, scaled to the target total."""
    weekly = np.array([cfg["weekly"][k] for k in DOW_KEYS])[cal["dow"].values]
    shock_rng = rnglib.stream(seed, "demand.shock")
    shock = np.exp(cfg["noise"]["day_shock_sigma"] * shock_rng.standard_normal(len(cal)))
    day = regime_level(cal, cfg["regime_knots"]) * trend_factor(cal, cfg) * weekly * event_multiplier(cal, cfg) * shock
    mu = day[:, None] * route_shares(cal, cfg, seed)
    return mu * (cfg["target_tickets"] / mu.sum())


def draw_counts(mu: np.ndarray, cfg: dict, seed: int) -> np.ndarray:
    """Negative binomial draw (gamma-Poisson), then adjust to exactly the target total."""
    rng = rnglib.stream(seed, "demand.count")
    size = cfg["noise"]["nb_size"]
    counts = rng.poisson(rng.gamma(size, mu / size)).astype(np.int64)
    diff = int(cfg["target_tickets"] - counts.sum())
    if diff > 0:
        counts += rng.multinomial(diff, (mu / mu.sum()).ravel()).reshape(mu.shape)
    elif diff < 0:
        counts -= rng.multivariate_hypergeometric(counts.ravel(), -diff).reshape(mu.shape)
    return counts


def group_weights(cal: pd.DataFrame, cfg: dict) -> np.ndarray:
    w = cfg["groups"]["weights"]
    out = np.where(cal["is_weekend"].values, w["weekend"], w["weekday"]).astype(float)
    out = np.where(cal["is_school_holiday"].values, w["school_holiday"], out)
    out = np.where(cal["is_lebaran_window"].values, w["lebaran_window"], out)
    out = np.where(cal["is_year_end"].values, w["year_end"], out)
    return out


def split_groups(cal: pd.DataFrame, counts: np.ndarray, cfg: dict, seed: int):
    """Per month draw a group share, then place that many group tickets on the days of the month.

    Returns the group tickets per day and route and the share drawn for each month.
    """
    rng = rnglib.stream(seed, "demand.group")
    lo, hi = cfg["groups"]["share_range"]
    gw = group_weights(cal, cfg)
    groups = np.zeros_like(counts)
    shares = {}
    for month_id in np.sort(cal["month_id"].unique()):
        idx = np.flatnonzero(cal["month_id"].values == month_id)
        cells = counts[idx].ravel()
        total = int(cells.sum())
        share = rng.uniform(lo, hi)
        want = int(round(share * total))
        if want < cfg["groups"]["min_pax"]:
            want = 0                                   # too small for even one group
        shares[month_id] = share
        if want == 0 or total == 0:
            continue
        weights = cells * np.repeat(gw[idx], counts.shape[1])
        placed = rng.multinomial(want, weights / weights.sum())
        for _ in range(20):                            # move any excess to cells with room
            excess = int(np.maximum(placed - cells, 0).sum())
            if excess == 0:
                break
            placed = np.minimum(placed, cells)
            room = cells - placed
            placed += rng.multinomial(excess, room / room.sum())
        groups[idx] = placed.reshape(len(idx), counts.shape[1])
    return groups, shares


def build_demand(cfg: dict, seed: int | None = None):
    """Run stage 1. Returns the long table (day x route) and the calendar."""
    seed = cfg["seed"] if seed is None else seed
    cal = build_calendar(cfg)
    mu = expected_tickets(cal, cfg, seed)
    counts = draw_counts(mu, cfg, seed)
    groups, shares = split_groups(cal, counts, cfg, seed)
    route_ids = sorted(cfg["routes"]["base_share"])
    rows = []
    for j, rid in enumerate(route_ids):
        rows.append(pd.DataFrame({
            "date": cal["date"], "route_id": rid, "tickets": counts[:, j],
            "group_tickets": groups[:, j], "individual_tickets": counts[:, j] - groups[:, j],
        }))
    long = pd.concat(rows, ignore_index=True).sort_values(["date", "route_id"], ignore_index=True)
    return long, cal, shares
