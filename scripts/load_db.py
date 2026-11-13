"""Stage 6 database loader: creates schema, loads CSV data, runs validation checks,
and optionally updates docs/data-dictionary.md.

Usage:
    python scripts/load_db.py [--host H] [--port P] [--user U] [--db D]
                              [--data-dir DIR] [--skip-checks] [--build-dict]
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = REPO_ROOT / "sql"

DDL_FILES = [
    "01_oltp.sql",
    "02_oltp_truth.sql",
    "03_reference_data.sql",
    "04_comments.sql",
]

TABLE_SOURCES = [
    ("oltp.employee", Path("stage2") / "employee.csv"),
    ("oltp.employee_history", Path("stage2") / "employee_history.csv"),
    ("oltp.company", Path("stage2") / "company.csv"),
    ("oltp.promo", Path("stage2") / "promo.csv"),
    ("oltp.trip", Path("stage2") / "trip.csv"),
    ("oltp.customer", Path("stage3") / "customer.csv"),
    ("oltp.group_booking", Path("stage3") / "group_booking.csv"),
    ("oltp.group_booking_detail", Path("stage3") / "group_booking_detail.csv"),
    ("oltp.ticket_sales", Path("stage3") / "ticket_sales.csv"),
    ("oltp.fcc_card", Path("stage4") / "fcc_card.csv"),
    ("oltp.fcc_redemption", Path("stage4") / "fcc_redemption.csv"),
    ("oltp.refund", Path("stage4") / "refund.csv"),
    ("oltp.bank_statement", Path("stage4") / "bank_statement.csv"),
    ("oltp_truth.customer_truth", Path("stage3") / "hidden" / "customer_truth.csv"),
    ("oltp_truth.ticket_group_truth", Path("stage3") / "hidden" / "ticket_group_truth.csv"),
    ("oltp_truth.group_booking_payment", Path("stage4") / "hidden" / "group_booking_payment.csv"),
    ("oltp_truth.anomaly_label", Path("stage5") / "hidden" / "anomaly_label.csv"),
]


def run_psql(args, sql_file=None, sql_cmd=None, capture=False):
    cmd = [
        os.environ.get("PSQL", "psql"),
        "-h", args.host,
        "-p", str(args.port),
        "-U", args.user,
        "-d", args.db,
        "-v", "ON_ERROR_STOP=1",
    ]
    if sql_file:
        cmd += ["-f", str(sql_file)]
    elif sql_cmd:
        cmd += ["-c", sql_cmd]
    res = subprocess.run(cmd, capture_output=capture, text=True)
    if res.returncode != 0:
        err_msg = res.stderr if capture else f"psql exited with code {res.returncode}"
        raise RuntimeError(f"psql execution failed: {err_msg}")
    return res


def load_tables(args):
    data_dir = Path(args.data_dir)
    print(f"Loading 17 tables from {data_dir}...")
    for table, rel_path in TABLE_SOURCES:
        file_path = data_dir / rel_path
        if not file_path.exists():
            raise FileNotFoundError(f"Missing required CSV for {table}: {file_path}")
        posix_path = str(file_path.resolve()).replace("\\", "/")
        sql = f"\\copy {table} FROM '{posix_path}' WITH (FORMAT csv, HEADER true, NULL '');"
        print(f"  -> Copying {table} from {rel_path}...")
        run_psql(args, sql_cmd=sql)


def run_checks(args):
    check_file = SQL_DIR / "05_checks.sql"
    print("Running sql/05_checks.sql (30 integrity and anomaly checks)...")
    res = run_psql(args, sql_file=check_file, capture=True)
    problems = []
    total_checks = 0
    for line in res.stdout.strip().splitlines():
        line = line.strip()
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) == 2 and parts[1].isdigit():
                name, count = parts[0], int(parts[1])
                total_checks += 1
                if count != 0:
                    problems.append((name, count))
    if total_checks < 30:
        raise RuntimeError(f"Expected at least 30 check queries, but only parsed {total_checks} results.")
    if problems:
        formatted = "\n".join(f"  - {name}: {cnt} problems" for name, cnt in problems)
        raise RuntimeError(f"Integrity checks failed ({len(problems)} checks reported problems):\n{formatted}")
    print(f"All {total_checks} checks passed: 0 problems detected.")


def build_dictionary(args):
    print("Rebuilding docs/data-dictionary.md...")
    dict_script = REPO_ROOT / "scripts" / "build_dictionary.py"
    cmd = [
        sys.executable,
        str(dict_script),
        "--host", args.host,
        "--port", str(args.port),
        "--user", args.user,
        "--db", args.db,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to rebuild data dictionary:\n{res.stderr}")
    print(res.stdout.strip())


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Load HST synthetic dataset into PostgreSQL.")
    p.add_argument("--host", default="localhost", help="PostgreSQL host (default: localhost)")
    p.add_argument("--port", type=int, default=5432, help="PostgreSQL port (default: 5432)")
    p.add_argument("--user", default="postgres", help="PostgreSQL user (default: postgres)")
    p.add_argument("--db", default="postgres", help="PostgreSQL database name (default: postgres)")
    p.add_argument("--data-dir", default="output", help="Root output directory containing stage CSVs (default: output)")
    p.add_argument("--skip-checks", action="store_true", help="Skip running sql/05_checks.sql")
    p.add_argument("--build-dict", action="store_true", help="Rebuild docs/data-dictionary.md after load")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        print("1. Applying DDL scripts...")
        for ddl in DDL_FILES:
            ddl_path = SQL_DIR / ddl
            print(f"  -> Running {ddl}...")
            run_psql(args, sql_file=ddl_path)

        print("2. Loading dataset tables...")
        load_tables(args)

        if not args.skip_checks:
            print("3. Validating data integrity...")
            run_checks(args)
        else:
            print("3. Skipping checks (--skip-checks specified).")

        if args.build_dict:
            print("4. Updating data dictionary...")
            build_dictionary(args)

        print("Database load completed successfully.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
