"""Day-level calendar: phases, Lebaran window, holidays, bans."""
import numpy as np
import pandas as pd

FIXED_HOLIDAYS = [(1, 1), (5, 1), (6, 1), (8, 17), (12, 25)]   # same list as calendar_event


def _in_md_window(month, day, window):
    """True where (month, day) lies in [start, end] given as (m, d, m, d), wrapping over New Year."""
    sm, sd, em, ed = window
    md, s, e = month * 100 + day, sm * 100 + sd, em * 100 + ed
    return (md >= s) | (md <= e) if s > e else (md >= s) & (md <= e)


def build_calendar(cfg: dict) -> pd.DataFrame:
    days = pd.date_range(cfg["period"]["start"], cfg["period"]["end"], freq="D")
    cal = pd.DataFrame({"date": days})
    cal["year"] = days.year
    cal["month"] = days.month
    cal["month_id"] = days.year * 12 + days.month - 1
    cal["dow"] = days.dayofweek                       # 0 = Monday
    cal["is_weekend"] = cal["dow"] >= 5

    cal["covid_phase"] = "normal"
    for ph in cfg["covid_phases"]:
        mask = (days >= pd.Timestamp(ph["start"])) & (days <= pd.Timestamp(ph["end"]))
        cal.loc[mask, "covid_phase"] = ph["phase"]

    # Offset to the nearest Lebaran, NaN outside +-30 days.
    d64 = days.values.astype("datetime64[D]")
    offset = np.full(len(cal), np.nan)
    for leb in cfg["lebaran"]["dates"]:
        diff = (d64 - np.datetime64(leb)).astype(int)
        near = np.abs(diff) <= 30
        offset[near] = diff[near]
    cal["lebaran_offset"] = offset
    w = cfg["lebaran"]["window_days"]
    cal["is_lebaran_window"] = np.abs(offset) <= w
    cal["is_lebaran_window"] = cal["is_lebaran_window"].fillna(False).astype(bool)

    ye = cfg["year_end"]["window"]
    cal["is_year_end"] = _in_md_window(cal["month"].values, days.day.values, (*ye[0], *ye[1]))

    school = np.zeros(len(cal), dtype=bool)
    for win in cfg["school_holidays"]:
        school |= _in_md_window(cal["month"].values, days.day.values, win)
    cal["is_school_holiday"] = school

    holiday = np.zeros(len(cal), dtype=bool)
    for m, d in FIXED_HOLIDAYS:
        holiday |= (cal["month"].values == m) & (days.day.values == d)
    holiday |= offset == 0
    cal["is_public_holiday"] = holiday

    cal["restriction_factor"] = 1.0
    for win in cfg["restriction_windows"]:
        mask = (days >= pd.Timestamp(win["start"])) & (days <= pd.Timestamp(win["end"]))
        cal.loc[mask, "restriction_factor"] = win["factor"]
    return cal
