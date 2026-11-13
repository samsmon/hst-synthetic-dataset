"""Throwaway PostgreSQL validation script.
Initializes a temporary PostgreSQL cluster, loads generated CSVs, and runs sql/05_checks.sql.
"""
import os
from pathlib import Path
import subprocess
import sys
import time

PG_BIN = Path(r"C:\Users\Sam\scoop\apps\postgresql\current\bin")
INITDB = PG_BIN / "initdb.exe"
PG_CTL = PG_BIN / "pg_ctl.exe"
PSQL = PG_BIN / "psql.exe"
CREATEDB = PG_BIN / "createdb.exe"

REPO_ROOT = Path(__file__).resolve().parent.parent
PORT = "5433"
HOST = "127.0.0.1"
USER = "postgres"
DB_NAME = "hst_val"


def run_cmd(args, check=True):
    res = subprocess.run(args, capture_output=True, text=True)
    if check and res.returncode != 0:
        print(f"FAILED: {' '.join(str(x) for x in args)}", file=sys.stderr)
        print("STDOUT:", res.stdout, file=sys.stderr)
        print("STDERR:", res.stderr, file=sys.stderr)
        raise RuntimeError(f"Command failed with code {res.returncode}")
    return res


def start_pg(data_dir):
    cmd = [str(PG_CTL), "-D", str(data_dir), "-o", f"-p {PORT}", "-l", str(data_dir / "server.log"), "start", "-w"]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if res.returncode != 0:
        raise RuntimeError("pg_ctl start failed")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validate generated CSVs against PostgreSQL schema and checks.")
    parser.add_argument("--data-dir", default=None, help="Root folder containing stage2, stage3, stage4")
    args = parser.parse_args()

    data_source = Path(args.data_dir) if args.data_dir else (REPO_ROOT / "output")
    if not (data_source / "stage4").exists() and (REPO_ROOT / "scratch_val").exists():
        data_source = REPO_ROOT / "scratch_val"

    data_dir = Path(os.environ.get("TEMP", r"C:\Users\Sam\AppData\Local\Temp")) / f"pg_db_val_{int(time.time())}"
    s2 = data_source / "stage2"
    s3 = data_source / "stage3"
    s4 = data_source / "stage4"
    s5 = data_source / "stage5"

    print(f"1. Initializing DB in {data_dir}...", flush=True)
    run_cmd([str(INITDB), "-D", str(data_dir), "-U", USER, "-A", "trust", "--no-locale", "-E", "UTF8"])

    print("2. Starting PostgreSQL on port", PORT, "...", flush=True)
    start_pg(data_dir)

    try:
        print("3. Creating database", DB_NAME, "...")
        run_cmd([str(CREATEDB), "-h", HOST, "-p", PORT, "-U", USER, DB_NAME])

        print("4. Running schema scripts...")
        run_cmd([str(PSQL), "-h", HOST, "-p", PORT, "-U", USER, "-d", DB_NAME, "-f", str(REPO_ROOT / "sql" / "01_oltp.sql")])
        run_cmd([str(PSQL), "-h", HOST, "-p", PORT, "-U", USER, "-d", DB_NAME, "-f", str(REPO_ROOT / "sql" / "02_oltp_truth.sql")])
        run_cmd([str(PSQL), "-h", HOST, "-p", PORT, "-U", USER, "-d", DB_NAME, "-f", str(REPO_ROOT / "sql" / "03_reference_data.sql")])

        print("5. Loading CSVs in dependency order...")
        copies = [
            ("oltp.employee", s2 / "employee.csv"),
            ("oltp.employee_history", s2 / "employee_history.csv"),
            ("oltp.company", s2 / "company.csv"),
            ("oltp.promo", s2 / "promo.csv"),
            ("oltp.trip", s2 / "trip.csv"),
            ("oltp.customer", s3 / "customer.csv"),
            ("oltp.group_booking", s3 / "group_booking.csv"),
            ("oltp.group_booking_detail", s3 / "group_booking_detail.csv"),
            ("oltp.ticket_sales", s3 / "ticket_sales.csv"),
            ("oltp.fcc_card", s4 / "fcc_card.csv"),
            ("oltp.fcc_redemption", s4 / "fcc_redemption.csv"),
            ("oltp.refund", s4 / "refund.csv"),
            ("oltp.bank_statement", s4 / "bank_statement.csv"),
            ("oltp_truth.customer_truth", s3 / "hidden" / "customer_truth.csv"),
            ("oltp_truth.ticket_group_truth", s3 / "hidden" / "ticket_group_truth.csv"),
            ("oltp_truth.group_booking_payment", s4 / "hidden" / "group_booking_payment.csv"),
            ("oltp_truth.anomaly_label", s5 / "hidden" / "anomaly_label.csv"),
        ]

        for table, file_path in copies:
            if not file_path.exists():
                raise FileNotFoundError(f"Missing file {file_path}")
            posix_path = str(file_path.resolve()).replace("\\", "/")
            sql = f"\\copy {table} FROM '{posix_path}' WITH (FORMAT csv, HEADER true, NULL '');"
            print(f"   Copying {table} from {file_path.name}...")
            run_cmd([str(PSQL), "-h", HOST, "-p", PORT, "-U", USER, "-d", DB_NAME, "-c", sql])

        print("6. Running sql/05_checks.sql...")
        res = run_cmd([str(PSQL), "-h", HOST, "-p", PORT, "-U", USER, "-d", DB_NAME, "-f", str(REPO_ROOT / "sql" / "05_checks.sql")])
        print("=== CHECKS OUTPUT ===")
        print(res.stdout)

        # Parse checks output to ensure all return 0 problems
        problems = []
        for line in res.stdout.strip().split("\n"):
            line = line.strip()
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) == 2 and parts[1].isdigit():
                    name, count = parts[0], int(parts[1])
                    if count != 0:
                        problems.append((name, count))

        if problems:
            print("FAILED CHECKS:", problems, file=sys.stderr)
            sys.exit(1)
        else:
            print("ALL CHECKS PASSED: 0 problems detected!")

    finally:
        print("7. Stopping PostgreSQL server...")
        run_cmd([str(PG_CTL), "-D", str(data_dir), "stop"], check=False)


if __name__ == "__main__":
    main()
