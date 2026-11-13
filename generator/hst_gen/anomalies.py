"""Stage 5: Injects operational and payment anomalies and builds anomaly_label."""
from pathlib import Path
import numpy as np
import pandas as pd

from .vecnames import TICKET_MULT, scatter


def inject_payment_anomalies(stage3_dir: Path, stage4_dir: Path, cfg: dict, rng: np.random.Generator):
    """Injects underpayment, overpayment, duplicate_payment, and name_mismatch."""
    s5_cfg = cfg["stage5"]
    rates = s5_cfg["rates"]
    bcfg = cfg["stage4"]["bank"]
    acc1, acc2 = str(bcfg["operator_accounts"][0]), str(bcfg["operator_accounts"][1])
    open1, open2 = float(bcfg["opening_balances"][acc1]), float(bcfg["opening_balances"][acc2])

    gb = pd.read_csv(stage3_dir / "group_booking.csv")
    stmt = pd.read_csv(stage4_dir / "bank_statement.csv", dtype={"account_no": str})
    pay = pd.read_csv(stage4_dir / "hidden" / "group_booking_payment.csv")

    labels = []

    # Map checked bookings deterministically
    checked_gb = gb[gb["status"] == "checked"].sort_values("id").copy()
    paid_bookings = set(pay["group_booking_id"].unique())
    eligible_gb = checked_gb[checked_gb["id"].isin(paid_bookings)].sort_values("id")

    n_checked = len(eligible_gb)
    n_under = max(1, int(round(n_checked * rates["underpayment"]))) if n_checked > 0 else 0
    n_over = max(1, int(round(n_checked * rates["overpayment"]))) if n_checked > 0 else 0

    perm = rng.permutation(eligible_gb["id"].values)
    under_ids = list(perm[:n_under])
    over_ids = list(perm[n_under:n_under + n_over])

    # 1. Underpayment
    cut_lo, cut_hi = s5_cfg["underpayment_cut_range"]
    stmt_deltas = {}  # stmt_id -> delta amount

    for bid in under_ids:
        b_row = gb[gb["id"] == bid].iloc[0]
        tot = float(b_row["total_amount"])
        b_pays = pay[pay["group_booking_id"] == bid]
        if b_pays.empty:
            continue
        cut_pct = rng.uniform(cut_lo, cut_hi)
        cut_amt = max(10000.0, float(round(tot * cut_pct / 10000.0) * 10000.0))
        target_pay_idx = b_pays.index[-1]
        cur_alloc = float(pay.loc[target_pay_idx, "allocated_amount"])
        actual_cut = min(cut_amt, max(0.0, cur_alloc - 10000.0))
        if actual_cut > 0:
            pay.loc[target_pay_idx, "allocated_amount"] = cur_alloc - actual_cut
            sid = int(pay.loc[target_pay_idx, "bank_statement_id"])
            stmt_deltas[sid] = stmt_deltas.get(sid, 0.0) - actual_cut
            labels.append({"entity_type": "group_booking", "entity_id": int(bid), "anomaly_type": "underpayment"})

    # 2. Overpayment
    add_lo, add_hi = s5_cfg["overpayment_add_range"]
    for bid in over_ids:
        b_row = gb[gb["id"] == bid].iloc[0]
        tot = float(b_row["total_amount"])
        b_pays = pay[pay["group_booking_id"] == bid]
        if b_pays.empty:
            continue
        add_pct = rng.uniform(add_lo, add_hi)
        add_amt = max(10000.0, float(round(tot * add_pct / 10000.0) * 10000.0))
        target_pay_idx = b_pays.index[-1]
        cur_alloc = float(pay.loc[target_pay_idx, "allocated_amount"])
        pay.loc[target_pay_idx, "allocated_amount"] = cur_alloc + add_amt
        pay.loc[target_pay_idx, "payment_type"] = "overpayment"
        sid = int(pay.loc[target_pay_idx, "bank_statement_id"])
        stmt_deltas[sid] = stmt_deltas.get(sid, 0.0) + add_amt
        labels.append({"entity_type": "group_booking", "entity_id": int(bid), "anomaly_type": "overpayment"})

    # Apply deltas to bank statements
    if stmt_deltas:
        stmt["amount"] = stmt["amount"] + stmt["id"].map(stmt_deltas).fillna(0.0)

    # 3. Duplicate payment
    trf_mask = stmt["transaction_code"] == "TRF"
    trf_indices = stmt[trf_mask].index.to_numpy()
    n_dup = max(1, int(round(len(trf_indices) * rates["duplicate_payment"]))) if len(trf_indices) > 0 else 0
    dup_indices = rng.choice(trf_indices, size=n_dup, replace=False) if n_dup > 0 else []

    max_date = pd.Timestamp("2025-12-31")
    dup_rows = []
    for idx in dup_indices:
        orig = stmt.loc[idx].to_dict()
        tx_dt = pd.Timestamp(orig["transaction_date"]) + pd.Timedelta(days=int(rng.integers(0, 3)))
        tx_dt = min(tx_dt, max_date)
        orig["transaction_date"] = tx_dt.strftime("%Y-%m-%d")
        orig["is_dup_payment"] = True
        dup_rows.append(orig)

    # 4. Name mismatch
    remaining_trf = sorted([i for i in trf_indices if i not in dup_indices])
    n_mismatch = max(1, int(round(len(remaining_trf) * rates["name_mismatch"]))) if len(remaining_trf) > 0 else 0
    mismatch_indices = rng.choice(remaining_trf, size=n_mismatch, replace=False) if n_mismatch > 0 else []
    mismatch_names = s5_cfg["mismatch_names"]

    stmt["is_name_mismatch"] = False
    for idx in mismatch_indices:
        stmt.loc[idx, "sender_name"] = rng.choice(mismatch_names)
        stmt.loc[idx, "is_name_mismatch"] = True

    # Combine statement lines and recalculate balance
    if dup_rows:
        dup_df = pd.DataFrame(dup_rows)
        stmt["is_dup_payment"] = False
        all_stmts = pd.concat([stmt, dup_df], ignore_index=True)
    else:
        all_stmts = stmt.copy()
        all_stmts["is_dup_payment"] = False

    all_stmts["account_no"] = all_stmts["account_no"].astype(str)
    prio_map = {"SETTLE": 1, "TRF": 1, "REFUND": 2, "FEE": 2, "INT": 3}
    all_stmts["prio"] = all_stmts["transaction_code"].map(prio_map).fillna(1).astype(int)
    all_stmts["orig_id"] = all_stmts["id"].fillna(99999999).astype(int)

    all_stmts.sort_values(["account_no", "transaction_date", "prio", "orig_id"], inplace=True)
    all_stmts.reset_index(drop=True, inplace=True)

    balances = np.empty(len(all_stmts), dtype=float)
    for acc, open_b in [(acc1, open1), (acc2, open2)]:
        m = (all_stmts["account_no"] == acc).to_numpy()
        if not m.any():
            continue
        sub_amt = all_stmts.loc[m, "amount"].to_numpy()
        sub_dir = all_stmts.loc[m, "direction"].to_numpy()
        signed = np.where(sub_dir == "credit", sub_amt, -sub_amt)
        bals = open_b + np.cumsum(signed)
        balances[m] = np.round(bals, 2)

    all_stmts["balance"] = balances
    all_stmts.sort_values(["transaction_date", "account_no", "prio", "orig_id"], inplace=True)
    all_stmts.reset_index(drop=True, inplace=True)

    old_to_new = dict(zip(all_stmts["orig_id"], np.arange(1, len(all_stmts) + 1)))
    all_stmts["new_id"] = np.arange(1, len(all_stmts) + 1, dtype=np.int64)

    # Record labels for duplicate payments and name mismatch
    for r in all_stmts.itertuples():
        if getattr(r, "is_dup_payment", False):
            labels.append({"entity_type": "bank_statement", "entity_id": int(r.new_id), "anomaly_type": "duplicate_payment"})
        elif getattr(r, "is_name_mismatch", False):
            labels.append({"entity_type": "bank_statement", "entity_id": int(r.new_id), "anomaly_type": "name_mismatch"})

    # Update group_booking_payment foreign keys
    pay["bank_statement_id"] = pay["bank_statement_id"].map(old_to_new)

    all_stmts["id"] = all_stmts["new_id"]
    cols = ["id", "account_no", "transaction_date", "transaction_code", "direction",
            "amount", "balance", "sender_name", "sender_account_no", "sender_bank", "message"]
    clean_stmt = all_stmts[cols].copy()

    return clean_stmt, pay, labels


def inject_ticket_anomalies(stage2_dir: Path, stage3_dir: Path, out_path: Path,
                            cfg: dict, rng: np.random.Generator, chunksize: int = 500_000):
    """Streams ticket_sales, injecting date_outlier, inactive_issuer, and duplicate_ticket."""
    s5_cfg = cfg["stage5"]
    rates = s5_cfg["rates"]
    disc_lo, disc_hi = s5_cfg["outlier_discount_range"]

    emp = pd.read_csv(stage2_dir / "employee.csv")
    emp["hire_dt"] = pd.to_datetime(emp["hire_date"])
    emp["end_dt"] = pd.to_datetime(emp["end_date"])
    has_end_emps = emp[emp["end_dt"].notna()][["id", "end_dt"]].sort_values("id").to_dict("records")
    all_emp_ids = np.sort(emp["id"].values)

    trips = pd.read_csv(stage2_dir / "trip.csv")
    trip_caps = dict(zip(trips["id"], trips["seat_capacity"]))
    max_trip_id = trips["id"].max()

    # Pass 1: count tickets per trip
    trip_counts = np.zeros(max_trip_id + 1, dtype=int)
    max_tid = 0
    in_path = stage3_dir / "ticket_sales.csv"

    for chk in pd.read_csv(in_path, usecols=["id", "trip_id"], chunksize=chunksize):
        np.add.at(trip_counts, chk["trip_id"].to_numpy(), 1)
        max_tid = max(max_tid, int(chk["id"].max()))

    # Pass 2: stream chunks, mutate in-place, collect duplicate candidates
    dup_candidates = []
    labels = []
    tmp_out = out_path.with_suffix(".tmp")

    first_chunk = True
    for chk in pd.read_csv(in_path, chunksize=chunksize):
        # 1. Date outliers
        # lead_days <= 1 on individual self-service / counter tickets
        purch_dt = pd.to_datetime(chk["purchase_date"])
        dep_dt = pd.to_datetime(chk["departure_date"])
        lead_days = (dep_dt - purch_dt).dt.days

        outlier_mask = (chk["group_booking_id"].isna()) & \
                       (chk["sales_channel_id"].isin([1, 4, 5, 6])) & \
                       (chk["status"].isin(["used", "issued"])) & \
                       (chk["promo_id"].isna()) & \
                       (lead_days <= 1)
        outlier_idx = np.sort(chk[outlier_mask].index.to_numpy())
        n_outliers = int(round(len(outlier_idx) * rates["date_outlier"]))
        if n_outliers > 0 and len(outlier_idx) > 0:
            chosen = rng.choice(outlier_idx, size=min(n_outliers, len(outlier_idx)), replace=False)
            pcts = np.round(rng.uniform(disc_lo, disc_hi, size=len(chosen)), 1)
            bases = chk.loc[chosen, "base_price"].to_numpy()
            discs = np.round(bases * pcts / 100.0).astype(int)
            fees = chk.loc[chosen, "service_fee_amount"].to_numpy()
            chk.loc[chosen, "discount_pct"] = pcts
            chk.loc[chosen, "discount_amount"] = discs
            chk.loc[chosen, "total_price"] = bases - discs + fees
            for tid in chk.loc[chosen, "id"]:
                labels.append({"entity_type": "ticket_sales", "entity_id": int(tid), "anomaly_type": "date_outlier"})

        # 2. Inactive issuers
        staffed_mask = (chk["sales_channel_id"].isin([1, 2, 3])) & \
                       (chk["status"].isin(["used", "issued"])) & \
                       chk["issued_by_employee_id"].notna()
        staffed_idx = np.sort(chk[staffed_mask].index.to_numpy())
        n_inactive = int(round(len(staffed_idx) * rates["inactive_issuer"]))
        if n_inactive > 0 and len(staffed_idx) > 0:
            chosen_staff = rng.choice(staffed_idx, size=min(n_inactive, len(staffed_idx)), replace=False)
            for c_idx in chosen_staff:
                p_date = pd.Timestamp(chk.loc[c_idx, "purchase_date"])
                cand_emps = sorted([r["id"] for r in has_end_emps if r["end_dt"] < p_date])
                if not cand_emps:
                    cand_emps = list(all_emp_ids)
                chosen_emp = rng.choice(cand_emps)
                chk.loc[c_idx, "issued_by_employee_id"] = chosen_emp
                labels.append({"entity_type": "ticket_sales", "entity_id": int(chk.loc[c_idx, "id"]), "anomaly_type": "inactive_issuer"})

        # 3. Duplicate tickets sampling (from self-service channels 4, 5, 6: app, web, agent)
        dup_mask = (chk["group_booking_id"].isna()) & \
                   (chk["sales_channel_id"].isin([4, 5, 6])) & \
                   (chk["promo_id"].isna()) & \
                   (chk["status"].isin(["used", "issued"]))
        dup_idx = np.sort(chk[dup_mask].index.to_numpy())
        n_dup = int(round(len(dup_idx) * rates["duplicate_ticket"]))
        if n_dup > 0 and len(dup_idx) > 0:
            chosen_dup = rng.choice(dup_idx, size=min(n_dup, len(dup_idx)), replace=False)
            for d_idx in chosen_dup:
                t_id = int(chk.loc[d_idx, "trip_id"])
                cap = trip_caps.get(t_id, 300)
                if trip_counts[t_id] < cap:
                    trip_counts[t_id] += 1
                    dup_candidates.append(chk.loc[d_idx].to_dict())

        nullable_int_cols = ["customer_id", "group_booking_id", "promo_id", "issued_by_employee_id", "issue_station_id"]
        for col in nullable_int_cols:
            if col in chk.columns:
                chk[col] = chk[col].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
        for col in ["payment_ref", "platform_payment_ref"]:
            if col in chk.columns:
                chk[col] = chk[col].fillna("")

        chk.to_csv(tmp_out, mode="w" if first_chunk else "a", header=first_chunk, index=False)
        first_chunk = False

    # Append duplicate tickets
    if dup_candidates:
        dup_df = pd.DataFrame(dup_candidates)
        n_new = len(dup_df)
        new_ids = np.arange(max_tid + 1, max_tid + 1 + n_new, dtype=np.int64)
        dup_df["id"] = new_ids
        dup_df["ticket_no"] = np.char.add("T", scatter(new_ids, TICKET_MULT, 12))
        for col in nullable_int_cols:
            if col in dup_df.columns:
                dup_df[col] = dup_df[col].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
        for col in ["payment_ref", "platform_payment_ref"]:
            if col in dup_df.columns:
                dup_df[col] = dup_df[col].fillna("")
        dup_df.to_csv(tmp_out, mode="a", header=False, index=False)
        for nid in new_ids:
            labels.append({"entity_type": "ticket_sales", "entity_id": int(nid), "anomaly_type": "duplicate_ticket"})

    if tmp_out.exists():
        tmp_out.replace(out_path)

    return labels
