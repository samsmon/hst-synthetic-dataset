"""Stage 2 report: headcount, promos and trip load factors."""
import numpy as np
import pandas as pd

from .report import _md_table

DEPARTMENT = {1: "Ticketing", 2: "Ticketing", 3: "Ticketing", 4: "Ticketing", 5: "Station Operations",
              6: "Station Operations", 7: "Station Operations", 8: "Customer Service", 9: "Customer Service",
              10: "Sales", 11: "Sales", 12: "Finance", 13: "Finance", 14: "Finance", 15: "Finance"}
STATION = {1: "Halim", 2: "Karawang", 3: "Padalarang", 4: "Tegalluar"}


def _active_on(emp: pd.DataFrame, day) -> pd.Series:
    return (emp["hire_date"] <= day) & (emp["end_date"].isna() | (emp["end_date"] > day))


def summarize_stage2(t: dict) -> str:
    emp, hist, promo, trips, comp = t["employee"], t["employee_history"], t["promo"], t["trip"], t["company"]
    out = []

    rows = []
    for y in range(2020, 2026):
        end = pd.Timestamp(f"{y}-12-31").date()
        rows.append({"year": y, "active_at_year_end": int(_active_on(emp, end).sum()),
                     "hired": int(((emp["hire_date"] >= pd.Timestamp(f"{y}-01-01").date()) & (emp["hire_date"] <= end)).sum()),
                     "left": int(((emp["end_date"] >= pd.Timestamp(f"{y}-01-01").date()) & (emp["end_date"] <= end)).sum())})
    out += ["## Employees per year", _md_table(pd.DataFrame(rows)),
            f"- employees ever: {len(emp)}, history rows: {len(hist)}, promotions: {t['emp_stats']['promotions']}, "
            f"transfers: {t['emp_stats']['transfers']}",
            f"- contract share: {(emp['employment_status'] == 'contract').mean():.2f}, "
            f"with a supervisor: {emp['supervisor_id'].notna().mean():.2f}", ""]

    now = emp[_active_on(emp, pd.Timestamp("2025-12-31").date())].copy()
    now["department"] = now["job_position_id"].map(DEPARTMENT)
    now["station"] = now["home_station_id"].map(STATION).fillna("HQ (no station)")
    out += ["## Active at 2025-12-31 by department", _md_table(now["department"].value_counts().rename_axis("department").reset_index(name="count")), ""]
    out += ["## Active at 2025-12-31 by station", _md_table(now["station"].value_counts().rename_axis("station").reset_index(name="count")), ""]
    sm = now[now["job_position_id"] == 7]["home_station_id"].value_counts()
    out += [f"- station masters per station (must be 1 each): {dict(sorted((STATION[k], int(v)) for k, v in sm.items()))}", ""]

    p = promo.copy()
    p["year"] = pd.to_datetime(p["start_date"]).dt.year
    tab = p.pivot_table(index="year", columns="type", values="id", aggfunc="count", fill_value=0).reset_index()
    out += ["## Promos per year by type", _md_table(tab), ""]
    deals = promo[(promo["type"] == "monthly_deal") & (pd.to_datetime(promo["start_date"]).dt.year == 2024)]
    show = deals[["name", "applies_to", "min_pax", "route_id", "discount_pct", "start_date", "end_date"]]
    out += ["## Monthly deals in 2024 (sample year)", _md_table(show), ""]
    g = promo[promo["applies_to"] == "group"]
    out += [f"- group promos: {len(g)}, smallest min_pax: {int(g['min_pax'].min())}, "
            f"discounts {sorted(g['discount_pct'].unique().tolist())}", ""]

    tr = trips.copy()
    tr["year"] = pd.to_datetime(tr["service_date"]).dt.year
    tr["lf"] = tr["_demand_dir"] / tr["seat_capacity"]
    rows = []
    for y, g in tr.groupby("year"):
        days = g["service_date"].nunique()
        rows.append({"year": y, "trips": len(g), "per_day": round(len(g) / days, 1),
                     "lf_mean": round(g["lf"].mean(), 2), "lf_p10": round(g["lf"].quantile(0.10), 2),
                     "lf_p90": round(g["lf"].quantile(0.90), 2), "lf_max": round(g["lf"].max(), 2)})
    out += ["## Trips per year and planned load factor", _md_table(pd.DataFrame(rows)),
            f"- total trips: {len(tr)}, capacities: {tr['seat_capacity'].value_counts().to_dict()}", ""]
    busiest = tr.groupby("service_date").size().nlargest(3)
    out += [f"- most runs in a day: {dict((str(k), int(v)) for k, v in busiest.items())}", ""]

    out += ["## Companies", _md_table(comp["type"].value_counts().rename_axis("type").reset_index(name="count")),
            f"- total {len(comp)}, cities {comp['city'].nunique()}, joined {comp['joined_date'].min()} to {comp['joined_date'].max()}", ""]
    return "\n".join(out)
