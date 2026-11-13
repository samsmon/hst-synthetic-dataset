"""Stage 3 invariants on a few mature months. They mirror the database constraints and add the checks
a database cannot do (capacity, staff on duty, promo rules, booking sizes)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hst_gen import config as cfglib                 # noqa: E402
from hst_gen.stage3 import run_stage3                # noqa: E402

FIRST, LAST = 36, 38                                  # three months of 2023 at full density
STATION_ROLES = {1: {1, 2, 3}, 2: {10}, 3: {8}}


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("s3")
    cfg = cfglib.load()
    ctx, stats, truth, _ = run_stage3(cfg, out, months=(FIRST, LAST), progress=False)
    t = pd.read_csv(out / "ticket_sales.csv", keep_default_na=False, na_values=[""], dtype={"period": str})
    b = pd.read_csv(out / "group_booking.csv", na_values=[""], dtype={"period": str})
    d = pd.read_csv(out / "group_booking_detail.csv")
    c = pd.read_csv(out / "customer.csv", na_values=[""], dtype={"id_number": str})
    tr = pd.read_csv(out / "hidden" / "ticket_group_truth.csv")
    return ctx, stats, t, b, d, c, tr, truth


def test_row_counts_match_demand(run):
    ctx, stats, t, *_ = run
    days = np.concatenate([ctx.month_rows[m] for m in list(ctx.month_rows)[FIRST:LAST]])
    assert len(t) == int(ctx.tickets[days].sum())
    assert t["id"].is_unique and t["ticket_no"].is_unique
    assert (t["id"].diff().dropna() == 1).all()


def test_money_and_dates(run):
    _, _, t, *_ = run
    assert (t["total_price"] == t["base_price"] - t["discount_amount"] + t["service_fee_amount"]).all()
    assert (t["total_price"] > 0).all() and (t["discount_pct"] <= 40).all()
    assert (t["purchase_date"] <= t["departure_date"]).all()
    assert (t["period"] == t["departure_date"].str[:7]).all()


def test_trip_capacity_direction_and_times(run):
    ctx, _, t, *_ = run
    trips = ctx.tables["trip"].set_index("id")
    per = t.groupby("trip_id").size()
    assert (per <= trips.loc[per.index, "seat_capacity"]).all()
    joined = t.join(trips[["service_date", "direction"]], on="trip_id")
    assert (joined["departure_date"] == joined["service_date"].astype(str)).all()
    north = joined["direction"] == "to_bandung"
    assert (joined.loc[north, "origin_station_id"] < joined.loc[north, "destination_station_id"]).all()
    assert (joined.loc[~north, "origin_station_id"] > joined.loc[~north, "destination_station_id"]).all()
    assert (t["arrival_time"] > t["departure_time"]).all()


def test_daily_demand_is_exact(run):
    ctx, _, t, *_ = run
    cal = ctx.tables["cal"]
    exp = pd.Series(ctx.tickets.sum(axis=1), index=cal["date"].dt.strftime("%Y-%m-%d"))
    got = t.groupby("departure_date").size()
    assert (exp.loc[got.index] == got).all()


def test_staff_on_duty(run):
    ctx, _, t, *_ = run
    staffed = t["sales_channel_id"].isin([1, 2, 3])
    assert t.loc[staffed, "issued_by_employee_id"].notna().all() and t.loc[staffed, "issue_station_id"].notna().all()
    assert t.loc[~staffed, "issued_by_employee_id"].isna().all() and t.loc[~staffed, "issue_station_id"].isna().all()
    hist = ctx.tables["employee_history"]
    sample = t[staffed].sample(2000, random_state=1)
    for r in sample.itertuples():
        day = pd.Timestamp(r.purchase_date).date()
        h = hist[(hist["employee_id"] == int(r.issued_by_employee_id)) & (hist["valid_from"] <= day)
                 & (hist["valid_to"].isna() | (hist["valid_to"] > day))]
        assert len(h) == 1, r.id
        assert h.iloc[0]["job_position_id"] in STATION_ROLES[r.sales_channel_id]
        assert h.iloc[0]["home_station_id"] == int(r.issue_station_id)


def test_group_bookings(run):
    _, _, t, b, d, _, truth_tickets, _ = run
    assert (b["passenger_count"] >= 20).all()
    assert b["booking_no"].is_unique and (b["payment_due_date"] >= b["document_date"]).all()
    assert (b["document_date"] <= b["period"] + "-31").all()
    pending = b[b["status"] == "pending"]["id"]
    group = t[t["order_id"].str.startswith("BAK-")].copy()
    group["booking"] = group["group_booking_id"]
    mapped = truth_tickets.set_index("ticket_sales_id")["group_booking_id"]
    group.loc[group["booking"].isna(), "booking"] = group.loc[group["booking"].isna(), "id"].map(mapped)
    assert group["booking"].notna().all()
    assert set(group.loc[group["group_booking_id"].isna(), "booking"]) <= set(pending)       # only pending ones are hidden
    legs = group.groupby(["booking", "departure_date"]).size().rename("n").reset_index().merge(
        b[["id", "passenger_count"]], left_on="booking", right_on="id")
    assert (legs["n"] == legs["passenger_count"]).all()
    totals = group.groupby("booking")["total_price"].sum()
    assert (b.set_index("id")["total_amount"].loc[totals.index] == totals).all()
    assert (d.groupby("group_booking_id").size() == group.groupby("booking")["departure_date"].nunique()).all()
    assert len(truth_tickets) == int((group["group_booking_id"].isna()).sum())


def test_group_share_per_month(run):
    ctx, _, t, *_ = run
    lo, hi = ctx.cfg["groups"]["share_range"]
    share = t.groupby("period").apply(lambda g: g["order_id"].str.startswith("BAK-").mean(), include_groups=False)
    assert ((share > lo - 0.01) & (share < hi + 0.01)).all(), share


def test_promos_follow_rules(run):
    ctx, _, t, b, *_ = run
    promo = ctx.tables["promo"].set_index("id")
    ind = t[t["promo_id"].notna() & ~t["order_id"].str.startswith("BAK-")]
    for r in ind.sample(min(len(ind), 1500), random_state=2).itertuples():
        p = promo.loc[int(r.promo_id)]
        assert str(p["start_date"]) <= r.purchase_date <= str(p["end_date"])
        assert p["applies_to"] in ("all", "individual", "fcc")
        if r.sales_channel_id != 3:
            assert p["applies_to"] != "fcc"
        assert r.discount_pct == p["discount_pct"]
    gb = b[b["promo_id"].notna()]
    for r in gb.itertuples():
        p = promo.loc[int(r.promo_id)]
        assert str(p["start_date"]) <= r.document_date <= str(p["end_date"])
        assert p["applies_to"] in ("all", "group") and r.passenger_count >= (0 if pd.isna(p["min_pax"]) else p["min_pax"])


def test_customers(run):
    _, _, t, _, _, c, _, truth = run
    assert c["id"].is_unique and c["id_number"].is_unique
    assert c["id_number"].str.match(r"^(99\d{14}|PP\d{7})$").all()
    cust = t["customer_id"].dropna().astype(int)
    assert set(cust) <= set(c["id"])
    first = t[t["customer_id"].notna()].groupby("customer_id")["purchase_date"].min()
    chk = c.set_index("id").loc[first.index[:5000]]
    assert (chk["created_at"].str[:10] == first.iloc[:5000].to_numpy()).all()
    assert set(truth["segment"]) == {"commuter", "occasional", "one_time"}
    assert len(truth) == len(c)


def test_same_seed_same_output(tmp_path):
    cfg = cfglib.load()
    cfg["target_tickets"] = 150_000
    run_stage3(cfg, tmp_path / "a", months=(30, 31), progress=False)
    run_stage3(cfg, tmp_path / "b", months=(30, 31), progress=False)
    for name in ("ticket_sales", "group_booking", "customer"):
        assert (tmp_path / "a" / f"{name}.csv").read_bytes() == (tmp_path / "b" / f"{name}.csv").read_bytes()


def test_no_promo_before_the_period_starts(tmp_path):
    cfg = cfglib.load()
    run_stage3(cfg, tmp_path, months=(0, 1), progress=False)
    t = pd.read_csv(tmp_path / "ticket_sales.csv", keep_default_na=False, na_values=[""])
    early = t[t["purchase_date"] < "2020-01-01"]
    assert len(early) > 0 and early["promo_id"].isna().all()
