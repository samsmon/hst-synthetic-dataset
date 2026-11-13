"""Runs stage 5: Injects anomalies into tickets, bookings, and bank statements, and outputs anomaly_label."""
from pathlib import Path
import time
import numpy as np
import pandas as pd

from . import rng as rnglib
from .anomalies import inject_payment_anomalies, inject_ticket_anomalies


def run_stage5(cfg: dict, out_dir: Path, stage2_dir: Path | None = None,
               stage3_dir: Path | None = None, stage4_dir: Path | None = None,
               seed: int | None = None):
    """Pipeline runner for Stage 5."""
    t0 = time.time()
    s_val = seed if seed is not None else cfg.get("seed", 42)
    rng = rnglib.stream(s_val, "stage5")

    s5_dir = Path(out_dir)
    base_out = s5_dir.parent
    s2_dir = Path(stage2_dir) if stage2_dir else base_out / "stage2"
    s3_dir = Path(stage3_dir) if stage3_dir else base_out / "stage3"
    s4_dir = Path(stage4_dir) if stage4_dir else base_out / "stage4"

    s5_dir.mkdir(parents=True, exist_ok=True)
    (s5_dir / "hidden").mkdir(parents=True, exist_ok=True)

    # 1. Payment and bank anomalies
    clean_stmt, pay, pay_labels = inject_payment_anomalies(s3_dir, s4_dir, cfg, rng)
    clean_stmt.to_csv(s4_dir / "bank_statement.csv", index=False)
    pay.to_csv(s4_dir / "hidden" / "group_booking_payment.csv", index=False)

    # 2. Ticket anomalies
    ticket_labels = inject_ticket_anomalies(s2_dir, s3_dir, s3_dir / "ticket_sales.csv", cfg, rng)

    # 3. Assemble anomaly_label
    all_labels = pay_labels + ticket_labels
    if all_labels:
        anom_df = pd.DataFrame(all_labels)
        anom_df.drop_duplicates(subset=["entity_type", "entity_id", "anomaly_type"], inplace=True)
        anom_df.sort_values(["entity_type", "entity_id", "anomaly_type"], inplace=True)
        anom_df.reset_index(drop=True, inplace=True)
        anom_df["id"] = np.arange(1, len(anom_df) + 1, dtype=np.int64)
        anom_df = anom_df[["id", "entity_type", "entity_id", "anomaly_type"]]
    else:
        anom_df = pd.DataFrame(columns=["id", "entity_type", "entity_id", "anomaly_type"])

    anom_df.to_csv(s5_dir / "hidden" / "anomaly_label.csv", index=False)
    anom_df.to_csv(s5_dir / "anomaly_label.csv", index=False)

    took = time.time() - t0
    return {
        "anomalies": anom_df,
        "statements": clean_stmt,
        "payments": pay,
        "took": took
    }
