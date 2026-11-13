"""Stage 5 tests: injected anomalies, answer keys, bank reconciliation, and determinism."""
import copy
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from hst_gen import config as cfglib
from hst_gen.pipeline import run_stage2, export_tables
from hst_gen.stage3 import run_stage3
from hst_gen.stage4 import run_stage4
from hst_gen.stage5 import run_stage5

FIRST = 30
LAST = 31


@pytest.fixture(scope="module")
def stage5_run(tmp_path_factory):
    base = tmp_path_factory.mktemp("stage5_test")
    s2_out = base / "stage2"
    s3_out = base / "stage3"
    s4_out = base / "stage4"
    s5_out = base / "stage5"

    cfg = cfglib.load(None)
    tables = run_stage2(cfg, seed=42)
    export_tables(tables, s2_out, ["employee", "employee_history", "company", "promo", "trip"])

    ctx, stats, truth, _ = run_stage3(cfg, s3_out, seed=42, months=(FIRST, LAST), progress=False)
    res4 = run_stage4(cfg, s4_out, stage2_dir=s2_out, stage3_dir=s3_out, seed=42)
    res5 = run_stage5(cfg, s5_out, stage2_dir=s2_out, stage3_dir=s3_out, stage4_dir=s4_out, seed=42)

    return {
        "cfg": cfg, "base": base,
        "s2": s2_out, "s3": s3_out, "s4": s4_out, "s5": s5_out,
        "res5": res5
    }


def test_stage5_anomalies_generated(stage5_run):
    s5 = stage5_run["s5"]
    anom_path = s5 / "hidden" / "anomaly_label.csv"
    assert anom_path.exists()

    df = pd.read_csv(anom_path)
    assert not df.empty
    assert set(df.columns) == {"id", "entity_type", "entity_id", "anomaly_type"}
    assert df["id"].is_unique

    # Unique constraint (entity_type, entity_id, anomaly_type)
    dups = df.duplicated(subset=["entity_type", "entity_id", "anomaly_type"])
    assert not dups.any()

    # Verify entity_types match schema CHECK
    valid_entities = {"ticket_sales", "group_booking", "bank_statement", "fcc_redemption"}
    assert set(df["entity_type"].unique()).issubset(valid_entities)

    # Check that anomaly types were injected
    present_types = set(df["anomaly_type"].unique())
    expected_subset = {"underpayment", "overpayment", "duplicate_payment", "name_mismatch", "duplicate_ticket", "date_outlier", "inactive_issuer"}
    assert present_types.issubset(expected_subset)
    assert len(present_types) >= 4  # in a 2-month sample, at least 4-7 types appear


def test_stage5_bank_balance_continuity(stage5_run):
    s4 = stage5_run["s4"]
    stmt = pd.read_csv(s4 / "bank_statement.csv")
    assert not stmt.empty

    for acc, grp in stmt.groupby("account_no"):
        sub = grp.sort_values(["transaction_date", "id"]).reset_index(drop=True)
        amounts = sub["amount"].to_numpy()
        directions = sub["direction"].to_numpy()
        balances = sub["balance"].to_numpy()

        for i in range(1, len(sub)):
            expected = balances[i - 1] + amounts[i] if directions[i] == "credit" else balances[i - 1] - amounts[i]
            assert np.isclose(balances[i], round(expected, 2), atol=0.01), \
                f"Discontinuous balance at index {i} in account {acc}: got {balances[i]}, expected {expected}"


def test_stage5_payment_allocations(stage5_run):
    s3 = stage5_run["s3"]
    s4 = stage5_run["s4"]
    s5 = stage5_run["s5"]

    gb = pd.read_csv(s3 / "group_booking.csv")
    pay = pd.read_csv(s4 / "hidden" / "group_booking_payment.csv")
    anom = pd.read_csv(s5 / "hidden" / "anomaly_label.csv")

    under_bids = set(anom[anom["anomaly_type"] == "underpayment"]["entity_id"])
    over_bids = set(anom[anom["anomaly_type"] == "overpayment"]["entity_id"])

    # Underpaid bookings: total_paid < total_amount
    pay_sums = pay.groupby("group_booking_id")["allocated_amount"].sum()
    for bid in under_bids:
        b_tot = float(gb[gb["id"] == bid]["total_amount"].iloc[0])
        paid = float(pay_sums.get(bid, 0.0))
        assert paid < b_tot, f"Booking {bid} marked underpayment but paid {paid} >= {b_tot}"

    # Overpaid bookings: total_paid > total_amount
    for bid in over_bids:
        b_tot = float(gb[gb["id"] == bid]["total_amount"].iloc[0])
        paid = float(pay_sums.get(bid, 0.0))
        assert paid > b_tot, f"Booking {bid} marked overpayment but paid {paid} <= {b_tot}"


def test_stage5_determinism(tmp_path):
    cfg = cfglib.load(None)
    base_a = tmp_path / "a"
    base_b = tmp_path / "b"

    tables = run_stage2(cfg, seed=77)
    for b in (base_a, base_b):
        export_tables(tables, b / "stage2", ["employee", "employee_history", "company", "promo", "trip"])
        run_stage3(cfg, b / "stage3", seed=77, months=(30, 31), progress=False)
        run_stage4(cfg, b / "stage4", stage2_dir=b / "stage2", stage3_dir=b / "stage3", seed=77)
        run_stage5(cfg, b / "stage5", stage2_dir=b / "stage2", stage3_dir=b / "stage3", stage4_dir=b / "stage4", seed=77)

    anom_a = (base_a / "stage5" / "hidden" / "anomaly_label.csv").read_bytes()
    anom_b = (base_b / "stage5" / "hidden" / "anomaly_label.csv").read_bytes()
    assert len(anom_a) == len(anom_b)
    assert anom_a == anom_b

    stmt_a = (base_a / "stage4" / "bank_statement.csv").read_bytes()
    stmt_b = (base_b / "stage4" / "bank_statement.csv").read_bytes()
    assert len(stmt_a) == len(stmt_b)
    assert stmt_a == stmt_b
