"""Ticket status assignment and refund generation."""
import numpy as np
import pandas as pd

TIME_D = "datetime64[D]"


def _dstr(a: np.ndarray) -> np.ndarray:
    return np.datetime_as_string(a, unit="D")


def process_status_and_refunds(tid: np.ndarray, purch_dates: np.ndarray, dep_dates: np.ndarray,
                               totals: np.ndarray, channels: np.ndarray, is_group: np.ndarray,
                               as_of: np.datetime64, cfg: dict, staff_cs, rng: np.random.Generator, ids):
    """Assigns status (used, issued, cancelled, refunded) and creates refund rows."""
    N = len(tid)
    status = np.where(dep_dates <= as_of, "used", "issued").astype("U12")
    if N == 0:
        return status, None

    # Lockdown window: tickets bought before March 2020 departing March to June 2020
    ld_start, ld_end = np.datetime64(cfg["lockdown_window"][0]), np.datetime64(cfg["lockdown_window"][1])
    is_lockdown = (purch_dates < ld_start) & (dep_dates >= ld_start) & (dep_dates <= ld_end)

    # Cancellation probabilities
    p_norm = rng.uniform(cfg["normal_cancel_rate"][0], cfg["normal_cancel_rate"][1])
    p_lock = rng.uniform(cfg["lockdown_refund_rate"][0], cfg["lockdown_refund_rate"][1])
    p_grp = cfg["group_cancel_rate"]

    prob = np.where(is_lockdown, p_lock, np.where(is_group, p_grp, p_norm))
    # FCC desk tickets (channel 3) are card quota redemptions; keep them intact
    prob = np.where(channels == 3, 0.0, prob)

    cancelled = rng.random(N) < prob
    n_canc = int(cancelled.sum())
    if n_canc == 0:
        return status, None

    # Lockdown tickets are all refunded; normal cancelled split into refunded vs cancelled
    canc_idx = np.flatnonzero(cancelled)
    canc_lock = is_lockdown[canc_idx]
    is_ref_norm = rng.random(n_canc) < cfg["refund_share"]
    is_ref = np.where(canc_lock, True, is_ref_norm)

    ref_idx = canc_idx[is_ref]
    unref_idx = canc_idx[~is_ref]
    status[unref_idx] = "cancelled"
    status[ref_idx] = "refunded"

    n_ref = len(ref_idx)
    if n_ref == 0:
        return status, None

    r_tid = tid[ref_idx]
    r_purch = purch_dates[ref_idx]
    r_dep = dep_dates[ref_idx]
    r_tot = totals[ref_idx]
    r_chan = channels[ref_idx]
    r_is_lock = is_lockdown[ref_idx]

    # Refund date between purchase and departure
    gap = (r_dep - r_purch).astype(int)
    off = np.where(gap > 0, rng.integers(0, np.maximum(gap, 1) + 1), 0)
    r_date = r_purch + off.astype("timedelta64[D]")
    r_date = np.where(r_is_lock, np.maximum(r_date, ld_start), r_date)
    r_date = np.minimum(r_date, r_dep)

    # Reasons
    reason_cfg = cfg["reasons"]
    reasons_list = list(reason_cfg.keys())
    reason_p = np.array([reason_cfg[r]["share"] for r in reasons_list], dtype=float)
    reason_p /= reason_p.sum()
    norm_reasons = np.array(reasons_list)[rng.choice(len(reasons_list), size=n_ref, p=reason_p)]
    lock_reasons = np.where(rng.random(n_ref) < 0.85, "schedule_change", "customer_request")
    reasons = np.where(r_is_lock, lock_reasons, norm_reasons)

    # Fees and amounts
    fee_pct = np.array([reason_cfg[r]["fee_pct"] for r in reasons])
    fee = np.round(r_tot * fee_pct).astype(np.int64)
    ref_amount = r_tot - fee

    # Processing staff: online (4, 5, 6) mostly NULL, staffed channels get CS officer on duty
    emp, _ = staff_cs.pick(r_date, rng)
    online = np.isin(r_chan, [4, 5, 6])
    has_emp = ~online | (rng.random(n_ref) < cfg["online_cs_processed_share"])
    proc_emp = np.where(has_emp & (emp > 0), emp.astype("U20"), "")

    refund_df = pd.DataFrame({
        "id": ids.take("refund", n_ref),
        "ticket_sales_id": r_tid,
        "refund_date": _dstr(r_date),
        "refund_amount": ref_amount,
        "refund_fee": fee,
        "reason": reasons,
        "processed_by_employee_id": proc_emp,
    })
    return status, refund_df
