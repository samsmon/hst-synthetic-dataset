"""Stage 2d: the train schedule, sized from the daily demand of stage 1."""
from datetime import time

import numpy as np
import pandas as pd

from . import rng as rnglib

DOW_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _hhmm(minutes: int) -> time:
    return time(minutes // 60, minutes % 60)


def build_trips(cfg: dict, seed: int, cal: pd.DataFrame, long: pd.DataFrame) -> pd.DataFrame:
    """One row per run. Column _demand_dir is the demand the run must serve (hidden helper for stage 3)."""
    rng = rnglib.stream(seed, "trips")
    tc = cfg["trips"]
    caps = np.array(list(tc["seat_capacity"]), dtype=int)
    cap_p = np.array(list(tc["seat_capacity"].values()), dtype=float)
    cap_p /= cap_p.sum()
    mean_cap = float((caps * cap_p).sum())
    daily = long.groupby("date")["tickets"].sum().reindex(cal["date"]).values
    t0, t1 = tc["first_departure_minute"], tc["last_departure_minute"]

    rows = []
    for d, dow, total in zip(cal["date"].dt.date, cal["dow"].values, daily):
        share_b = tc["to_bandung_share"][DOW_KEYS[dow]]
        demand = {"to_bandung": int(round(total * share_b))}
        demand["to_jakarta"] = int(total) - demand["to_bandung"]
        for direction, dem in demand.items():
            n = int(np.clip(np.ceil(dem / (tc["target_load_factor"] * mean_cap)),
                            tc["min_trips_per_direction"], tc["max_trips_per_direction"]))
            cap = rng.choice(caps, size=n, p=cap_p)
            while cap.sum() * tc["max_load_factor"] < dem and len(cap) < 2 * tc["max_trips_per_direction"]:
                cap = np.append(cap, caps.max())
            n = len(cap)
            spacing = (t1 - t0) / n
            minutes = t0 + (np.arange(n) + 0.5) * spacing + rng.uniform(-0.15, 0.15, size=n) * spacing
            minutes = np.clip((np.round(minutes / 5) * 5).astype(int), t0, t1)
            share = cap / cap.sum()
            for i in range(n):
                number = 101 + 2 * i if direction == "to_bandung" else 102 + 2 * i
                dep = int(minutes[i])
                rows.append((f"HST{number}", d, direction, _hhmm(dep), _hhmm(dep + tc["duration_minutes"]),
                             int(cap[i]), float(dem * share[i])))
    trips = pd.DataFrame(rows, columns=["trip_no", "service_date", "direction", "departure_time",
                                        "arrival_time", "seat_capacity", "_demand_dir"])
    trips = trips.sort_values(["service_date", "departure_time", "direction"], ignore_index=True)
    trips.insert(0, "id", range(1, len(trips) + 1))
    return trips
