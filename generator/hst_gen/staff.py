"""Pick employees who held a given role on a given date, from employee_history."""
import numpy as np
import pandas as pd

FAR = np.datetime64("2100-01-01")


class StaffIndex:
    def __init__(self, history: pd.DataFrame, roles):
        h = history[history["job_position_id"].isin(roles)]
        self.emp = h["employee_id"].to_numpy(dtype=np.int64)
        self.start = pd.to_datetime(h["valid_from"]).to_numpy().astype("datetime64[D]")
        end = pd.to_datetime(h["valid_to"]).to_numpy().astype("datetime64[D]")
        self.end = np.where(np.isnat(end), FAR, end)
        self.station = h["home_station_id"].fillna(0).to_numpy(dtype=np.int64)

    def active(self, day) -> np.ndarray:
        return np.flatnonzero((self.start <= day) & (self.end > day))

    def pick(self, dates: np.ndarray, rng: np.random.Generator, want_station: np.ndarray | None = None):
        """For each date choose one active holder (preferring want_station). Returns (employee id, station id).

        Rows without any active holder get employee id 0.
        """
        n = len(dates)
        emp = np.zeros(n, dtype=np.int64)
        st = np.zeros(n, dtype=np.int64)
        if n == 0:
            return emp, st
        order = np.argsort(dates, kind="stable")
        uniq, first, counts = np.unique(dates[order], return_index=True, return_counts=True)
        for day, f, c in zip(uniq, first, counts):
            rows = order[f:f + c]
            act = self.active(day)
            if act.size == 0:
                continue
            if want_station is None:
                chosen = act[rng.integers(act.size, size=c)]
            else:
                chosen = np.empty(c, dtype=np.int64)
                want = want_station[rows]
                for s in np.unique(want):
                    m = want == s
                    pool = act[self.station[act] == s]
                    pool = pool if pool.size else act
                    chosen[m] = pool[rng.integers(pool.size, size=int(m.sum()))]
            emp[rows] = self.emp[chosen]
            st[rows] = self.station[chosen]
        return emp, st
