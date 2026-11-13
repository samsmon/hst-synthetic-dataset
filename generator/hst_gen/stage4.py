"""Runs stage 4: FCC cards & redemptions, bank statements and booking payments."""
from pathlib import Path
import shutil
import time
import pandas as pd

from .bank import build_bank
from .fcc import build_fcc
from .pipeline import run_stage2


def run_stage4(cfg: dict, out_dir: Path, stage2_dir: Path | None = None,
               stage3_dir: Path | None = None, seed: int | None = None):
    t0 = time.perf_counter()
    seed = cfg["seed"] if seed is None else seed
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "hidden").mkdir(exist_ok=True)

    base_out = out.parent
    s2_dir = Path(stage2_dir) if stage2_dir else base_out / "stage2"
    s3_dir = Path(stage3_dir) if stage3_dir else base_out / "stage3"

    # Get employee_history
    hist_path = s2_dir / "employee_history.csv"
    if hist_path.exists():
        emp_hist = pd.read_csv(hist_path)
    else:
        tables = run_stage2(cfg, seed)
        emp_hist = tables["employee_history"]

    # 1. FCC
    cards, redemptions = build_fcc(s3_dir / "ticket_sales.csv", emp_hist, cfg, seed)
    cards.to_csv(out / "fcc_card.csv", index=False)
    redemptions.to_csv(out / "fcc_redemption.csv", index=False)

    # 2. Refunds
    ref_path_s3 = s3_dir / "refund.csv"
    ref_path_out = out / "refund.csv"
    if ref_path_s3.exists():
        if ref_path_s3.resolve() != ref_path_out.resolve():
            shutil.copyfile(ref_path_s3, ref_path_out)
        refunds = pd.read_csv(ref_path_out)
    elif ref_path_out.exists():
        refunds = pd.read_csv(ref_path_out)
    else:
        refunds = pd.DataFrame(columns=[
            "id", "ticket_sales_id", "refund_date", "refund_amount", "refund_fee", "reason", "processed_by_employee_id"
        ])
        refunds.to_csv(ref_path_out, index=False)

    # 3. Bank statement & Payments
    statements, payments = build_bank(s2_dir, s3_dir, ref_path_out, cfg, seed)
    statements.to_csv(out / "bank_statement.csv", index=False)
    payments.to_csv(out / "hidden" / "group_booking_payment.csv", index=False)

    took = time.perf_counter() - t0
    return {
        "cards": cards,
        "redemptions": redemptions,
        "refunds": refunds,
        "statements": statements,
        "payments": payments,
        "took": took,
    }
