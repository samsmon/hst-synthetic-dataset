"""Shared, read-only inputs for stage 3: demand cells, trips, promos, staff and fares."""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .pipeline import run_stage2
from .reference import fares
from .staff import StaffIndex


@dataclass
class Context:
    cfg: dict
    seed: int
    tables: dict
    dates: np.ndarray                      # datetime64[D] per day of the period
    month_rows: dict                       # month_id -> array of day indexes
    tickets: np.ndarray                    # (days, 3) tickets per day and route
    group: np.ndarray
    individual: np.ndarray
    trips_by_key: dict                     # (day index, direction) -> (trip ids, capacities, departure minutes)
    load: np.ndarray                       # (days, 2) planned load factor per direction
    ind_promo: tuple                       # best individual promo (pct, id) per day and route
    fcc_promo: tuple
    group_promos: list                    # (start, end, min pax, route id or 0, pct, id)
    fares: pd.DataFrame
    staff: dict = field(default_factory=dict)

    def day_index(self, dates64: np.ndarray) -> np.ndarray:
        """Day index of dates, clipped to the period."""
        return np.clip(np.searchsorted(self.dates, dates64), 0, len(self.dates) - 1)


def _best_promos(promo: pd.DataFrame, dates: np.ndarray, applies: tuple, n_routes: int = 3):
    pct = np.zeros((len(dates), n_routes))
    pid = np.zeros((len(dates), n_routes), dtype=np.int64)
    for r in promo[promo["applies_to"].isin(applies)].itertuples():
        a = int(np.searchsorted(dates, np.datetime64(r.start_date)))
        b = int(np.searchsorted(dates, np.datetime64(r.end_date), side="right"))
        cols = range(n_routes) if pd.isna(r.route_id) else [int(r.route_id) - 1]
        for c in cols:
            better = pct[a:b, c] < r.discount_pct
            pct[a:b, c] = np.where(better, r.discount_pct, pct[a:b, c])
            pid[a:b, c] = np.where(better, r.id, pid[a:b, c])
    return pct, pid


def build_context(cfg: dict, seed: int | None = None, tables: dict | None = None) -> Context:
    seed = cfg["seed"] if seed is None else seed
    t = tables or run_stage2(cfg, seed)
    cal, long, trips, promo = t["cal"], t["long"], t["trip"], t["promo"]
    dates = cal["date"].values.astype("datetime64[D]")
    n = len(dates)
    shape = (n, len(cfg["routes"]["base_share"]))
    month_rows = {m: np.flatnonzero(cal["month_id"].values == m) for m in np.sort(cal["month_id"].unique())}

    day_idx = np.searchsorted(dates, pd.to_datetime(trips["service_date"]).to_numpy().astype("datetime64[D]"))
    direction = (trips["direction"] == "to_jakarta").to_numpy().astype(int)
    dep_min = trips["departure_time"].map(lambda x: x.hour * 60 + x.minute).to_numpy()
    cap = trips["seat_capacity"].to_numpy()
    dem = trips["_demand_dir"].to_numpy()
    ids = trips["id"].to_numpy()
    trips_by_key, load = {}, np.zeros((n, 2))
    key = day_idx * 2 + direction
    order = np.argsort(key, kind="stable")
    uniq, start, cnt = np.unique(key[order], return_index=True, return_counts=True)
    for k, s, c in zip(uniq, start, cnt):
        rows = order[s:s + c]
        trips_by_key[(int(k // 2), int(k % 2))] = (ids[rows], cap[rows], dep_min[rows])
        load[int(k // 2), int(k % 2)] = dem[rows].sum() / cap[rows].sum()

    gp = [(np.datetime64(r.start_date, "D"), np.datetime64(r.end_date, "D"), 0 if pd.isna(r.min_pax) else int(r.min_pax),
           0 if pd.isna(r.route_id) else int(r.route_id), float(r.discount_pct), int(r.id))
          for r in promo[promo["applies_to"].isin(["group", "all"])].itertuples()]
    ctx = Context(cfg=cfg, seed=seed, tables=t, dates=dates, month_rows=month_rows,
                  tickets=long["tickets"].to_numpy().reshape(shape),
                  group=long["group_tickets"].to_numpy().reshape(shape),
                  individual=long["individual_tickets"].to_numpy().reshape(shape),
                  trips_by_key=trips_by_key, load=load,
                  ind_promo=_best_promos(promo, dates, ("all", "individual")),
                  fcc_promo=_best_promos(promo, dates, ("all", "fcc")),
                  group_promos=gp, fares=fares())
    hist = t["employee_history"]
    for channel, roles in cfg["stage3"]["staff_roles"].items():
        ctx.staff[int(channel)] = StaffIndex(hist, roles)
    ctx.staff["group_creator"] = StaffIndex(hist, [10])
    ctx.staff["verifier"] = StaffIndex(hist, [12])
    ctx.staff["cs"] = StaffIndex(hist, [8, 9])
    return ctx
