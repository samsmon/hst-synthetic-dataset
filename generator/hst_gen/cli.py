"""Command line entry: python -m hst_gen <command>."""
import argparse
import time
from pathlib import Path

from . import config as cfglib
from .demand import build_demand
from .report import summarize, svg_chart


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


def main(argv=None):
    p = argparse.ArgumentParser(prog="hst_gen")
    p.add_argument("command", choices=["demand"])
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
    {"demand": cmd_demand}[args.command](args, cfg)
