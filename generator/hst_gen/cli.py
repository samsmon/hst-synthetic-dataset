"""Command line entry: python -m hst_gen <command>."""
import argparse
import time
from pathlib import Path

from . import config as cfglib
from .demand import build_demand
from .pipeline import export_tables, run_stage2
from .report import summarize, svg_chart
from .report2 import summarize_stage2
from .report3 import summarize_stage3
from .stage3 import run_stage3


def cmd_demand(args, cfg):
    t0 = time.perf_counter()
    long, cal, shares = build_demand(cfg)
    took = time.perf_counter() - t0
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    long.to_csv(out / "stage1_demand.csv", index=False)
    (out / "stage1_summary.md").write_text(summarize(long, cal, shares), encoding="utf-8")
    (out / "stage1_demand.svg").write_text(svg_chart(long, cal), encoding="utf-8")
    print(f"stage 1 done in {took:.2f}s: {int(long['tickets'].sum()):,} tickets, "
          f"{int(long['group_tickets'].sum()):,} group, files in {out}")


def cmd_stage2(args, cfg):
    t0 = time.perf_counter()
    tables = run_stage2(cfg)
    took = time.perf_counter() - t0
    out = Path(args.out) / "stage2"
    export_tables(tables, out, ["employee", "employee_history", "company", "promo", "trip"])
    (out / "stage2_summary.md").write_text(summarize_stage2(tables), encoding="utf-8")
    print(f"stage 2 done in {took:.1f}s: {len(tables['employee'])} employees, {len(tables['company'])} companies, "
          f"{len(tables['promo'])} promos, {len(tables['trip'])} trips, files in {out}")


def cmd_stage3(args, cfg):
    out = Path(args.out) / "stage3"
    ctx, stats, truth, took = run_stage3(cfg, out)
    (out / "stage3_summary.md").write_text(summarize_stage3(ctx, stats, truth, took), encoding="utf-8")
    total = sum(r["tickets"] for r in stats.rows)
    print(f"stage 3 done in {took:.0f}s: {total:,} tickets, files in {out}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="hst_gen")
    p.add_argument("command", choices=["demand", "stage2", "stage3"])
    p.add_argument("--config", default=None)
    p.add_argument("--out", default="output")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--tickets", type=int, default=None)
    args = p.parse_args(argv)
    cfg = cfglib.load(args.config)
    if args.seed is not None:
        cfg["seed"] = args.seed
    if args.tickets is not None:
        cfg["target_tickets"] = args.tickets
    {"demand": cmd_demand, "stage2": cmd_stage2, "stage3": cmd_stage3}[args.command](args, cfg)
