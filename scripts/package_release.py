"""Packaging script for HST Synthetic Dataset v0.2.0.

Produces:
  - hst_dataset_csv_v0.2.0.tar.gz (structured CSV files: oltp/, oltp_truth/, reference/)
  - hst_dataset_postgres_v0.2.0.sql.gz (complete PostgreSQL dump with DDL, data, comments)
  - checksums.txt (SHA256 checksums for both release archives)

Usage:
  python scripts/package_release.py [--port 5433] [--keep-csv-dir] [--rebuild-csv]
"""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "output"
SQL_DIR = REPO_ROOT / "sql"

VERSION = "v0.2.0"
TAR_GZ_NAME = f"hst_dataset_csv_{VERSION}.tar.gz"
SQL_GZ_NAME = f"hst_dataset_postgres_{VERSION}.sql.gz"
CHECKSUMS_NAME = "checksums.txt"

CSV_TREE = {
    "oltp": [
        ("employee.csv", OUTPUT_DIR / "stage2" / "employee.csv"),
        ("employee_history.csv", OUTPUT_DIR / "stage2" / "employee_history.csv"),
        ("company.csv", OUTPUT_DIR / "stage2" / "company.csv"),
        ("promo.csv", OUTPUT_DIR / "stage2" / "promo.csv"),
        ("trip.csv", OUTPUT_DIR / "stage2" / "trip.csv"),
        ("customer.csv", OUTPUT_DIR / "stage3" / "customer.csv"),
        ("group_booking.csv", OUTPUT_DIR / "stage3" / "group_booking.csv"),
        ("group_booking_detail.csv", OUTPUT_DIR / "stage3" / "group_booking_detail.csv"),
        ("ticket_sales.csv", OUTPUT_DIR / "stage3" / "ticket_sales.csv"),
        ("fcc_card.csv", OUTPUT_DIR / "stage4" / "fcc_card.csv"),
        ("fcc_redemption.csv", OUTPUT_DIR / "stage4" / "fcc_redemption.csv"),
        ("refund.csv", OUTPUT_DIR / "stage4" / "refund.csv"),
        ("bank_statement.csv", OUTPUT_DIR / "stage4" / "bank_statement.csv"),
    ],
    "oltp_truth": [
        ("customer_truth.csv", OUTPUT_DIR / "stage3" / "hidden" / "customer_truth.csv"),
        ("ticket_group_truth.csv", OUTPUT_DIR / "stage3" / "hidden" / "ticket_group_truth.csv"),
        ("group_booking_payment.csv", OUTPUT_DIR / "stage4" / "hidden" / "group_booking_payment.csv"),
        ("anomaly_label.csv", OUTPUT_DIR / "stage5" / "hidden" / "anomaly_label.csv"),
    ],
    "reference": [
        ("stage1_demand.csv", OUTPUT_DIR / "stage1_demand.csv"),
        ("company_hidden.csv", OUTPUT_DIR / "stage2" / "hidden" / "company_hidden.csv"),
        ("trip_hidden.csv", OUTPUT_DIR / "stage2" / "hidden" / "trip_hidden.csv"),
    ],
}

DDL_FILES = [
    "01_oltp.sql",
    "02_oltp_truth.sql",
    "03_reference_data.sql",
    "04_comments.sql",
]

POSTGRES_TABLES = [
    ("oltp.employee", "oltp/employee.csv"),
    ("oltp.employee_history", "oltp/employee_history.csv"),
    ("oltp.company", "oltp/company.csv"),
    ("oltp.promo", "oltp/promo.csv"),
    ("oltp.trip", "oltp/trip.csv"),
    ("oltp.customer", "oltp/customer.csv"),
    ("oltp.group_booking", "oltp/group_booking.csv"),
    ("oltp.group_booking_detail", "oltp/group_booking_detail.csv"),
    ("oltp.ticket_sales", "oltp/ticket_sales.csv"),
    ("oltp.fcc_card", "oltp/fcc_card.csv"),
    ("oltp.fcc_redemption", "oltp/fcc_redemption.csv"),
    ("oltp.refund", "oltp/refund.csv"),
    ("oltp.bank_statement", "oltp/bank_statement.csv"),
    ("oltp_truth.customer_truth", "oltp_truth/customer_truth.csv"),
    ("oltp_truth.ticket_group_truth", "oltp_truth/ticket_group_truth.csv"),
    ("oltp_truth.group_booking_payment", "oltp_truth/group_booking_payment.csv"),
    ("oltp_truth.anomaly_label", "oltp_truth/anomaly_label.csv"),
]


def find_pg_bin() -> Path:
    scoop_bin = Path(r"C:\Users\Sam\scoop\apps\postgresql\current\bin")
    if (scoop_bin / "initdb.exe").exists():
        return scoop_bin
    p = shutil.which("initdb")
    if p:
        return Path(p).parent
    raise FileNotFoundError("PostgreSQL binaries not found in Scoop or PATH.")


def run_cmd(cmd, check=True):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if check and res.returncode != 0:
        print(f"ERROR executing: {' '.join(str(c) for c in cmd)}", file=sys.stderr, flush=True)
        print("STDOUT:", res.stdout, file=sys.stderr, flush=True)
        print("STDERR:", res.stderr, file=sys.stderr, flush=True)
        raise RuntimeError(f"Command failed with exit code {res.returncode}")
    return res


def package_csv_archive(csv_root: Path, tar_out: Path, rebuild: bool = False):
    print(f"\n--- 1. Packaging CSV files into {csv_root.name}/ ---", flush=True)
    if not csv_root.exists() or rebuild:
        if csv_root.exists():
            shutil.rmtree(csv_root)
        csv_root.mkdir(parents=True)
        for subfolder, files in CSV_TREE.items():
            folder_path = csv_root / subfolder
            folder_path.mkdir(parents=True, exist_ok=True)
            for dest_name, src_path in files:
                if not src_path.exists():
                    raise FileNotFoundError(f"Missing source file: {src_path}")
                target = folder_path / dest_name
                try:
                    os.link(src_path, target)
                except OSError:
                    shutil.copy2(src_path, target)
                print(f"  [CSV] {subfolder}/{dest_name} ({src_path.stat().st_size:,} bytes)", flush=True)
    else:
        print(f"  -> Using existing directory tree {csv_root.name}/", flush=True)

    if not tar_out.exists() or rebuild:
        print(f"Compressing to {tar_out.name}...", flush=True)
        t0 = time.time()
        tar_exe = shutil.which("tar") or r"C:\Windows\System32\tar.exe"
        if Path(tar_exe).exists():
            run_cmd([tar_exe, "-czf", str(tar_out), csv_root.name], check=True)
        else:
            import tarfile
            with tarfile.open(tar_out, "w:gz") as tar:
                tar.add(csv_root, arcname=csv_root.name)
        elapsed = time.time() - t0
        print(f"  -> Created {tar_out.name} ({tar_out.stat().st_size:,} bytes in {elapsed:.1f}s)", flush=True)
    else:
        print(f"  -> Using existing archive {tar_out.name} ({tar_out.stat().st_size:,} bytes)", flush=True)


def package_postgres_dump(csv_root: Path, sql_gz_out: Path, port: int):
    print(f"\n--- 2. Building PostgreSQL Dump on port {port} ---", flush=True)
    pg_bin = find_pg_bin()
    initdb = str(pg_bin / "initdb.exe")
    pg_ctl = str(pg_bin / "pg_ctl.exe")
    psql = str(pg_bin / "psql.exe")
    createdb = str(pg_bin / "createdb.exe")
    pg_dump = str(pg_bin / "pg_dump.exe")

    db_data = Path(tempfile.mkdtemp(prefix="pg_hst_release_"))
    db_name = "hst_release"
    user = "postgres"
    host = "127.0.0.1"

    print(f"Initializing temporary cluster at {db_data}...", flush=True)
    run_cmd([initdb, "-D", str(db_data), "-U", user, "-A", "trust", "--no-locale", "-E", "UTF8"])

    print(f"Starting PostgreSQL on {host}:{port}...", flush=True)
    server_log = db_data / "server.log"
    subprocess.run(
        [pg_ctl, "-D", str(db_data), "-o", f"-p {port}", "-l", str(server_log), "start", "-W"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    ready = False
    for _ in range(50):
        try:
            with socket.create_connection((host, port), timeout=0.5):
                ready = True
                break
        except OSError:
            time.sleep(0.1)
    if not ready:
        raise RuntimeError(f"PostgreSQL failed to accept connections on port {port} within 5s")

    try:
        print(f"Creating database {db_name}...", flush=True)
        run_cmd([createdb, "-h", host, "-p", str(port), "-U", user, db_name])

        print("Executing DDL scripts...", flush=True)
        for ddl in DDL_FILES:
            ddl_path = SQL_DIR / ddl
            print(f"  -> {ddl}...", flush=True)
            run_cmd([psql, "-h", host, "-p", str(port), "-U", user, "-d", db_name, "-f", str(ddl_path)])

        print("Loading 17 tables from packaged CSVs...", flush=True)
        for table, rel_path in POSTGRES_TABLES:
            csv_path = csv_root / rel_path
            if not csv_path.exists():
                raise FileNotFoundError(f"Missing CSV: {csv_path}")
            posix_path = str(csv_path.resolve()).replace("\\", "/")
            sql = f"\\copy {table} FROM '{posix_path}' WITH (FORMAT csv, HEADER true, NULL '');"
            print(f"  -> Loading {table}...", flush=True)
            run_cmd([psql, "-h", host, "-p", str(port), "-U", user, "-d", db_name, "-c", sql])

        print("Running integrity checks (sql/05_checks.sql)...", flush=True)
        check_res = run_cmd([psql, "-h", host, "-p", str(port), "-U", user, "-d", db_name, "-f", str(SQL_DIR / "05_checks.sql")])
        failed_checks = []
        for line in check_res.stdout.splitlines():
            line = line.strip()
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) == 2 and parts[1].isdigit():
                    name, count = parts[0], int(parts[1])
                    if count != 0:
                        failed_checks.append((name, count))
        if failed_checks:
            raise RuntimeError(f"Integrity check failed: {failed_checks}")
        print("  -> All 30 integrity checks passed (0 problems).", flush=True)

        print(f"Running pg_dump to {sql_gz_out.name} with -Z 6...", flush=True)
        t0 = time.time()
        dump_cmd = [
            pg_dump,
            "-h", host,
            "-p", str(port),
            "-U", user,
            "-d", db_name,
            "--no-owner",
            "--no-privileges",
            "-Z", "6",
            "-f", str(sql_gz_out),
        ]
        run_cmd(dump_cmd)
        elapsed = time.time() - t0
        print(f"  -> Created {sql_gz_out.name} ({sql_gz_out.stat().st_size:,} bytes in {elapsed:.1f}s)", flush=True)

    finally:
        print("Stopping temporary PostgreSQL server...", flush=True)
        subprocess.run([pg_ctl, "-D", str(db_data), "stop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
        shutil.rmtree(db_data, ignore_errors=True)


def compute_sha256(files: list[Path], output_file: Path):
    print(f"\n--- 3. Computing SHA256 Checksums into {output_file.name} ---", flush=True)
    lines = []
    for f in files:
        h = hashlib.sha256()
        with open(f, "rb") as fp:
            while chunk := fp.read(1024 * 1024):
                h.update(chunk)
        digest = h.hexdigest()
        line = f"{digest}  {f.name}"
        lines.append(line)
        print(f"  {line}", flush=True)

    with open(output_file, "w", encoding="utf-8") as out:
        out.write("\n".join(lines) + "\n")
    print("Checksums recorded.", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Package HST Synthetic Dataset v0.2.0 for release.")
    parser.add_argument("--port", type=int, default=5433, help="Port for temporary PostgreSQL cluster (default: 5433)")
    parser.add_argument("--keep-csv-dir", action="store_true", help="Keep hst_dataset_csv/ uncompressed folder")
    parser.add_argument("--rebuild-csv", action="store_true", help="Force rebuild CSV directory and tarball")
    args = parser.parse_args()

    csv_root = REPO_ROOT / "hst_dataset_csv"
    tar_out = REPO_ROOT / TAR_GZ_NAME
    sql_gz_out = REPO_ROOT / SQL_GZ_NAME
    checksums_out = REPO_ROOT / CHECKSUMS_NAME

    package_csv_archive(csv_root, tar_out, rebuild=args.rebuild_csv)
    package_postgres_dump(csv_root, sql_gz_out, args.port)
    compute_sha256([tar_out, sql_gz_out], checksums_out)

    if not args.keep_csv_dir and csv_root.exists():
        print(f"\nCleaning up uncompressed {csv_root.name}/...", flush=True)
        shutil.rmtree(csv_root, ignore_errors=True)

    print("\n=======================================================", flush=True)
    print("Release Packaging Complete!", flush=True)
    print(f"  1. {tar_out.name}: {tar_out.stat().st_size:,} bytes", flush=True)
    print(f"  2. {sql_gz_out.name}: {sql_gz_out.stat().st_size:,} bytes", flush=True)
    print(f"  3. {checksums_out.name}: {checksums_out.stat().st_size:,} bytes", flush=True)
    print("=======================================================", flush=True)


if __name__ == "__main__":
    main()
