"""Stage 1 report: a markdown summary and a dependency-free SVG chart."""
import numpy as np
import pandas as pd


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.astype(object).itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def summarize(long: pd.DataFrame, cal: pd.DataFrame, shares: dict) -> str:
    day = long.groupby("date")[["tickets", "group_tickets"]].sum().reset_index().merge(cal, on="date")
    out = []

    yearly = day.groupby("year").agg(tickets=("tickets", "sum"), group=("group_tickets", "sum"))
    yearly["group_share_%"] = (100 * yearly["group"] / yearly["tickets"]).round(1)
    yearly["avg_per_day"] = (yearly["tickets"] / day.groupby("year").size()).round(0).astype(int)
    out += ["## Tickets per year", _md_table(yearly.reset_index()), ""]

    phase = day.groupby("covid_phase")["tickets"].mean()
    base = phase.get("normal", np.nan)
    order = [p for p in ["pre", "lockdown", "restrictions", "recovery", "normal"] if p in phase.index]
    ph = pd.DataFrame({"phase": order, "avg_tickets_per_day": [round(phase[p]) for p in order],
                       "vs_normal_%": [round(100 * phase[p] / base) for p in order]})
    out += ["## COVID phases", _md_table(ph), ""]

    month = day.groupby("month_id").agg(t=("tickets", "sum"), g=("group_tickets", "sum"))
    month["share"] = month["g"] / month["t"]
    out += ["## Group share per month",
            f"- months: {len(month)}, realised share min {month['share'].min():.3f}, "
            f"max {month['share'].max():.3f}, mean {month['share'].mean():.3f}",
            f"- months with zero group tickets: {int((month['g'] == 0).sum())}", ""]

    rows = []
    for leb in sorted(day.loc[day["lebaran_offset"] == 0, "date"]):
        near = day[(day["date"] - leb).abs() <= pd.Timedelta(days=45)]
        win = near[near["is_lebaran_window"]]["tickets"].mean()
        ref = near[(near["lebaran_offset"] <= -15) & (near["lebaran_offset"] >= -35)]["tickets"].mean()
        peak = near.loc[near["tickets"].idxmax()]
        rows.append({"lebaran": leb.date(), "window_avg": round(win), "reference_avg": round(ref),
                     "ratio": round(win / ref, 2), "peak_day": peak["date"].date(), "peak": int(peak["tickets"])})
    out += ["## Lebaran windows (H-7..H+7 against H-35..H-15)", _md_table(pd.DataFrame(rows)), ""]

    ye = day[day["is_year_end"]].groupby("year")["tickets"].mean()
    out += ["## Year-end window average per day (Dec 20 to Jan 3)", _md_table(ye.round().astype(int).reset_index()), ""]

    wd = day[day["year"] >= 2023].groupby("dow")["tickets"].mean()
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out += ["## Weekday profile (2023 to 2025, average per day)",
            _md_table(pd.DataFrame({"day": names, "avg": wd.round().astype(int).values})), ""]

    top = day.nlargest(10, "tickets")[["date", "tickets", "covid_phase"]]
    top["date"] = top["date"].dt.date
    out += ["## Ten busiest days", _md_table(top), ""]
    return "\n".join(out)


def svg_chart(long: pd.DataFrame, cal: pd.DataFrame) -> str:
    """Two panels: tickets per month, and group share per month with the 15 to 35 percent band."""
    day = long.groupby("date")[["tickets", "group_tickets"]].sum().reset_index().merge(cal[["date", "month_id"]], on="date")
    m = day.groupby("month_id").agg(t=("tickets", "sum"), g=("group_tickets", "sum"))
    share = (m["g"] / m["t"]).values
    tickets = m["t"].values
    n = len(m)
    w, h, left, right, gap = 900, 520, 60, 20, 60
    pw = w - left - right
    ph = (h - 3 * 30 - gap) / 2

    def x(i):
        return left + pw * i / (n - 1)

    def panel(vals, ymax, top, label, fmt):
        y = lambda v: top + ph - ph * v / ymax
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        grid = "".join(f'<line x1="{left}" x2="{w - right}" y1="{y(ymax * k / 4):.1f}" y2="{y(ymax * k / 4):.1f}" stroke="#ddd"/>'
                       f'<text x="{left - 6}" y="{y(ymax * k / 4) + 4:.1f}" text-anchor="end" font-size="11" fill="#555">{fmt(ymax * k / 4)}</text>'
                       for k in range(5))
        return (f'<text x="{left}" y="{top - 8}" font-size="13" font-weight="bold" fill="#222">{label}</text>{grid}'
                f'<polyline points="{pts}" fill="none" stroke="#1f6feb" stroke-width="2"/>')

    p1 = panel(tickets, tickets.max() * 1.05, 40, "Tickets per month", lambda v: f"{v / 1000:.0f}k")
    top2 = 40 + ph + gap
    p2 = panel(share, 0.5, top2, "Group share per month (band 15 to 35 percent)", lambda v: f"{v * 100:.0f}%")
    y2 = lambda v: top2 + ph - ph * v / 0.5
    band = f'<rect x="{left}" y="{y2(0.35):.1f}" width="{pw}" height="{y2(0.15) - y2(0.35):.1f}" fill="#1f6feb" opacity="0.08"/>'
    years = "".join(f'<text x="{x(i):.1f}" y="{h - 8}" text-anchor="middle" font-size="11" fill="#555">{2020 + i // 12}</text>'
                    for i in range(0, n, 12))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="sans-serif">'
            f'<rect width="{w}" height="{h}" fill="white"/>{p1}{band}{p2}{years}</svg>')
