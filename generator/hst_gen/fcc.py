"""Derive FCC cards and redemptions from ticket_sales channel 3 (FCC desk)."""
from pathlib import Path
import numpy as np
import pandas as pd

from . import rng as rnglib
from .staff import StaffIndex


def _dstr(a: np.ndarray) -> np.ndarray:
    return np.datetime_as_string(a, unit="D")


def build_fcc(ticket_sales_path: Path, employee_history: pd.DataFrame, cfg: dict, seed: int):
    """Reads ticket_sales in chunks, extracts channel 3 tickets, and builds fcc_card and fcc_redemption."""
    rng = rnglib.stream(seed, "stage4.fcc")
    fcc_cfg = cfg["stage4"]["fcc"]

    cols = ["id", "order_id", "customer_id", "route_id", "purchase_date",
            "departure_date", "sales_channel_id", "issued_by_employee_id"]
    chunks = []
    for chunk in pd.read_csv(ticket_sales_path, usecols=cols, chunksize=500_000):
        m = chunk["sales_channel_id"] == 3
        if m.any():
            chunks.append(chunk[m])

    if not chunks:
        empty_card = pd.DataFrame(columns=[
            "id", "card_no", "customer_id", "registration_date", "expiry_date",
            "route_id", "card_type", "initial_quota", "remaining_quota", "registered_by_employee_id"
        ])
        empty_red = pd.DataFrame(columns=[
            "id", "order_id", "card_id", "ticket_sales_id", "departure_date",
            "redeemed_by_employee_id", "redeemed_at"
        ])
        return empty_card, empty_red

    df = pd.concat(chunks, ignore_index=True)
    df.sort_values(["customer_id", "purchase_date", "id"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    n = len(df)
    cust_arr = df["customer_id"].to_numpy(dtype=np.int64)
    purch_arr = pd.to_datetime(df["purchase_date"]).to_numpy().astype("datetime64[D]")
    tid_arr = df["id"].to_numpy(dtype=np.int64)
    oid_arr = df["order_id"].to_numpy()
    route_arr = df["route_id"].to_numpy(dtype=np.int64)
    dep_arr = df["departure_date"].to_numpy()
    emp_arr = df["issued_by_employee_id"].to_numpy(dtype=np.int64)

    card_ids_for_red = np.empty(n, dtype=np.int64)
    card_customers = []
    card_reg_dates = []
    card_exp_dates = []
    card_routes = []
    card_types = []
    card_init_quotas = []

    p_g = fcc_cfg["type_share"]["G"]
    v_days = {
        "G": np.timedelta64(fcc_cfg["validity_days"]["G"], "D"),
        "S": np.timedelta64(fcc_cfg["validity_days"]["S"], "D"),
    }
    q_map = {"G": fcc_cfg["quota"]["G"], "S": fcc_cfg["quota"]["S"]}

    rand_types = rng.random(n) < p_g
    card_idx = 0
    curr_card_id = 0
    curr_cust = -1
    curr_exp = np.datetime64("1970-01-01", "D")
    curr_used = 0
    curr_quota = 0

    for i in range(n):
        c = cust_arr[i]
        d = purch_arr[i]
        if c != curr_cust or d > curr_exp or curr_used >= curr_quota:
            curr_card_id += 1
            curr_cust = c
            ctype = "G" if rand_types[card_idx] else "S"
            card_idx += 1
            curr_quota = q_map[ctype]
            curr_used = 0
            curr_exp = d + v_days[ctype]

            card_customers.append(c)
            card_reg_dates.append(d)
            card_exp_dates.append(curr_exp)
            card_routes.append(route_arr[i])
            card_types.append(ctype)
            card_init_quotas.append(curr_quota)

        curr_used += 1
        card_ids_for_red[i] = curr_card_id

    n_cards = curr_card_id
    card_reg_arr = np.array(card_reg_dates, dtype="datetime64[D]")
    card_exp_arr = np.array(card_exp_dates, dtype="datetime64[D]")
    card_init_arr = np.array(card_init_quotas, dtype=np.int64)

    # Remaining quota = initial - redemptions
    counts = np.bincount(card_ids_for_red, minlength=n_cards + 1)[1:]
    rem_quota = card_init_arr - counts

    # Registration staff: Customer Service Officer (job_position 8) on duty
    staff_cs = StaffIndex(employee_history, [8])
    reg_emp, _ = staff_cs.pick(card_reg_arr, rng)

    card_ids = np.arange(1, n_cards + 1, dtype=np.int64)
    card_no = np.char.add("FCC", np.char.zfill(card_ids.astype("U12"), 8))

    cards_df = pd.DataFrame({
        "id": card_ids,
        "card_no": card_no,
        "customer_id": np.array(card_customers, dtype=np.int64),
        "registration_date": _dstr(card_reg_arr),
        "expiry_date": _dstr(card_exp_arr),
        "route_id": np.array(card_routes, dtype=np.int64),
        "card_type": np.array(card_types),
        "initial_quota": card_init_arr,
        "remaining_quota": rem_quota,
        "registered_by_employee_id": np.where(reg_emp > 0, reg_emp.astype("U20"), ""),
    })

    # Redemptions
    red_mins = rng.integers(360, 1260, size=n)
    red_secs = rng.integers(0, 60, size=n)
    hh = red_mins // 60
    mm = red_mins % 60
    t_str = np.char.add(np.char.zfill(hh.astype("U2"), 2),
                        np.char.add(":", np.char.add(np.char.zfill(mm.astype("U2"), 2),
                                                    np.char.add(":", np.char.zfill(red_secs.astype("U2"), 2)))))
    redeemed_at = np.char.add(_dstr(purch_arr), np.char.add(" ", np.char.add(t_str, "+07:00")))

    red_df = pd.DataFrame({
        "id": np.arange(1, n + 1, dtype=np.int64),
        "order_id": oid_arr,
        "card_id": card_ids_for_red,
        "ticket_sales_id": tid_arr,
        "departure_date": dep_arr,
        "redeemed_by_employee_id": np.where(emp_arr > 0, emp_arr.astype("U20"), ""),
        "redeemed_at": redeemed_at,
    })

    return cards_df, red_df
