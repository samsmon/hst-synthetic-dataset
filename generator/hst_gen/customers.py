"""Customers of individual tickets: commuters (persistent, may churn), occasional travellers, one-time buyers."""
import numpy as np
import pandas as pd

from .vecnames import NIK_MULT, PASSPORT_MULT, PHONE_MULT, People, scatter

SEG = {"commuter": 0, "occasional": 1, "one_time": 2}
EMPTY = np.array([], dtype=np.int64)


class CustomerBook:
    def __init__(self, cfg: dict, people: People, ids):
        self.c = cfg["stage3"]["customers"]
        self.people, self.ids = people, ids
        # commuter pool (arrays grow by concatenation)
        self.cm_id, self.cm_route = EMPTY.copy(), EMPTY.copy()
        self.cm_weight, self.cm_fcc = np.array([]), np.array([], dtype=bool)
        self.cm_name, self.cm_idnum, self.cm_nat = np.array([], dtype="U60"), np.array([], dtype="U20"), np.array([], dtype="U2")
        self.cm_active = np.array([], dtype=bool)
        self.cm_created = np.array([], dtype="datetime64[D]")               # account creation date, NaT until the first month is done
        self.cm_churn: dict = {}                       # customer id -> churn date
        # occasional pool
        self.oc_id, self.oc_name, self.oc_idnum, self.oc_nat = EMPTY.copy(), np.array([], dtype="U60"), np.array([], dtype="U20"), np.array([], dtype="U2")
        self.oc_created = np.array([], dtype="datetime64[D]")
        self.truth: list = []                          # (customer id, segment) of every customer

    # ------------------------------------------------------------ new customers
    def _create(self, rng, n: int, ref_date: np.datetime64):
        """Attributes of n new customers (without an id yet assigned to a segment)."""
        c = self.c
        gender = np.where(rng.random(n) < 0.5, "M", "F")
        name, stem = self.people.draw(rng, gender)
        nat = np.full(n, "ID", dtype="U2")
        idnum = np.char.add("99", scatter(self.ids.take("nik", n), NIK_MULT, 14))
        foreign = rng.random(n) < c["foreign_share"]
        k = int(foreign.sum())
        if k:
            fname, fnat = self.people.foreign(rng, k)
            name[foreign], nat[foreign] = fname, fnat
            stem[foreign] = np.char.replace(np.char.lower(fname), " ", ".")
            idnum[foreign] = scatter(self.ids.take("passport", k), PASSPORT_MULT, 7, "PP")
        cid = self.ids.take("customer", n)
        age = np.clip(rng.normal(c["age"]["mean"], c["age"]["sd"], size=n), c["age"]["min"], c["age"]["max"])
        birth = ref_date - (age * 365.25).astype("timedelta64[D]")
        has_mail, has_phone = rng.random(n) < 0.70, rng.random(n) < 0.90
        email = np.where(has_mail, np.char.add(np.char.add(stem, cid.astype("U12")), "@mail.example"), "")
        phone = np.where(has_phone, np.char.add("0809", scatter(cid, PHONE_MULT, 8)), "")
        frame = pd.DataFrame({"id": cid, "id_number": idnum, "name": name, "gender": gender, "birth_date": birth,
                              "email": email, "phone": phone, "city": self.people.city(rng, n), "nationality": nat})
        return frame, cid, name, idnum, nat

    # ---------------------------------------------------------------- commuters
    def _commuters_for_route(self, rng, route: int, n_tickets: int, month_start: np.datetime64):
        """Customer pool indexes for n tickets on a route. Creates commuters when the pool is too small."""
        c = self.c
        mine = (self.cm_route == route) & self.cm_active
        # some leave before this month
        leave = np.flatnonzero(mine & (rng.random(len(mine)) < c["commuter_monthly_churn"]))
        for i in leave:
            self.cm_active[i] = False
            self.cm_churn[int(self.cm_id[i])] = month_start
        mine = (self.cm_route == route) & self.cm_active
        target = int(np.ceil(n_tickets / c["commuter_trips_per_month"]))
        if mine.sum() > 1.25 * target:                      # demand shrank (COVID): surplus commuters leave
            extra = np.flatnonzero(mine)
            extra = rng.choice(extra, size=int(mine.sum() - 1.25 * target), replace=False)
            self.cm_active[extra] = False
            for i in extra:
                self.cm_churn[int(self.cm_id[i])] = month_start
            mine = (self.cm_route == route) & self.cm_active
        new_frame = None
        n_new = min(max(target - int(mine.sum()), 0), n_tickets)
        if n_new:
            new_frame, cid, name, idnum, nat = self._create(rng, n_new, month_start)
            start = len(self.cm_id)
            self.cm_id = np.concatenate([self.cm_id, cid])
            self.cm_route = np.concatenate([self.cm_route, np.full(n_new, route)])
            self.cm_weight = np.concatenate([self.cm_weight, rng.lognormal(0, c["commuter_weight_sigma"], size=n_new)])
            self.cm_fcc = np.concatenate([self.cm_fcc, rng.random(n_new) < c["commuter_fcc_share"]])
            self.cm_name, self.cm_idnum, self.cm_nat = (np.concatenate([self.cm_name, name]),
                                                        np.concatenate([self.cm_idnum, idnum]), np.concatenate([self.cm_nat, nat]))
            self.cm_active = np.concatenate([self.cm_active, np.ones(n_new, dtype=bool)])
            self.cm_created = np.concatenate([self.cm_created, np.full(n_new, np.datetime64("NaT"), dtype="datetime64[D]")])
            self.truth += [(int(i), "commuter") for i in cid]
        pool = np.flatnonzero((self.cm_route == route) & self.cm_active)
        pick = pool[rng.choice(pool.size, size=n_tickets, p=self.cm_weight[pool] / self.cm_weight[pool].sum())]
        if n_new:                                           # every new commuter gets at least one ticket
            fresh = np.arange(len(self.cm_id) - n_new, len(self.cm_id))
            slots = rng.choice(n_tickets, size=n_new, replace=False)
            pick[slots] = fresh
        return pick, new_frame

    # ----------------------------------------------------------------- assign
    def assign(self, rng, month_start: np.datetime64, route: np.ndarray, share_scale: float = 1.0):
        """Segment and customer for every individual ticket of a month (route ids 1 to 3).

        Returns a dict of per-ticket arrays and the frame of customers created this month.
        """
        n = len(route)
        sh = self.c["segment_share"]
        p = np.array([sh["commuter"], sh["occasional"], sh["one_time"]])
        seg = rng.choice(3, size=n, p=p / p.sum())
        cid = np.zeros(n, dtype=np.int64)
        name, idnum, nat = np.empty(n, dtype="U60"), np.empty(n, dtype="U20"), np.empty(n, dtype="U2")
        fcc = np.zeros(n, dtype=bool)
        created = np.full(n, np.datetime64("NaT"), dtype="datetime64[D]")
        fresh = []

        for r in (1, 2, 3):                                   # commuters, per route
            rows = np.flatnonzero((seg == 0) & (route == r))
            if rows.size == 0:
                continue
            pick, new_frame = self._commuters_for_route(rng, r, rows.size, month_start)
            cid[rows], name[rows], idnum[rows], nat[rows] = self.cm_id[pick], self.cm_name[pick], self.cm_idnum[pick], self.cm_nat[pick]
            fcc[rows] = self.cm_fcc[pick]
            created[rows] = self.cm_created[pick]
            if new_frame is not None:
                fresh.append(new_frame)

        rows = np.flatnonzero(seg == 1)                       # occasional: some are new, others come back
        if rows.size:
            is_new = rng.random(rows.size) < self.c["occasional_new_share"]
            if len(self.oc_id) == 0:
                is_new[:] = True
            old, new = rows[~is_new], rows[is_new]
            if old.size:
                back = len(self.oc_id) - 1 - np.minimum(rng.exponential(0.35 * len(self.oc_id), size=old.size).astype(int), len(self.oc_id) - 1)
                cid[old], name[old], idnum[old], nat[old] = self.oc_id[back], self.oc_name[back], self.oc_idnum[back], self.oc_nat[back]
                created[old] = self.oc_created[back]
            if new.size:
                frame, nid, nname, nidnum, nnat = self._create(rng, new.size, month_start)
                cid[new], name[new], idnum[new], nat[new] = nid, nname, nidnum, nnat
                self.oc_id, self.oc_name = np.concatenate([self.oc_id, nid]), np.concatenate([self.oc_name, nname])
                self.oc_idnum, self.oc_nat = np.concatenate([self.oc_idnum, nidnum]), np.concatenate([self.oc_nat, nnat])
                self.oc_created = np.concatenate([self.oc_created, np.full(new.size, np.datetime64("NaT"), dtype="datetime64[D]")])
                self.truth += [(int(i), "occasional") for i in nid]
                fresh.append(frame)

        rows = np.flatnonzero(seg == 2)                       # one-time: always a new person
        if rows.size:
            frame, nid, nname, nidnum, nnat = self._create(rng, rows.size, month_start)
            cid[rows], name[rows], idnum[rows], nat[rows] = nid, nname, nidnum, nnat
            self.truth += [(int(i), "one_time") for i in nid]
            fresh.append(frame)
        new_customers = pd.concat(fresh, ignore_index=True) if fresh else None
        return {"customer_id": cid, "name": name, "id_number": idnum, "nationality": nat, "segment": seg, "has_fcc": fcc,
                "created": created}, new_customers

    def register(self, ids: np.ndarray, dates: np.ndarray):
        """Record the creation date of customers made this month (their first purchase date)."""
        for pool_id, pool_created in ((self.cm_id, self.cm_created), (self.oc_id, self.oc_created)):
            if len(pool_id) == 0:
                continue
            pos = np.searchsorted(pool_id, ids)
            ok = (pos < len(pool_id)) & (pool_id[np.minimum(pos, len(pool_id) - 1)] == ids)
            pool_created[pos[ok]] = dates[ok]

    def truth_frame(self) -> pd.DataFrame:
        df = pd.DataFrame(self.truth, columns=["customer_id", "segment"])
        df["churn_date"] = df["customer_id"].map(self.cm_churn)
        return df.sort_values("customer_id", ignore_index=True)
