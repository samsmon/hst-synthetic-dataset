"""Stage 4 tests: FCC cards, redemptions, ticket status, refunds, and bank statements."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hst_gen import config as cfglib                 # noqa: E402
from hst_gen.pipeline import run_stage2, export_tables  # noqa: E402
from hst_gen.stage3 import run_stage3                # noqa: E402
from hst_gen.stage4 import run_stage4                # noqa: E402

FIRST, LAST = 36, 38                                  # three months of 2023


@pytest.fixture(scope="module")
def run4(tmp_path_factory):
    base = tmp_path_factory.mktemp("s4_test")
    s2_out = base / "stage2"
    s3_out = base / "stage3"
    s4_out = base / "stage4"

    cfg = cfglib.load()
    tables = run_stage2(cfg)
    export_tables(tables, s2_out, ["employee", "employee_history", "company", "promo", "trip"])

    ctx, stats, truth, _ = run_stage3(cfg, s3_out, months=(FIRST, LAST), progress=False)
    res = run_stage4(cfg, s4_out, stage2_dir=s2_out, stage3_dir=s3_out)

    t = pd.read_csv(s3_out / "ticket_sales.csv", keep_default_na=False, na_values=[""], dtype={"period": str})
    b = pd.read_csv(s3_out / "group_booking.csv", na_values=[""], dtype={"period": str})
    cards = res["cards"]
    reds = res["redemptions"]
    refunds = res["refunds"]
    stmts = res["statements"]
    payments = res["payments"]
    hist = tables["employee_history"]

    return ctx, t, b, cards, reds, refunds, stmts, payments, hist


def test_fcc_card_validity_and_quotas(run4):
    _, t, _, cards, reds, _, _, _, hist = run4
    assert len(cards) > 0 and len(reds) > 0
    assert cards["id"].is_unique and cards["card_no"].is_unique
    assert reds["id"].is_unique and reds["order_id"].is_unique

    # Expiry > registration
    assert (pd.to_datetime(cards["expiry_date"]) > pd.to_datetime(cards["registration_date"])).all()

    # Card type G and S properties
    is_g = cards["card_type"] == "G"
    is_s = cards["card_type"] == "S"
    assert (cards.loc[is_g, "initial_quota"] == 10).all()
    assert (cards.loc[is_s, "initial_quota"] == 6).all()
    g_dur = (pd.to_datetime(cards.loc[is_g, "expiry_date"]) - pd.to_datetime(cards.loc[is_g, "registration_date"])).dt.days
    s_dur = (pd.to_datetime(cards.loc[is_s, "expiry_date"]) - pd.to_datetime(cards.loc[is_s, "registration_date"])).dt.days
    assert (g_dur == 60).all()
    assert (s_dur == 30).all()

    # Redemptions count and remaining quota
    red_counts = reds.groupby("card_id").size().reindex(cards["id"], fill_value=0)
    assert (cards["remaining_quota"] == cards["initial_quota"] - red_counts.values).all()
    assert (cards["remaining_quota"] >= 0).all()
    assert (cards["remaining_quota"] <= cards["initial_quota"]).all()

    # Redemptions date within validity
    merged_red = reds.merge(cards[["id", "registration_date", "expiry_date", "route_id"]], left_on="card_id", right_on="id")
    r_date = pd.to_datetime(merged_red["redeemed_at"].str[:10])
    reg_date = pd.to_datetime(merged_red["registration_date"])
    exp_date = pd.to_datetime(merged_red["expiry_date"])
    assert (r_date >= reg_date).all()
    assert (r_date <= exp_date).all()

    # Route matches ticket route
    t_route = t.set_index("id")["route_id"]
    assert (merged_red["route_id"] == merged_red["ticket_sales_id"].map(t_route)).all()

    # Registered by employee is active CSO on registration date
    cso_hist = hist[hist["job_position_id"] == 8]
    sample = cards.sample(min(len(cards), 200), random_state=42)
    for r in sample.itertuples():
        day = pd.Timestamp(r.registration_date).date()
        emp_id = int(r.registered_by_employee_id)
        active = cso_hist[(cso_hist["employee_id"] == emp_id) & (pd.to_datetime(cso_hist["valid_from"]).dt.date <= day)
                          & (cso_hist["valid_to"].isna() | (pd.to_datetime(cso_hist["valid_to"]).dt.date > day))]
        assert len(active) >= 1, f"Employee {emp_id} not active CSO on {day}"


def test_refunds_and_status(run4):
    _, t, _, _, _, refunds, _, _, hist = run4
    valid_statuses = {"issued", "used", "cancelled", "refunded"}
    assert set(t["status"]).issubset(valid_statuses)

    # Every refunded ticket has a refund row, cancelled tickets do not
    ref_tids = set(refunds["ticket_sales_id"])
    t_ref_ids = set(t[t["status"] == "refunded"]["id"])
    t_canc_ids = set(t[t["status"] == "cancelled"]["id"])
    assert ref_tids == t_ref_ids
    assert len(t_canc_ids.intersection(ref_tids)) == 0

    if not refunds.empty:
        assert refunds["id"].is_unique and refunds["ticket_sales_id"].is_unique
        t_sub = t.set_index("id").loc[refunds["ticket_sales_id"]]
        r_date = pd.to_datetime(refunds["refund_date"]).dt.date.values
        p_date = pd.to_datetime(t_sub["purchase_date"]).dt.date.values
        d_date = pd.to_datetime(t_sub["departure_date"]).dt.date.values

        assert (r_date >= p_date).all()
        assert (r_date <= d_date).all()
        assert (refunds["refund_amount"].values <= t_sub["total_price"].values).all()
        assert (refunds["refund_amount"].values == t_sub["total_price"].values - refunds["refund_fee"].values).all()

        # Fee rules
        no_fee = refunds["reason"].isin(["schedule_change", "duplicate_booking"])
        assert (refunds.loc[no_fee, "refund_fee"] == 0).all()

        req = refunds["reason"] == "customer_request"
        expected_fee = np.round(t_sub.loc[req.values, "total_price"].values * 0.25).astype(int)
        assert (refunds.loc[req, "refund_fee"].values == expected_fee).all()

        # Staff CS check if non-empty
        cs_hist = hist[hist["job_position_id"].isin([8, 9])]
        proc_emp = refunds[refunds["processed_by_employee_id"].notna() & refunds["processed_by_employee_id"].ne("")]
        sample = proc_emp.sample(min(len(proc_emp), 200), random_state=42)
        for r in sample.itertuples():
            day = pd.Timestamp(r.refund_date).date()
            emp_id = int(r.processed_by_employee_id)
            active = cs_hist[(cs_hist["employee_id"] == emp_id) & (pd.to_datetime(cs_hist["valid_from"]).dt.date <= day)
                             & (cs_hist["valid_to"].isna() | (pd.to_datetime(cs_hist["valid_to"]).dt.date > day))]
            assert len(active) >= 1, f"CS employee {emp_id} not active on {day}"


def test_bank_statement_and_payments(run4):
    _, _, b, _, _, _, stmts, payments, _ = run4
    assert len(stmts) > 0 and len(payments) > 0
    assert stmts["id"].is_unique

    # Valid codes and directions
    valid_codes = {"TRF", "SETTLE", "FEE", "INT", "REFUND", "OTHER"}
    assert set(stmts["transaction_code"]).issubset(valid_codes)
    assert set(stmts["direction"]).issubset({"credit", "debit"})
    assert (stmts["amount"] > 0).all()

    # Balance continuity per account
    for acc, grp in stmts.groupby("account_no"):
        grp = grp.sort_values(["transaction_date", "id"])
        amt = grp["amount"].values
        dr = grp["direction"].values
        bal = grp["balance"].values
        diff = np.where(dr == "credit", amt, -amt)
        calc_bal = np.round(bal[0] + np.cumsum(np.concatenate([[0], diff[1:]])), 2)
        assert np.allclose(bal, calc_bal, atol=0.01), f"Discontinuous balance on account {acc}"

    # Allocation checks
    # Allocations do not exceed bank statement line amount
    line_allocs = payments.groupby("bank_statement_id")["allocated_amount"].sum()
    s_amt = stmts.set_index("id")["amount"]
    assert (line_allocs <= s_amt.loc[line_allocs.index] + 0.01).all()

    # Clean checked bookings have allocated payments summing to total_amount
    checked_b = b[b["status"] == "checked"]
    booking_allocs = payments.groupby("group_booking_id")["allocated_amount"].sum()
    chk_allocs = booking_allocs.reindex(checked_b["id"], fill_value=0.0)
    assert np.allclose(chk_allocs.values, checked_b["total_amount"].values, atol=0.01)


def test_same_seed_determinism(tmp_path):
    cfg = cfglib.load()
    base_a = tmp_path / "a"
    base_b = tmp_path / "b"

    tables = run_stage2(cfg, seed=42)
    export_tables(tables, base_a / "stage2", ["employee", "employee_history", "company", "promo", "trip"])
    export_tables(tables, base_b / "stage2", ["employee", "employee_history", "company", "promo", "trip"])

    run_stage3(cfg, base_a / "stage3", seed=42, months=(30, 31), progress=False)
    run_stage3(cfg, base_b / "stage3", seed=42, months=(30, 31), progress=False)

    run_stage4(cfg, base_a / "stage4", stage2_dir=base_a / "stage2", stage3_dir=base_a / "stage3", seed=42)
    run_stage4(cfg, base_b / "stage4", stage2_dir=base_b / "stage2", stage3_dir=base_b / "stage3", seed=42)

    for name in ("fcc_card", "fcc_redemption", "refund", "bank_statement"):
        assert (base_a / "stage4" / f"{name}.csv").read_bytes() == (base_b / "stage4" / f"{name}.csv").read_bytes()
    assert (base_a / "stage4" / "hidden" / "group_booking_payment.csv").read_bytes() == \
           (base_b / "stage4" / "hidden" / "group_booking_payment.csv").read_bytes()
