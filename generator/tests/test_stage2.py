import copy
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hst_gen import config as cfglib          # noqa: E402
from hst_gen.pipeline import run_stage2        # noqa: E402

SUPERVISOR = {1: 3, 2: 3, 3: 4, 5: 6, 6: 7, 8: 9, 9: 7, 10: 11, 12: 15, 13: 14, 14: 15}
STATION_BASED = {1, 2, 3, 5, 6, 7, 8, 9, 10}
HQ_SINGLE = {4, 11, 15}


@pytest.fixture(scope="module")
def t():
    cfg = cfglib.load()
    cfg["target_tickets"] = 300_000
    return cfg, run_stage2(cfg, seed=5)


def active_on(emp, day):
    day = pd.Timestamp(day).date()
    return emp[(emp["hire_date"] <= day) & (emp["end_date"].isna() | (emp["end_date"] > day))]


def test_employee_basics(t):
    _, tab = t
    e = tab["employee"]
    assert e["nip"].is_unique and (e["nip"].str.len() == 18).all()
    assert e["id"].is_unique and e["id"].is_monotonic_increasing
    assert (e["end_date"].dropna() > e.loc[e["end_date"].notna(), "hire_date"]).all()
    age = [(h - b).days / 365.25 for h, b in zip(e["hire_date"], e["birth_date"])]
    assert min(age) > 20 and max(age) < 60
    assert 400 <= len(e) <= 650


def test_history_is_contiguous_and_matches_employee(t):
    _, tab = t
    e, h = tab["employee"].set_index("id"), tab["employee_history"]
    for emp_id, g in h.groupby("employee_id"):
        g = g.sort_values("valid_from")
        assert g.iloc[0]["valid_from"] == e.loc[emp_id, "hire_date"]
        assert list(g["valid_to"].iloc[:-1]) == list(g["valid_from"].iloc[1:])
        last = g.iloc[-1]
        end = e.loc[emp_id, "end_date"]
        assert (pd.isna(last["valid_to"]) and pd.isna(end)) or last["valid_to"] == end
        assert last["job_position_id"] == e.loc[emp_id, "job_position_id"]
        assert (pd.isna(last["home_station_id"]) and pd.isna(e.loc[emp_id, "home_station_id"])) \
            or last["home_station_id"] == e.loc[emp_id, "home_station_id"]
        assert (g["valid_to"].dropna() > g.loc[g["valid_to"].notna(), "valid_from"]).all()


def test_station_rules_and_supervisors(t):
    _, tab = t
    e = tab["employee"]
    sb = e["job_position_id"].isin(STATION_BASED)
    assert e.loc[sb, "home_station_id"].notna().all()
    assert e.loc[~sb, "home_station_id"].isna().all()
    group_sales = e[e["job_position_id"] == 10]
    assert set(group_sales["home_station_id"].dropna()) <= {1, 4}
    hist = tab["employee_history"]
    for row in e[e["supervisor_id"].notna()].itertuples():
        day = (row.end_date - pd.Timedelta(days=1).to_pytimedelta()) if pd.notna(row.end_date) else pd.Timestamp("2025-12-31").date()
        g = hist[(hist["employee_id"] == row.supervisor_id) & (hist["valid_from"] <= day)
                 & (hist["valid_to"].isna() | (hist["valid_to"] > day))]
        assert len(g) == 1 and g.iloc[0]["job_position_id"] == SUPERVISOR[row.job_position_id], row.id
        if SUPERVISOR[row.job_position_id] in STATION_BASED and pd.notna(row.home_station_id):
            assert g.iloc[0]["home_station_id"] == row.home_station_id
    assert e["supervisor_id"].notna().mean() > 0.95


def test_singleton_posts_have_one_holder(t):
    _, tab = t
    h = tab["employee_history"]
    for day in pd.date_range("2020-03-01", "2025-12-01", freq="MS"):
        d = day.date()
        live = h[(h["valid_from"] <= d) & (h["valid_to"].isna() | (h["valid_to"] > d))]
        for st in (1, 2, 3, 4):
            assert ((live["job_position_id"] == 7) & (live["home_station_id"] == st)).sum() == 1, (day, st)
        for pid in HQ_SINGLE:
            assert (live["job_position_id"] == pid).sum() == 1, (day, pid)


def test_singleton_posts_never_have_two_holders(t):
    _, tab = t
    h = tab["employee_history"]
    for pid, group in h[h["job_position_id"].isin(HQ_SINGLE | {7})].groupby(
            ["job_position_id", h["home_station_id"].fillna(0)]):
        rows = group.sort_values("valid_from")
        ends = rows["valid_to"].shift().iloc[1:]
        starts = rows["valid_from"].iloc[1:]
        assert (starts.values >= ends.values).all(), pid


def test_headcount_follows_target(t):
    cfg, tab = t
    for date_s, want in [("2021-12-31", 150), ("2022-12-31", 360), ("2025-12-31", 420)]:
        got = len(active_on(tab["employee"], date_s))
        assert abs(got - want) / want < 0.08, (date_s, got, want)


def test_promos(t):
    _, tab = t
    p, cal = tab["promo"], tab["cal"]
    assert p["id"].is_unique and p["promo_code"].is_unique
    g = p[p["applies_to"] == "group"]
    assert len(g) > 10 and g["min_pax"].min() >= 20
    peak = set(cal.loc[cal["is_lebaran_window"] | cal["is_year_end"], "date"].dt.date)
    for r in p[p["type"].isin(["monthly_deal", "anniversary"])].itertuples():
        days = {r.start_date + pd.Timedelta(days=i).to_pytimedelta() for i in range((r.end_date - r.start_date).days + 1)}
        assert not days & peak, r.promo_code
    per_year = p.assign(year=pd.to_datetime(p["start_date"]).dt.year).groupby(["year", "type"]).size().unstack(fill_value=0)
    assert (per_year["anniversary"] == 1).all() and (per_year["loyalty"] == 1).all() and (per_year["seasonal"] == 2).all()
    assert per_year["monthly_deal"].between(5, 20).all()


def test_trips(t):
    cfg, tab = t
    tr, cal = tab["trip"], tab["cal"]
    assert not tr.duplicated(["trip_no", "service_date"]).any()
    assert set(tr["seat_capacity"]) <= set(cfg["trips"]["seat_capacity"])
    assert tr["service_date"].nunique() == len(cal)
    assert (tr["arrival_time"] > tr["departure_time"]).all()
    day = tr.groupby(["service_date", "direction"]).agg(cap=("seat_capacity", "sum"), dem=("_demand_dir", "sum"))
    assert (day["dem"] <= day["cap"] * cfg["trips"]["max_load_factor"] + 1e-6).all()
    total = tab["long"].groupby("date")["tickets"].sum().sum()
    assert abs(tr["_demand_dir"].sum() - total) < 1


def test_same_seed_same_output():
    cfg = cfglib.load()
    cfg["target_tickets"] = 50_000
    a, b = run_stage2(copy.deepcopy(cfg), seed=9), run_stage2(copy.deepcopy(cfg), seed=9)
    for name in ("employee", "employee_history", "company", "promo", "trip"):
        pd.testing.assert_frame_equal(a[name], b[name])
