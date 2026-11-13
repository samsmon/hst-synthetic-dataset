import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hst_gen import config as cfglib          # noqa: E402
from hst_gen.demand import build_demand        # noqa: E402

TARGET = 200_000


@pytest.fixture(scope="module")
def result():
    cfg = cfglib.load()
    cfg["target_tickets"] = TARGET
    long, cal, shares = build_demand(cfg, seed=7)
    return cfg, long, cal, shares


def daily(long, cal):
    d = long.groupby("date")[["tickets", "group_tickets"]].sum().reset_index()
    return d.merge(cal, on="date")


def test_total_is_exact(result):
    _, long, _, _ = result
    assert int(long["tickets"].sum()) == TARGET


def test_no_negative_and_split_adds_up(result):
    _, long, _, _ = result
    assert (long[["tickets", "group_tickets", "individual_tickets"]] >= 0).all().all()
    assert (long["group_tickets"] + long["individual_tickets"] == long["tickets"]).all()


def test_same_seed_same_output():
    cfg = cfglib.load()
    cfg["target_tickets"] = 50_000
    a, _, _ = build_demand(cfg, seed=3)
    b, _, _ = build_demand(cfg, seed=3)
    c, _, _ = build_demand(cfg, seed=4)
    pd.testing.assert_frame_equal(a, b)
    assert not a["tickets"].equals(c["tickets"])


def test_monthly_group_share_in_range(result):
    cfg, long, cal, _ = result
    lo, hi = cfg["groups"]["share_range"]
    d = daily(long, cal).groupby("month_id")[["tickets", "group_tickets"]].sum()
    share = d["group_tickets"] / d["tickets"]
    # rounding to whole tickets can move a share by 1 / tickets
    tol = 1.0 / d["tickets"]
    assert ((share >= lo - tol) & (share <= hi + tol)).all()
    assert share.max() - share.min() > 0.05            # shares really vary by month


def test_covid_shape(result):
    _, long, cal, _ = result
    d = daily(long, cal)
    normal = d[d["year"] >= 2023]["tickets"].mean()
    lockdown = d[d["covid_phase"] == "lockdown"]["tickets"].mean()
    assert lockdown < 0.30 * normal
    delta = d[(d["date"] >= "2021-07-10") & (d["date"] <= "2021-07-25")]["tickets"].mean()
    assert delta < 0.20 * normal


def test_lebaran_and_year_end_peaks(result):
    _, long, cal, _ = result
    d = daily(long, cal)
    d = d[d["year"] >= 2023]
    for leb in d.loc[d["lebaran_offset"] == 0, "date"]:
        near = d[(d["date"] - leb).abs() <= pd.Timedelta(days=45)]
        win = near[near["is_lebaran_window"]]["tickets"].mean()
        ref = near[(near["lebaran_offset"] <= -15) & (near["lebaran_offset"] >= -35)]["tickets"].mean()
        assert win > 1.15 * ref
    ye = d[d["is_year_end"]]["tickets"].mean()
    assert ye > 1.1 * d[~d["is_year_end"]]["tickets"].mean()


def test_weekend_above_midweek(result):
    _, long, cal, _ = result
    d = daily(long, cal)
    d = d[d["year"] >= 2023]
    fri_sun = d[d["dow"].isin([4, 5, 6])]["tickets"].mean()
    tue_wed = d[d["dow"].isin([1, 2])]["tickets"].mean()
    assert fri_sun > 1.2 * tue_wed
