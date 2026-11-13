"""Generates bank_statement and oltp_truth.group_booking_payment."""
from pathlib import Path
import numpy as np
import pandas as pd

from . import rng as rnglib


def _dstr(dt) -> str:
    if isinstance(dt, str):
        return dt[:10]
    if hasattr(dt, "strftime"):
        return dt.strftime("%Y-%m-%d")
    return str(np.datetime_as_string(dt, unit="D"))


def _corrupt_name(name: str, mode: str) -> str:
    if mode == "upper":
        return name.upper()
    if mode == "short":
        for pfx in ("PT ", "CV "):
            if name.startswith(pfx):
                return name[len(pfx):]
        return " ".join(name.split()[:2])
    if mode == "typo" and len(name) > 5:
        i = len(name) // 2
        return name[:i] + name[i + 1] + name[i] + name[i + 2:]
    return name


def _corrupt_msg(bno: str, cname: str, ptype: str, mode: str) -> str:
    if mode == "empty":
        return ""
    if mode == "abbreviated":
        return f"{bno}" if ptype == "full" else f"{ptype.upper()} {bno}"
    if mode == "typo":
        return f"Pembayaran {bno.replace('-', ' ')} {cname[:10]}"
    if ptype == "full":
        return f"Pembayaran {bno} {cname}"
    if ptype == "deposit":
        return f"DP {bno} {cname}"
    if ptype == "final":
        return f"Pelunasan {bno} {cname}"
    return f"Cicilan {bno} {cname}"


def build_bank(stage2_dir: Path, stage3_dir: Path, refund_path: Path, cfg: dict, seed: int):
    """Builds bank_statement and group_booking_payment tables."""
    rng = rnglib.stream(seed, "stage4.bank")
    bcfg = cfg["stage4"]["bank"]
    acc1, acc2 = bcfg["operator_accounts"]
    open1, open2 = bcfg["opening_balances"][acc1], bcfg["opening_balances"][acc2]

    # Load source tables
    gb = pd.read_csv(stage3_dir / "group_booking.csv")
    co = pd.read_csv(stage2_dir / "company.csv")
    ch = pd.read_csv(stage2_dir / "hidden" / "company_hidden.csv")
    ref = pd.read_csv(refund_path) if refund_path.exists() else pd.DataFrame(columns=["id", "ticket_sales_id", "refund_date", "refund_amount"])

    # Aggregate online daily sales for SETTLE lines
    settle_agg = {}
    tk_path = stage3_dir / "ticket_sales.csv"
    if tk_path.exists():
        for chk in pd.read_csv(tk_path, usecols=["purchase_date", "sales_channel_id", "total_price"], chunksize=500_000):
            online = chk[chk["sales_channel_id"].isin([4, 5, 6])]
            if not online.empty:
                daily = online.groupby("purchase_date")["total_price"].sum()
                for d, val in daily.items():
                    settle_agg[d] = settle_agg.get(d, 0) + int(val)

    # Join companies
    co_merged = co.merge(ch, left_on="id", right_on="company_id")
    gb = gb.merge(co_merged[["id", "late_probability", "mean_pay_lag_days"]], left_on="company_id", right_on="id", suffixes=("", "_co"))

    # Determine bank details per company
    n_co = len(co)
    banks = np.array(bcfg["sender_banks"])
    co_banks = dict(zip(co["id"], banks[rng.integers(0, len(banks), size=n_co)]))
    co_accs = dict(zip(co["id"], [f"0{rng.integers(100_000_000, 999_999_999)}" for _ in range(n_co)]))

    # Parse dates
    gb["doc_dt"] = pd.to_datetime(gb["document_date"])
    gb["due_dt"] = pd.to_datetime(gb["payment_due_date"])
    gb["first_dep"] = pd.to_datetime(gb["period"] + "-01")

    used_multi = set()
    multi_pairs = []
    checked_gb = gb[gb["status"] == "checked"].sort_values("doc_dt")
    target_multi_pairs = int(len(gb) * bcfg["patterns"]["multi_booking"] / 2)

    for cid, grp in checked_gb.groupby("company_id"):
        if len(multi_pairs) >= target_multi_pairs:
            break
        if len(grp) >= 2:
            rows = grp.to_dict("records")
            for i in range(len(rows) - 1):
                if rows[i]["id"] in used_multi or rows[i + 1]["id"] in used_multi:
                    continue
                diff = (rows[i + 1]["doc_dt"] - rows[i]["doc_dt"]).days
                if 0 <= diff <= 14:
                    multi_pairs.append((rows[i], rows[i + 1]))
                    used_multi.add(rows[i]["id"])
                    used_multi.add(rows[i + 1]["id"])
                    break

    name_modes = list(bcfg["sender_name_variants"].keys())
    name_probs = np.array(list(bcfg["sender_name_variants"].values()), dtype=float)
    msg_modes = list(bcfg["message_variants"].keys())
    msg_probs = np.array(list(bcfg["message_variants"].values()), dtype=float)

    raw_statements = []
    payments = []
    temp_stmt_id = 0
    max_date = pd.Timestamp("2025-12-31")

    # 1. Multi-booking transfers
    for b1, b2 in multi_pairs:
        temp_stmt_id += 1
        cid = b1["company_id"]
        cname = b1["counterparty_name"]
        amt = int(b1["total_amount"] + b2["total_amount"])
        is_late = rng.random() < b1["late_probability"]
        doc = max(b1["doc_dt"], b2["doc_dt"])
        due = min(b1["due_dt"], b2["due_dt"])
        if is_late:
            lag = max(1, int(round(rng.exponential(b1["mean_pay_lag_days"]))))
            tx_dt = due + pd.Timedelta(days=lag)
        else:
            tx_dt = doc + pd.Timedelta(days=int(rng.integers(1, 14)))
            tx_dt = min(tx_dt, due)
        tx_dt = min(tx_dt, max_date)

        acc = acc1 if rng.random() < bcfg["account_shares"][acc1] else acc2
        nm_mode = rng.choice(name_modes, p=name_probs)
        raw_statements.append({
            "temp_id": temp_stmt_id, "account_no": acc, "transaction_date": _dstr(tx_dt),
            "transaction_code": "TRF", "direction": "credit", "amount": float(amt),
            "sender_name": _corrupt_name(cname, nm_mode), "sender_account_no": co_accs[cid],
            "sender_bank": co_banks[cid], "message": f"Pembayaran {b1['booking_no']} & {b2['booking_no']}"
        })
        payments.append({"temp_stmt_id": temp_stmt_id, "group_booking_id": b1["id"], "payment_type": "full", "allocated_amount": float(b1["total_amount"])})
        payments.append({"temp_stmt_id": temp_stmt_id, "group_booking_id": b2["id"], "payment_type": "full", "allocated_amount": float(b2["total_amount"])})

    # 2. Individual bookings
    p_full = bcfg["patterns"]["full"]
    p_dep = bcfg["patterns"]["deposit_final"]
    p_inst = bcfg["patterns"]["instalments"]
    tot_pat = p_full + p_dep + p_inst
    pat_probs = np.array([p_full, p_dep, p_inst]) / tot_pat

    cutoff_pending = pd.Timestamp("2025-11-01")

    for r in gb.itertuples():
        if r.id in used_multi:
            continue
        cid = r.company_id
        cname = r.counterparty_name
        bno = r.booking_no
        amt = int(r.total_amount)
        doc, due = r.doc_dt, r.due_dt
        is_pending = r.status == "pending"
        is_recent_pending = is_pending and (doc >= cutoff_pending)

        if is_recent_pending:
            roll = rng.random()
            if roll < 0.40:
                continue  # completely unpaid
            elif roll < 0.75:
                # deposit only
                temp_stmt_id += 1
                dep_amt = max(10000, min(amt - 10000, int(round(amt * 0.30 / 10000) * 10000)))
                tx_dt = min(doc + pd.Timedelta(days=int(rng.integers(1, 5))), max_date)
                acc = acc1 if rng.random() < bcfg["account_shares"][acc1] else acc2
                raw_statements.append({
                    "temp_id": temp_stmt_id, "account_no": acc, "transaction_date": _dstr(tx_dt),
                    "transaction_code": "TRF", "direction": "credit", "amount": float(dep_amt),
                    "sender_name": _corrupt_name(cname, rng.choice(name_modes, p=name_probs)),
                    "sender_account_no": co_accs[cid], "sender_bank": co_banks[cid],
                    "message": _corrupt_msg(bno, cname, "deposit", rng.choice(msg_modes, p=msg_probs))
                })
                payments.append({"temp_stmt_id": temp_stmt_id, "group_booking_id": r.id, "payment_type": "deposit", "allocated_amount": float(dep_amt)})
                continue

        # Normal clean booking
        pat = rng.choice(["full", "deposit_final", "instalments"], p=pat_probs)
        is_late = rng.random() < r.late_probability
        acc = acc1 if rng.random() < bcfg["account_shares"][acc1] else acc2

        if pat == "full":
            temp_stmt_id += 1
            if is_late:
                lag = max(1, int(round(rng.exponential(r.mean_pay_lag_days))))
                tx_dt = due + pd.Timedelta(days=lag)
            else:
                tx_dt = doc + pd.Timedelta(days=int(rng.integers(1, 14)))
                tx_dt = min(tx_dt, due)
            tx_dt = min(tx_dt, max_date)

            raw_statements.append({
                "temp_id": temp_stmt_id, "account_no": acc, "transaction_date": _dstr(tx_dt),
                "transaction_code": "TRF", "direction": "credit", "amount": float(amt),
                "sender_name": _corrupt_name(cname, rng.choice(name_modes, p=name_probs)),
                "sender_account_no": co_accs[cid], "sender_bank": co_banks[cid],
                "message": _corrupt_msg(bno, cname, "full", rng.choice(msg_modes, p=msg_probs))
            })
            payments.append({"temp_stmt_id": temp_stmt_id, "group_booking_id": r.id, "payment_type": "full", "allocated_amount": float(amt)})

        elif pat == "deposit_final":
            dep_pct = rng.uniform(bcfg["deposit_pct_range"][0], bcfg["deposit_pct_range"][1])
            dep_amt = max(10000, min(amt - 10000, int(round(amt * dep_pct / 10000) * 10000)))
            fin_amt = amt - dep_amt

            dt1 = min(doc + pd.Timedelta(days=int(rng.integers(1, 6))), max_date)
            if is_late:
                lag = max(1, int(round(rng.exponential(r.mean_pay_lag_days))))
                dt2 = due + pd.Timedelta(days=lag)
            else:
                dt2 = dt1 + pd.Timedelta(days=int(rng.integers(1, 9)))
                dt2 = min(dt2, due)
            dt2 = max(dt1, min(dt2, max_date))

            temp_stmt_id += 1
            raw_statements.append({
                "temp_id": temp_stmt_id, "account_no": acc, "transaction_date": _dstr(dt1),
                "transaction_code": "TRF", "direction": "credit", "amount": float(dep_amt),
                "sender_name": _corrupt_name(cname, rng.choice(name_modes, p=name_probs)),
                "sender_account_no": co_accs[cid], "sender_bank": co_banks[cid],
                "message": _corrupt_msg(bno, cname, "deposit", rng.choice(msg_modes, p=msg_probs))
            })
            payments.append({"temp_stmt_id": temp_stmt_id, "group_booking_id": r.id, "payment_type": "deposit", "allocated_amount": float(dep_amt)})

            temp_stmt_id += 1
            raw_statements.append({
                "temp_id": temp_stmt_id, "account_no": acc, "transaction_date": _dstr(dt2),
                "transaction_code": "TRF", "direction": "credit", "amount": float(fin_amt),
                "sender_name": _corrupt_name(cname, rng.choice(name_modes, p=name_probs)),
                "sender_account_no": co_accs[cid], "sender_bank": co_banks[cid],
                "message": _corrupt_msg(bno, cname, "final", rng.choice(msg_modes, p=msg_probs))
            })
            payments.append({"temp_stmt_id": temp_stmt_id, "group_booking_id": r.id, "payment_type": "final", "allocated_amount": float(fin_amt)})

        else:  # instalments (3 parts)
            a1 = max(10000, int(round(amt * 0.35 / 10000) * 10000))
            a2 = max(10000, int(round(amt * 0.35 / 10000) * 10000))
            if a1 + a2 >= amt:
                a1 = amt // 3
                a2 = amt // 3
            a3 = amt - a1 - a2

            dt1 = min(doc + pd.Timedelta(days=int(rng.integers(1, 4))), max_date)
            dt2 = min(dt1 + pd.Timedelta(days=int(rng.integers(3, 7))), max_date)
            if is_late:
                lag = max(1, int(round(rng.exponential(r.mean_pay_lag_days))))
                dt3 = due + pd.Timedelta(days=lag)
            else:
                dt3 = min(dt2 + pd.Timedelta(days=int(rng.integers(3, 7))), due)
            dt3 = max(dt2, min(dt3, max_date))

            for a_part, dt_part in [(a1, dt1), (a2, dt2), (a3, dt3)]:
                temp_stmt_id += 1
                raw_statements.append({
                    "temp_id": temp_stmt_id, "account_no": acc, "transaction_date": _dstr(dt_part),
                    "transaction_code": "TRF", "direction": "credit", "amount": float(a_part),
                    "sender_name": _corrupt_name(cname, rng.choice(name_modes, p=name_probs)),
                    "sender_account_no": co_accs[cid], "sender_bank": co_banks[cid],
                    "message": _corrupt_msg(bno, cname, "instalment", rng.choice(msg_modes, p=msg_probs))
                })
                payments.append({"temp_stmt_id": temp_stmt_id, "group_booking_id": r.id, "payment_type": "instalment", "allocated_amount": float(a_part)})

    # 3. SETTLE lines (daily online sales of previous day)
    for pdate_str, s_amt in sorted(settle_agg.items()):
        if s_amt <= 0:
            continue
        tx_dt = pd.Timestamp(pdate_str) + pd.Timedelta(days=1)
        if tx_dt <= max_date:
            temp_stmt_id += 1
            raw_statements.append({
                "temp_id": temp_stmt_id, "account_no": acc1, "transaction_date": _dstr(tx_dt),
                "transaction_code": "SETTLE", "direction": "credit", "amount": float(s_amt),
                "sender_name": "PT MIDTRANS INDONESIA", "sender_account_no": "014-99887766",
                "sender_bank": "BCA", "message": f"SETTLEMENT ONLINE SALES {pdate_str}"
            })

    # 4. REFUND lines
    if not ref.empty:
        valid_refs = ref[ref["refund_amount"] > 0]
        for r_row in valid_refs.itertuples():
            temp_stmt_id += 1
            raw_statements.append({
                "temp_id": temp_stmt_id, "account_no": acc1, "transaction_date": str(r_row.refund_date),
                "transaction_code": "REFUND", "direction": "debit", "amount": float(r_row.refund_amount),
                "sender_name": "", "sender_account_no": "", "sender_bank": "",
                "message": f"REFUND TICKET {r_row.ticket_sales_id}"
            })

    # 5. Monthly FEE and INT lines (28th of every month)
    months = pd.date_range("2020-01-01", "2025-12-31", freq="MS")
    fee1, fee2 = bcfg["monthly_fees"][acc1], bcfg["monthly_fees"][acc2]
    int_rate = bcfg["monthly_interest_rate"]

    for m in months:
        d28 = m.strftime("%Y-%m-28")
        for acc, fee, op_bal in [(acc1, fee1, open1), (acc2, fee2, open2)]:
            temp_stmt_id += 1
            raw_statements.append({
                "temp_id": temp_stmt_id, "account_no": acc, "transaction_date": d28,
                "transaction_code": "FEE", "direction": "debit", "amount": float(fee),
                "sender_name": "", "sender_account_no": "", "sender_bank": "",
                "message": "BIAYA ADMINISTRASI BANK"
            })
            temp_stmt_id += 1
            int_amt = round(op_bal * int_rate, 2)
            raw_statements.append({
                "temp_id": temp_stmt_id, "account_no": acc, "transaction_date": d28,
                "transaction_code": "INT", "direction": "credit", "amount": float(int_amt),
                "sender_name": "", "sender_account_no": "", "sender_bank": "",
                "message": "BUNGA REKENING"
            })

    stmt_df = pd.DataFrame(raw_statements)
    prio_map = {"SETTLE": 1, "TRF": 1, "REFUND": 2, "FEE": 2, "INT": 3}
    stmt_df["prio"] = stmt_df["transaction_code"].map(prio_map)
    stmt_df.sort_values(["account_no", "transaction_date", "prio", "temp_id"], inplace=True)
    stmt_df.reset_index(drop=True, inplace=True)

    balances = np.empty(len(stmt_df), dtype=float)
    for acc, open_b in [(acc1, open1), (acc2, open2)]:
        m = stmt_df["account_no"] == acc
        if not m.any():
            continue
        sub_amt = stmt_df.loc[m, "amount"].to_numpy()
        sub_dir = stmt_df.loc[m, "direction"].to_numpy()
        signed = np.where(sub_dir == "credit", sub_amt, -sub_amt)
        bals = open_b + np.cumsum(signed)
        balances[m] = np.round(bals, 2)

    stmt_df["balance"] = balances

    stmt_df.sort_values(["transaction_date", "account_no", "prio", "temp_id"], inplace=True)
    stmt_df.reset_index(drop=True, inplace=True)

    stmt_df["id"] = np.arange(1, len(stmt_df) + 1, dtype=np.int64)
    temp_to_real = dict(zip(stmt_df["temp_id"], stmt_df["id"]))

    out_stmt = stmt_df[[
        "id", "account_no", "transaction_date", "transaction_code", "direction",
        "amount", "balance", "sender_name", "sender_account_no", "sender_bank", "message"
    ]]

    pay_df = pd.DataFrame(payments)
    pay_df["bank_statement_id"] = pay_df["temp_stmt_id"].map(temp_to_real)
    out_pay = pay_df[["bank_statement_id", "group_booking_id", "payment_type", "allocated_amount"]]
    out_pay = out_pay.sort_values(["bank_statement_id", "group_booking_id"], ignore_index=True)

    return out_stmt, out_pay
