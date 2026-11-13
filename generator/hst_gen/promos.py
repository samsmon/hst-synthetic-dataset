"""Stage 2c: promos, modelled on offers such as "February Deals: 20 percent for groups of 20 or more"."""
import calendar
from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import rng as rnglib
from .demand import regime_level, trend_factor


def _pick(rng, mapping):
    keys = list(mapping)
    p = np.array(list(mapping.values()), dtype=float)
    return keys[int(rng.choice(len(keys), p=p / p.sum()))]


def _peak_days(cal: pd.DataFrame) -> set:
    mask = cal["is_lebaran_window"].values | cal["is_year_end"].values
    return set(cal.loc[mask, "date"].dt.date)


def _overlaps(start: date, end: date, peak: set) -> bool:
    return any((start + timedelta(days=i)) in peak for i in range((end - start).days + 1))


def build_promos(cfg: dict, seed: int, cal: pd.DataFrame, long: pd.DataFrame) -> pd.DataFrame:
    rng = rnglib.stream(seed, "promos")
    pc = cfg["promos"]
    peak = _peak_days(cal)
    years = sorted(cal["year"].unique())
    rows = []

    def add(kind, code, name, applies, min_pax, route, pct, start, end):
        rows.append({"promo_code": code, "name": name, "type": kind, "applies_to": applies, "min_pax": min_pax,
                     "route_id": route, "discount_pct": float(pct), "start_date": start, "end_date": end})

    md = pc["monthly_deal"]
    routes = sorted(cfg["routes"]["base_share"])
    for year in years:
        for month in range(1, 13):
            n = int(rng.choice(3, p=md["count_probs"]))
            ndays = calendar.monthrange(year, month)[1]
            for k in range(n):
                for _ in range(8):                                    # find a window outside the peak periods
                    lo, hi = md["duration_days"]
                    first = int(rng.integers(1, ndays - lo + 2))
                    length = int(rng.integers(lo, min(hi, ndays - first + 1) + 1))
                    start = date(year, month, first)
                    end = start + timedelta(days=length - 1)
                    if not _overlaps(start, end, peak):
                        break
                else:
                    continue
                audience = _pick(rng, md["audience"])
                if audience == "group":
                    pct, min_pax = rng.choice(md["discount_group"]), int(_pick(rng, md["min_pax"]))
                else:
                    w = np.array(md["discount_other_weights"])
                    pct, min_pax = rng.choice(md["discount_other"], p=w / w.sum()), None
                route = int(rng.choice(routes)) if rng.random() < md["route_limited_share"] else None
                label = {"group": " for Groups", "individual": " for Individuals", "all": ""}[audience]
                add("monthly_deal", f"HST-{calendar.month_abbr[month].upper()}-{year}-{k + 1}",
                    f"HST {calendar.month_name[month]} Deals{label}", audience, min_pax, route, pct, start, end)

        an = pc["anniversary"]                                        # one week, any date outside the peaks
        for _ in range(500):
            start = date(year, 1, 1) + timedelta(days=int(rng.integers(0, 365 - an["duration_days"])))
            end = start + timedelta(days=an["duration_days"] - 1)
            if not _overlaps(start, end, peak):
                break
        add("anniversary", f"HST-ANNIV-{year}", f"HST Anniversary Week {year}", "all", None, None,
            rng.choice(an["discounts"]), start, end)

        add("loyalty", f"HST-MEMBER-{year}", f"HST Member Fare {year}", "fcc", None, None,
            pc["loyalty"]["discount_until_2022"] if year <= 2022 else pc["loyalty"]["discount_from_2023"],
            date(year, 1, 1), date(year, 12, 31))

    # Low-season savers: the months with the weakest demand relative to the expected level.
    day = long.groupby("date")["tickets"].sum().reindex(cal["date"]).values
    expected = regime_level(cal, cfg["regime_knots"]) * trend_factor(cal, cfg)
    frame = pd.DataFrame({"year": cal["year"], "month": cal["month"], "t": day, "e": expected})
    ratio = frame.groupby(["year", "month"]).agg(t=("t", "sum"), e=("e", "sum"))
    ratio["r"] = ratio["t"] / ratio["e"]
    sv = pc["seasonal"]
    for year in years:
        for month in ratio.loc[year]["r"].nsmallest(sv["months_per_year"]).index:
            ndays = calendar.monthrange(year, month)[1]
            add("seasonal", f"HST-SAVER-{calendar.month_abbr[month].upper()}-{year}",
                f"HST Low Season Saver {calendar.month_name[month]}", "individual", None, None,
                rng.choice(sv["discounts"]), date(year, month, 1), date(year, month, ndays))

    promo = pd.DataFrame(rows).sort_values(["start_date", "promo_code"], ignore_index=True)
    dup = promo.groupby(["name", promo["start_date"].map(lambda d: d.year)]).cumcount()
    promo.loc[dup > 0, "name"] = promo["name"] + " " + (dup[dup > 0] + 1).map({2: "II", 3: "III"}).fillna("+")
    promo.insert(0, "id", range(1, len(promo) + 1))
    promo["min_pax"] = promo["min_pax"].astype("Int64")
    promo["route_id"] = promo["route_id"].astype("Int64")
    return promo
