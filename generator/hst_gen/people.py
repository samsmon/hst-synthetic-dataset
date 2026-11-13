"""Stage 2a: employees and their career history, simulated month by month.

Headcount follows a target curve. Each month people leave, get promoted or move
station, singleton posts (station master, managers) are refilled, and the rest of
the gap is hired by position and station shares.
"""
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import rng as rnglib
from .names import name_pools, person_names, slug


def _month_starts(start: date, end: date):
    cur = date(start.year, start.month, 1)
    while cur <= end:
        yield cur
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)


def _days_in_month(m: date) -> int:
    nxt = date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    return (nxt - m).days


class _Sim:
    def __init__(self, cfg: dict, seed: int):
        self.cfg = cfg["employees"]
        self.rng = rnglib.stream(seed, "people.employees")
        self.pos = {p["id"]: p for p in self.cfg["positions"]}
        self.stations = sorted(self.cfg["station_weights"])
        self.pools = name_pools(seed)
        self.emps: list[dict] = []
        knots = self.cfg["headcount_knots"]
        self._kx = np.array([pd.Timestamp(d).as_unit("ns").value for d, _ in knots], dtype="float64")
        self._ky = np.array([v for _, v in knots], dtype="float64")
        self.singletons = [(pid, st) for pid, p in self.pos.items() if p.get("singleton")
                           for st in (self.stations if p["singleton"] == "per_station" else [None])]
        self.promotions = 0
        self.transfers = 0
        self.vacated: dict = {}                  # (position, station) -> date the last holder left

    # ----------------------------------------------------------------- helpers
    def target(self, when: date) -> int:
        return int(round(np.interp(pd.Timestamp(when).as_unit("ns").value, self._kx, self._ky)))

    def active(self):
        return [e for e in self.emps if e["end"] is None]

    def day_in(self, month: date) -> date:
        return month + timedelta(days=int(self.rng.integers(_days_in_month(month))))

    def station_choices(self, pid):
        p = self.pos[pid]
        if not p["station_based"]:
            return {None: 1.0}
        w = p.get("stations") or self.cfg["station_weights"]
        tot = sum(w.values())
        return {st: v / tot for st, v in w.items()}

    # ------------------------------------------------------------------- hiring
    def hire(self, pid, station, when: date, active, window=None):
        rng = self.rng
        gender = "M" if rng.random() < 0.5 else "F"
        senior = pid in (3, 4, 6, 7, 9, 11, 14, 15)
        age = float(np.clip(rng.normal(34 if senior else 26, 4), 21, 55))
        birth = when - timedelta(days=int(age * 365.25 + rng.integers(-180, 180)))
        status = "contract" if rng.random() < self.pos[pid]["contract_share"] else "permanent"
        emp = {"gender": gender, "birth": birth, "hire": when, "end": None, "status": status,
               "pos": pid, "station": station, "pos_start": when,
               "history": [{"pos": pid, "station": station, "start": when}]}
        self.emps.append(emp)
        active.append(emp)
        return emp

    def change_position(self, emp, pid, station, when: date, active):
        emp["history"].append({"pos": pid, "station": station, "start": when})
        emp["pos"], emp["station"], emp["pos_start"] = pid, station, when

    def desired(self, n_total: int):
        nonsingle = [p for p in self.cfg["positions"] if not p.get("singleton")]
        share_sum = sum(p["share"] for p in nonsingle)
        free = max(n_total - len(self.singletons), 0)
        cells = {}
        for p in nonsingle:
            for st, w in self.station_choices(p["id"]).items():
                cells[(p["id"], st)] = p["share"] / share_sum * free * w
        return cells

    def fill_to(self, n_total, when_fn, active):
        """Hire into the largest gaps until the target headcount is reached."""
        cells = self.desired(n_total)
        counts = {}
        for e in active:
            counts[(e["pos"], e["station"])] = counts.get((e["pos"], e["station"]), 0) + 1
        keys = list(cells)
        while len(active) < n_total:
            gaps = np.array([max(cells[k] - counts.get(k, 0), 0.02) for k in keys])
            k = keys[int(self.rng.choice(len(keys), p=gaps / gaps.sum()))]
            self.hire(k[0], k[1], when_fn(), active)
            counts[k] = counts.get(k, 0) + 1

    def fill_singletons(self, when_fn, active, min_tenure_months):
        for pid, st in self.singletons:
            holders = [e for e in active if e["pos"] == pid and (st is None or e["station"] == st)]
            if holders:
                continue
            start = when_fn()
            left = self.vacated.get((pid, st))
            if left is not None and start <= left:
                start = left + timedelta(days=1)
            feeders = [p["id"] for p in self.cfg["positions"] if p.get("next") == pid]
            pool = [e for e in active if e["pos"] in feeders and (st is None or e["station"] == st)
                    and (start - e["pos_start"]).days >= 30 * min_tenure_months]
            if pool:
                pick = min(pool, key=lambda e: e["pos_start"])
                self.change_position(pick, pid, st, start, active)
                self.promotions += 1
            else:
                self.hire(pid, st, start, active)

    # --------------------------------------------------------------- simulation
    def run(self, start: date, end: date):
        rng, cfg = self.rng, self.cfg
        # Initial cohort, hired before the period starts.
        w0, w1 = (pd.Timestamp(d).date() for d in cfg["initial_hire_window"])
        span = (w1 - w0).days
        active: list[dict] = []
        random_day = lambda: w0 + timedelta(days=int(rng.integers(span)))    # noqa: E731
        for pid, st in self.singletons:
            self.hire(pid, st, date(2017, 1, 1) + timedelta(days=int(rng.integers(540))), active)
        self.fill_to(self.target(start), random_day, active)

        promo = cfg["promotion"]
        for month in _month_starts(date(start.year, start.month, 1) + timedelta(days=31), end):
            when = lambda m=month: self.day_in(m)                              # noqa: E731
            active = self.active()
            for e in list(active):                                             # attrition
                rate = cfg["monthly_attrition"][e["status"]]
                if rng.random() < rate and (month - e["pos_start"]).days > 0:
                    e["end"] = month + timedelta(days=int(rng.integers(1, _days_in_month(month))))
                    if self.pos[e["pos"]].get("singleton"):
                        self.vacated[(e["pos"], e["station"])] = e["end"]
            active = self.active()
            for e in list(active):                                             # promotions and transfers
                nxt = self.pos[e["pos"]].get("next")
                tenure = (month - e["pos_start"]).days / 30.4
                if (nxt and not self.pos[nxt].get("singleton") and tenure >= promo["min_tenure_months"]
                        and rng.random() < promo["monthly_hazard"]):
                    self.change_position(e, nxt, e["station"] if self.pos[nxt]["station_based"] else None, when(), active)
                    self.promotions += 1
                elif (self.pos[e["pos"]]["station_based"] and not self.pos[e["pos"]].get("singleton")
                      and tenure >= 6 and rng.random() < cfg["transfer_monthly_hazard"]):
                    options = [s for s in self.station_choices(e["pos"]) if s != e["station"]]
                    if options:
                        self.change_position(e, e["pos"], options[int(rng.integers(len(options)))], when(), active)
                        self.transfers += 1
            self.fill_singletons(when, active, cfg["min_tenure_for_vacancy_months"])
            self.fill_to(self.target(month + timedelta(days=_days_in_month(month) - 1)), when, active)


def _resolve_supervisors(sim, emps, period_end: date, rng):
    """Supervisor: a holder of the supervising position, at the same station when that position is
    station based, on the last day of the employee (end date minus one day, or the period end)."""
    holders: dict = {}
    for e in emps:
        for j, row in enumerate(e["history"]):
            nxt = e["history"][j + 1]["start"] if j + 1 < len(e["history"]) else None
            until = nxt or e["end"] or period_end + timedelta(days=1)
            holders.setdefault(row["pos"], []).append((row["start"], until, row["station"], e["id"]))
    out = {}
    for e in emps:
        sp = sim.pos[e["pos"]]["supervisor"]
        if sp is None:
            out[e["id"]] = None
            continue
        day = (e["end"] - timedelta(days=1)) if e["end"] else period_end
        need_station = sim.pos[sp]["station_based"] and e["station"] is not None
        pool = [i for (a, b, st, i) in holders.get(sp, []) if a <= day < b and i != e["id"]
                and (not need_station or st == e["station"])]
        out[e["id"]] = pool[int(rng.integers(len(pool)))] if pool else None
    return out


def build_employees(cfg: dict, seed: int):
    """Returns (employee, employee_history) DataFrames in the oltp column layout."""
    sim = _Sim(cfg, seed)
    start = pd.Timestamp(cfg["period"]["start"]).date()
    end = pd.Timestamp(cfg["period"]["end"]).date()
    sim.run(start, end)
    rng = sim.rng

    order = sorted(range(len(sim.emps)), key=lambda i: (sim.emps[i]["hire"], rng.random()))
    for new_id, i in enumerate(order, start=1):
        sim.emps[i]["id"] = new_id
    emps = sorted(sim.emps, key=lambda e: e["id"])

    supervisors = _resolve_supervisors(sim, emps, end, rng)
    names = person_names(rng, [e["gender"] for e in emps], sim.pools)
    used_nip, used_mail = set(), set()
    rows, hist = [], []
    for e, full in zip(emps, names):
        first, last = slug(full.split()[0]), slug(full.split()[-1])
        key = (e["birth"].strftime("%Y%m%d"), e["hire"].strftime("%Y%m"), "1" if e["gender"] == "M" else "2")
        seq = 900 + int(rng.integers(100))
        while "".join(key) + f"{seq:03d}" in used_nip:
            seq = 900 + (seq - 899) % 100
        nip = "".join(key) + f"{seq:03d}"
        used_nip.add(nip)
        mail, n = f"{first}.{last}", 1
        while mail in used_mail:
            n += 1
            mail = f"{first}.{last}{n}"
        used_mail.add(mail)
        h = e["history"]
        for j, row in enumerate(h):
            valid_to = h[j + 1]["start"] if j + 1 < len(h) else e["end"]
            hist.append({"employee_id": e["id"], "job_position_id": row["pos"], "home_station_id": row["station"],
                         "valid_from": row["start"], "valid_to": valid_to})
        sup_id = supervisors[e["id"]]
        rows.append({"id": e["id"], "nip": nip, "full_name": full, "gender": e["gender"],
                     "birth_date": e["birth"], "email": f"{mail}@hst-rail.example",
                     "phone": f"08120000{int(rng.integers(10000)):04d}", "hire_date": e["hire"], "end_date": e["end"],
                     "employment_status": e["status"], "job_position_id": e["pos"], "home_station_id": e["station"],
                     "supervisor_id": sup_id})
    employee = pd.DataFrame(rows)
    employee["home_station_id"] = employee["home_station_id"].astype("Int64")
    employee["supervisor_id"] = employee["supervisor_id"].astype("Int64")
    history = pd.DataFrame(hist)
    history.insert(0, "id", range(1, len(history) + 1))
    history["home_station_id"] = history["home_station_id"].astype("Int64")
    return employee, history, {"promotions": sim.promotions, "transfers": sim.transfers}
