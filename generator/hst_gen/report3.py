"""Stage 3 report, built from the running aggregates (no need to read the big CSV back)."""
import numpy as np
import pandas as pd

from .report import _md_table

CHANNELS = {1: "counter", 2: "group desk", 3: "FCC desk", 4: "agent", 5: "app", 6: "web"}


def summarize_stage3(ctx, stats, truth: pd.DataFrame, seconds: float) -> str:
    m = pd.DataFrame(stats.rows)
    first = m["month_id"].min()
    m["year"] = 2020 + (m["month_id"] - first) // 12
    m["share"] = m["group"] / m["tickets"]
    out = [f"- run time {seconds:.0f} s for {int(m['tickets'].sum()):,} tickets, "
           f"{int(m['new_customers'].sum()):,} customers, {int(m['bookings'].sum()):,} group bookings", ""]

    y = m.groupby("year").agg(tickets=("tickets", "sum"), group=("group", "sum"), bookings=("bookings", "sum"),
                              new_customers=("new_customers", "sum"), pending=("pending_bookings", "sum")).reset_index()
    y["group_share_%"] = (100 * y["group"] / y["tickets"]).round(1)
    out += ["## Per year", _md_table(y),
            f"- monthly group share: min {m['share'].min():.3f}, max {m['share'].max():.3f}, "
            f"months outside 15 to 35 percent: {int(((m['share'] < 0.15) | (m['share'] > 0.35)).sum())}",
            f"- staffed tickets without an employee: {int(m['staffed_without_employee'].sum())}", ""]

    c = pd.concat(stats.by_year_channel).groupby(["year", "channel"], as_index=False).sum(numeric_only=True)
    pivot = c.pivot(index="year", columns="channel", values="n").fillna(0)
    share = (100 * pivot.div(pivot.sum(axis=1), axis=0)).round(1).rename(columns=CHANNELS).reset_index()
    out += ["## Sales channel mix per year (percent of tickets)", _md_table(share), ""]

    k = pd.concat(stats.by_year_channel).groupby(["year", "kind"], as_index=False).sum(numeric_only=True)
    k["avg_discount_%"] = (k["disc"] / k["n"]).round(2)
    k["avg_price"] = (k["price"] / k["n"]).round(0).astype(int)
    out += ["## Average discount and price", _md_table(k[["year", "kind", "n", "avg_discount_%", "avg_price"]]), ""]

    w = pd.concat(stats.by_window).groupby(["window", "kind"], as_index=False).sum(numeric_only=True)
    w["avg_discount_%"] = (w["disc"] / w["n"]).round(2)
    out += ["## Average discount by period (smaller when crowded)", _md_table(w[["window", "kind", "n", "avg_discount_%"]]), ""]

    sizes = np.concatenate(stats.booking_sizes) if stats.booking_sizes else np.array([0])
    out += ["## Group bookings",
            f"- passengers per booking: min {sizes.min()}, median {int(np.median(sizes))}, mean {sizes.mean():.1f}, "
            f"p95 {int(np.quantile(sizes, 0.95))}, max {sizes.max()}",
            f"- pending bookings: {int(m['pending_bookings'].sum())}", ""]

    cap = ctx.tables["trip"].set_index("id")["seat_capacity"]
    used = pd.Series(stats.trip_count[: int(cap.index.max()) + 1]).reindex(cap.index)
    lf = used / cap
    out += ["## Trips (actual tickets against seats)",
            f"- trips {len(cap):,}, mean {used.mean():.0f} tickets, mean load factor {lf.mean():.2f}, "
            f"p10 {lf.quantile(0.1):.2f}, p90 {lf.quantile(0.9):.2f}, max {lf.max():.2f}, over capacity: {int((lf > 1).sum())}", ""]

    seg = truth["segment"].value_counts().rename_axis("segment").reset_index(name="customers")
    churned = int(truth["churn_date"].notna().sum())
    out += ["## Customers (generator segments)", _md_table(seg),
            f"- commuters who churned: {churned}, total customers {len(truth):,}", ""]
    return "\n".join(out)
