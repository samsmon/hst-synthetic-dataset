"""Runs stage 3 month by month, streams CSV files and collects the numbers for the report."""
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .ctx import build_context
from .tickets import State, generate_month

TABLES = ["ticket_sales", "group_booking", "group_booking_detail", "customer", "refund"]


class Stats:
    """Small running aggregates, so the full ticket table never has to be read back."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.rows = []                       # per month
        self.by_year_channel = []            # year, kind, channel, n, discount sum, price sum
        self.by_window = []                  # window label, kind, n, discount sum
        self.trip_count = np.zeros(int(ctx.tables["trip"]["id"].max()) + 2, dtype=np.int64)
        self.booking_sizes = []
        self.group_months = []
        cal = ctx.tables["cal"]
        label = np.where(cal["is_lebaran_window"], "lebaran", np.where(cal["is_year_end"], "year_end",
                         np.where(cal["is_school_holiday"], "school_holiday", "regular")))
        self.window = dict(zip(cal["date"].dt.strftime("%Y-%m-%d"), label))

    def add(self, month_id: int, res: dict, took: float):
        t = res["ticket_sales"]
        kind = np.where(t["group_booking_id"].ne("") | np.isin(t["order_id"].str[:4], ["BAK-"]), "group", "individual")
        year = t["departure_date"].str[:4].astype(int)
        disc = t["discount_pct"].to_numpy()
        df = pd.DataFrame({"year": year, "kind": kind, "channel": t["sales_channel_id"], "disc": disc, "price": t["total_price"]})
        g = df.groupby(["year", "kind", "channel"]).agg(n=("disc", "size"), disc=("disc", "sum"), price=("price", "sum")).reset_index()
        self.by_year_channel.append(g)
        w = pd.DataFrame({"window": t["departure_date"].map(self.window), "kind": kind, "disc": disc})
        self.by_window.append(w.groupby(["window", "kind"]).agg(n=("disc", "size"), disc=("disc", "sum")).reset_index())
        np.add.at(self.trip_count, t["trip_id"].to_numpy(), 1)
        issued = t["issued_by_employee_id"].ne("")
        staffed = t["sales_channel_id"].isin([1, 2, 3])
        gb = res.get("group_booking")
        if gb is not None:
            self.booking_sizes.append(gb["passenger_count"].to_numpy())
        self.rows.append({
            "month_id": month_id, "tickets": len(t), "group": res["n_group"], "individual": res["n_individual"],
            "new_customers": 0 if "customer" not in res else len(res["customer"]),
            "bookings": 0 if gb is None else len(gb), "pending_bookings": res["pending"],
            "staffed_without_employee": int((staffed & ~issued).sum()), "seconds": round(took, 2)})


def run_stage3(cfg: dict, out: Path, seed: int | None = None, months: tuple | None = None, progress: bool = True):
    t0 = time.perf_counter()
    ctx = build_context(cfg, seed)
    st, stats = State(ctx), Stats(ctx)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "hidden").mkdir(exist_ok=True)
    for name in TABLES:
        (out / f"{name}.csv").unlink(missing_ok=True)
    (out / "hidden" / "ticket_group_truth.csv").unlink(missing_ok=True)
    first = dict.fromkeys(TABLES + ["ticket_group_truth"], True)

    def write(name, df, path):
        df.to_csv(path, mode="w" if first[name] else "a", header=first[name], index=False)
        first[name] = False

    month_list = list(ctx.month_rows)[slice(*months)] if months else list(ctx.month_rows)
    for i, m in enumerate(month_list, start=1):
        t1 = time.perf_counter()
        res = generate_month(st, m)
        for name in TABLES:
            if res.get(name) is not None:
                write(name, res[name], out / f"{name}.csv")
        if res.get("ticket_group_truth") is not None and len(res["ticket_group_truth"]):
            write("ticket_group_truth", res["ticket_group_truth"], out / "hidden" / "ticket_group_truth.csv")
        stats.add(m, res, time.perf_counter() - t1)
        if progress and (i % 6 == 0 or i == len(month_list)):
            print(f"  month {i}/{len(month_list)}  tickets so far {sum(r['tickets'] for r in stats.rows):,}  "
                  f"elapsed {time.perf_counter() - t0:.0f}s", flush=True)
    truth = st.book.truth_frame()
    truth.to_csv(out / "hidden" / "customer_truth.csv", index=False)
    return ctx, stats, truth, time.perf_counter() - t0
