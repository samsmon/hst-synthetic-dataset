"""Group bookings: pack the group tickets of a month into bookings, then fill in company, dates and promo."""
import numpy as np
import pandas as pd


class Ids:
    """Running counters so ids stay unique across months."""

    def __init__(self):
        self.next = {"customer": 1, "ticket": 1, "booking": 1, "detail": 1, "nik": 1, "passport": 1, "order": 1, "ref": 1}

    def take(self, name: str, n: int) -> np.ndarray:
        start = self.next[name]
        self.next[name] = start + n
        return np.arange(start, start + n, dtype=np.int64)


def pack_month(rng: np.random.Generator, g: np.ndarray, gcfg: dict):
    """Split group tickets per day and route into bookings of at least min passengers.

    A booking has P passengers and 1 to 3 departure days; every passenger has one ticket on each day.
    Leftovers smaller than the minimum join a single-day booking of that day, otherwise they are
    returned as converted (they become individual tickets). Returns (bookings, converted).
    """
    sz = gcfg["size"]
    minp, maxp, mu, sigma = sz["min"], sz["max"], sz["lognormal_mu"], sz["lognormal_sigma"]
    counts = np.array(list(gcfg["date_count_probs"]))
    probs = np.array(list(gcfg["date_count_probs"].values()), dtype=float)
    probs /= probs.sum()
    gap_lo, gap_hi = gcfg["date_gap_days"]
    bookings, converted = [], np.zeros_like(g)
    for r in range(g.shape[1]):
        resid = g[:, r].astype(np.int64).copy()
        mine = []
        while True:
            elig = np.flatnonzero(resid >= minp)
            if elig.size == 0:
                break
            d0 = int(rng.choice(elig, p=resid[elig] / resid[elig].sum()))
            size = min(minp + int(rng.lognormal(mu, sigma)), maxp, int(resid[d0]))
            if 0 < resid[d0] - size < minp:
                size = int(resid[d0])                       # the rest could not stand alone
            days = [d0]
            for _ in range(int(rng.choice(counts, p=probs)) - 1):
                nxt = days[-1] + int(rng.integers(gap_lo, gap_hi + 1))
                if nxt < len(resid) and resid[nxt] >= size:
                    days.append(nxt)
                else:
                    break
            for d in days:
                resid[d] -= size
            mine.append({"route": r + 1, "size": size, "days": days})
        for d in np.flatnonzero(resid > 0):
            singles = [b for b in mine if b["days"] == [int(d)]]
            if singles:
                singles[int(rng.integers(len(singles)))]["size"] += int(resid[d])
            else:
                converted[d, r] += resid[d]
        bookings.extend(mine)
    return bookings, converted


def assign_directions(rng: np.random.Generator, bookings: list, want_b: np.ndarray, want_j: np.ndarray, p_first_bandung: float):
    """Direction per leg (0 to_bandung, 1 to_jakarta): legs alternate, the first leg is chosen so a day never
    gets more group tickets in a direction than the day plans for. Returns the group tickets per day and direction."""
    used = np.zeros((len(want_b), 2), dtype=np.int64)
    cap = np.stack([want_b, want_j], axis=1)
    for i in rng.permutation(len(bookings)):
        b = bookings[i]
        options = []
        for first in (0, 1):
            dirs = [(first + j) % 2 for j in range(len(b["days"]))]
            over = sum(max(0, used[d, k] + b["size"] - cap[d, k]) for d, k in zip(b["days"], dirs))
            options.append((over, dirs))
        a, c = options
        if a[0] == 0 and c[0] == 0:
            pick = a if rng.random() < p_first_bandung else c
        else:
            pick = a if a[0] <= c[0] else c
        b["dirs"] = pick[1]
        for d, k in zip(b["days"], b["dirs"]):
            used[d, k] += b["size"]
    return used


def booking_frame(ctx, rng, bookings: list, month_days: np.ndarray, ids: Ids) -> pd.DataFrame:
    """One row per booking with company, document date, due date and the best qualifying promo."""
    g3 = ctx.cfg["stage3"]["group"]
    comp, hid = ctx.tables["company"], ctx.tables["company_hidden"]
    n = len(bookings)
    first_day = np.array([month_days[b["days"][0]] for b in bookings], dtype=np.int64)
    last_day = np.array([month_days[b["days"][-1]] for b in bookings], dtype=np.int64)
    size = np.array([b["size"] for b in bookings], dtype=np.int64)
    route = np.array([b["route"] for b in bookings], dtype=np.int64)
    first_dep = ctx.dates[first_day]
    joined = pd.to_datetime(comp["joined_date"]).to_numpy().astype("datetime64[D]")
    weight = hid["activity_weight"].to_numpy()

    company_idx = np.zeros(n, dtype=np.int64)
    for d in np.unique(first_dep):                        # eligibility depends on the departure date
        rows = np.flatnonzero(first_dep == d)
        ok = np.flatnonzero(joined <= d - np.timedelta64(4, "D"))
        if ok.size == 0:
            ok = np.array([int(np.argmin(joined))])
        company_idx[rows] = ok[rng.choice(ok.size, size=rows.size, p=weight[ok] / weight[ok].sum())]

    ld = g3["lead_days"]
    lead = np.clip(np.round(rng.lognormal(np.log(ld["median"]), ld["sigma"], size=n)), ld["min"], ld["max"]).astype(int)
    doc = np.maximum(first_dep - lead.astype("timedelta64[D]"), joined[company_idx])
    doc = np.minimum(doc, first_dep - np.timedelta64(3, "D"))
    due = np.minimum(first_dep - np.timedelta64(3, "D"), doc + np.timedelta64(g3["due_days_after_document"], "D"))

    best_pct, best_id = np.zeros(n), np.zeros(n, dtype=np.int64)
    for start, end, min_pax, route_id, pct, pid in ctx.group_promos:
        ok = (doc >= start) & (doc <= end) & (size >= min_pax)
        if route_id:
            ok &= route == route_id
        better = ok & (pct > best_pct)
        best_pct = np.where(better, pct, best_pct)
        best_id = np.where(better, pid, best_id)

    cls_keys = list(g3["seat_class"])
    cls_p = np.array(list(g3["seat_class"].values()), dtype=float)
    ch_keys = [int(k) for k in g3["channel"]]
    ch_p = np.array(list(g3["channel"].values()), dtype=float)
    return pd.DataFrame({
        "id": ids.take("booking", n), "company_id": comp["id"].to_numpy()[company_idx],
        "company_idx": company_idx, "size": size, "route_id": route, "first_day": first_day, "last_day": last_day,
        "document_date": doc, "payment_due_date": due, "promo_pct": best_pct, "promo_id": best_id,
        "seat_class": np.array(cls_keys)[rng.choice(len(cls_keys), size=n, p=cls_p / cls_p.sum())],
        "channel": np.array(ch_keys)[rng.choice(len(ch_keys), size=n, p=ch_p / ch_p.sum())],
    })
