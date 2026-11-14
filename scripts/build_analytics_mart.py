"""Build denormalized wide analytics mart for HST Synthetic Dataset using DuckDB.

Joins 10.8M tickets with customers, trips, promos, corporate entities,
loyalty cards, refunds, and reference lookup tables into Parquet and CSV.gz.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("build_analytics_mart")

EXPECTED_ROW_COUNT = 10_815_864


def resolve_paths(data_dir: Path) -> dict[str, Path]:
    """Find source CSV files in data_dir (supports output/ or hst_dataset_csv/ layout)."""
    candidates = {
        "ticket_sales": [data_dir / "stage3" / "ticket_sales.csv", data_dir / "oltp" / "ticket_sales.csv", data_dir / "ticket_sales.csv"],
        "customer": [data_dir / "stage3" / "customer.csv", data_dir / "oltp" / "customer.csv", data_dir / "customer.csv"],
        "customer_truth": [data_dir / "stage3" / "hidden" / "customer_truth.csv", data_dir / "oltp_truth" / "customer_truth.csv", data_dir / "customer_truth.csv"],
        "trip": [data_dir / "stage2" / "trip.csv", data_dir / "oltp" / "trip.csv", data_dir / "trip.csv"],
        "promo": [data_dir / "stage2" / "promo.csv", data_dir / "oltp" / "promo.csv", data_dir / "promo.csv"],
        "company": [data_dir / "stage2" / "company.csv", data_dir / "oltp" / "company.csv", data_dir / "company.csv"],
        "group_booking": [data_dir / "stage3" / "group_booking.csv", data_dir / "oltp" / "group_booking.csv", data_dir / "group_booking.csv"],
        "fcc_card": [data_dir / "stage4" / "fcc_card.csv", data_dir / "oltp" / "fcc_card.csv", data_dir / "fcc_card.csv"],
        "fcc_redemption": [data_dir / "stage4" / "fcc_redemption.csv", data_dir / "oltp" / "fcc_redemption.csv", data_dir / "fcc_redemption.csv"],
        "refund": [data_dir / "stage4" / "refund.csv", data_dir / "oltp" / "refund.csv", data_dir / "refund.csv"],
    }
    resolved = {}
    for key, paths in candidates.items():
        found = next((p for p in paths if p.exists()), None)
        if not found:
            raise FileNotFoundError(f"Cannot find source CSV for {key}. Searched: {[str(p) for p in paths]}")
        resolved[key] = found
        logger.info(f"Using {key}: {found}")
    return resolved


def setup_dimensions(con: duckdb.DuckDBPyConnection, paths: dict[str, Path]) -> None:
    """Preload reference and dimension lookup tables into in-memory tables."""
    logger.info("Setting up dimension and reference tables in DuckDB...")
    con.execute("""
    CREATE TABLE station_lookup AS 
    SELECT 1 AS station_id, 'Halim' AS station_name
    UNION ALL SELECT 2, 'Karawang'
    UNION ALL SELECT 3, 'Padalarang'
    UNION ALL SELECT 4, 'Tegalluar';

    CREATE TABLE channel_lookup AS 
    SELECT 1 AS channel_id, 'Counter' AS channel_name
    UNION ALL SELECT 2, 'Group'
    UNION ALL SELECT 3, 'FCC'
    UNION ALL SELECT 4, 'Agent'
    UNION ALL SELECT 5, 'App'
    UNION ALL SELECT 6, 'Web';
    """)

    con.execute(f"""
    CREATE TABLE trip_dim AS SELECT id, trip_no, seat_capacity FROM read_csv_auto('{paths["trip"].as_posix()}');
    CREATE TABLE promo_dim AS SELECT id, promo_code, name AS promo_name, type AS promo_type FROM read_csv_auto('{paths["promo"].as_posix()}');
    CREATE TABLE fcc_dim AS 
    SELECT r.ticket_sales_id, c.card_type AS fcc_card_type 
    FROM read_csv_auto('{paths["fcc_redemption"].as_posix()}') r 
    JOIN read_csv_auto('{paths["fcc_card"].as_posix()}') c ON r.card_id = c.id;

    CREATE TABLE refund_dim AS SELECT ticket_sales_id, refund_amount, refund_fee, refund_date FROM read_csv_auto('{paths["refund"].as_posix()}');
    CREATE TABLE group_dim AS 
    SELECT gb.id AS group_booking_id, gb.booking_no AS group_booking_no, comp.name AS company_name, comp.type AS company_type 
    FROM read_csv_auto('{paths["group_booking"].as_posix()}') gb 
    LEFT JOIN read_csv_auto('{paths["company"].as_posix()}') comp ON gb.company_id = comp.id;

    CREATE TABLE customer_truth_dim AS SELECT customer_id, segment AS customer_segment FROM read_csv_auto('{paths["customer_truth"].as_posix()}');
    CREATE TABLE customer_dim AS SELECT id, name AS customer_name, gender AS customer_gender, city AS customer_city FROM read_csv_auto('{paths["customer"].as_posix()}');
    """)
    logger.info("Dimension tables ready.")


def get_wide_query(ticket_sales_path: Path) -> str:
    """Return SQL statement defining wide analytics mart."""
    return f"""
    SELECT 
        ts.id AS ticket_id,
        ts.order_id,
        ts.ticket_no,
        ts.purchase_date AS booking_time,
        CAST(ts.departure_date AS DATE) AS travel_date,
        ts.departure_time,
        ts.arrival_time,
        date_diff('day', CAST(ts.purchase_date AS DATE), CAST(ts.departure_date AS DATE)) AS lead_time_days,
        ts.status AS ticket_status,
        ts.seat_class,
        ts.base_price,
        ts.discount_pct,
        ts.discount_amount,
        ts.service_fee_amount,
        ts.total_price,
        COALESCE(ts.total_price, 0) - COALESCE(ref.refund_amount, 0) AS net_revenue,
        ts.payment_method,
        st_orig.station_name AS origin_station_name,
        st_dest.station_name AS destination_station_name,
        CASE ts.route_id 
            WHEN 1 THEN 'Jakarta - Bandung' 
            WHEN 2 THEN 'Jakarta - Karawang' 
            WHEN 3 THEN 'Karawang - Bandung' 
            ELSE 'Other' 
        END AS route_name,
        sc.channel_name AS sales_channel_name,
        CASE 
            WHEN ts.origin_station_id < ts.destination_station_id THEN 'outbound'
            ELSE 'inbound'
        END AS travel_direction,
        CASE 
            WHEN (CAST(ts.departure_date AS DATE) BETWEEN DATE '2020-05-17' AND DATE '2020-05-24')
              OR (CAST(ts.departure_date AS DATE) BETWEEN DATE '2021-05-06' AND DATE '2021-05-13')
              OR (CAST(ts.departure_date AS DATE) BETWEEN DATE '2022-04-25' AND DATE '2022-05-02')
              OR (CAST(ts.departure_date AS DATE) BETWEEN DATE '2023-04-15' AND DATE '2023-04-22')
              OR (CAST(ts.departure_date AS DATE) BETWEEN DATE '2024-04-03' AND DATE '2024-04-10')
              OR (CAST(ts.departure_date AS DATE) BETWEEN DATE '2025-03-24' AND DATE '2025-03-31')
            THEN 'lebaran_mudik'
            WHEN (CAST(ts.departure_date AS DATE) BETWEEN DATE '2020-05-25' AND DATE '2020-05-31')
              OR (CAST(ts.departure_date AS DATE) BETWEEN DATE '2021-05-14' AND DATE '2021-05-20')
              OR (CAST(ts.departure_date AS DATE) BETWEEN DATE '2022-05-03' AND DATE '2022-05-09')
              OR (CAST(ts.departure_date AS DATE) BETWEEN DATE '2023-04-23' AND DATE '2023-04-29')
              OR (CAST(ts.departure_date AS DATE) BETWEEN DATE '2024-04-11' AND DATE '2024-04-17')
              OR (CAST(ts.departure_date AS DATE) BETWEEN DATE '2025-04-01' AND DATE '2025-04-07')
            THEN 'lebaran_balik'
            WHEN (EXTRACT(month FROM CAST(ts.departure_date AS DATE)) = 12 AND EXTRACT(day FROM CAST(ts.departure_date AS DATE)) >= 23)
              OR (EXTRACT(month FROM CAST(ts.departure_date AS DATE)) = 1 AND EXTRACT(day FROM CAST(ts.departure_date AS DATE)) <= 2)
            THEN 'nataru'
            WHEN EXTRACT(month FROM CAST(ts.departure_date AS DATE)) IN (6, 7)
            THEN 'school_holiday'
            WHEN CAST(ts.departure_date AS DATE) BETWEEN DATE '2020-03-01' AND DATE '2021-09-30'
            THEN 'covid_restriction'
            ELSE 'normal'
        END AS season_type,
        CASE 
            WHEN ts.departure_time >= '06:00:00' AND ts.departure_time < '09:00:00' THEN 'morning_commute'
            WHEN ts.departure_time >= '09:00:00' AND ts.departure_time < '16:00:00' THEN 'afternoon'
            WHEN ts.departure_time >= '16:00:00' AND ts.departure_time < '19:00:00' THEN 'evening_commute'
            ELSE 'night'
        END AS time_slot,
        ts.customer_id,
        c.customer_name,
        c.customer_gender,
        c.customer_city,
        ct.customer_segment,
        tr.trip_no,
        tr.seat_capacity,
        pr.promo_code,
        pr.promo_name,
        pr.promo_type,
        CASE WHEN fcc.fcc_card_type IS NOT NULL THEN true ELSE false END AS is_fcc_member,
        fcc.fcc_card_type,
        CASE WHEN ref.refund_amount IS NOT NULL AND ref.refund_amount > 0 THEN true ELSE false END AS is_refunded,
        ref.refund_amount,
        ref.refund_fee,
        ref.refund_date,
        gb.group_booking_no,
        gb.company_name,
        gb.company_type
    FROM read_csv_auto('{ticket_sales_path.as_posix()}') ts
    JOIN station_lookup st_orig ON ts.origin_station_id = st_orig.station_id
    JOIN station_lookup st_dest ON ts.destination_station_id = st_dest.station_id
    JOIN channel_lookup sc ON ts.sales_channel_id = sc.channel_id
    LEFT JOIN customer_dim c ON ts.customer_id = c.id
    LEFT JOIN customer_truth_dim ct ON ts.customer_id = ct.customer_id
    LEFT JOIN trip_dim tr ON ts.trip_id = tr.id
    LEFT JOIN promo_dim pr ON ts.promo_id = pr.id
    LEFT JOIN fcc_dim fcc ON ts.id = fcc.ticket_sales_id
    LEFT JOIN refund_dim ref ON ts.id = ref.ticket_sales_id
    LEFT JOIN group_dim gb ON ts.group_booking_id = gb.group_booking_id
    """


def build_analytics_mart(data_dir: Path, out_dir: Path, version: str = "v0.3.0") -> None:
    """Build and export wide analytics mart Parquet and CSV.gz files."""
    paths = resolve_paths(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / f"hst_analytics_wide_{version}.parquet"
    csv_gz_path = out_dir / f"hst_analytics_wide_{version}.csv.gz"

    con = duckdb.connect()
    setup_dimensions(con, paths)

    logger.info("Executing wide analytics query and writing Parquet (ZSTD)...")
    t0 = time.time()
    query = get_wide_query(paths["ticket_sales"])
    con.execute(f"COPY ({query}) TO '{parquet_path.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD);")
    logger.info(f"Parquet exported: {parquet_path} ({parquet_path.stat().st_size / (1024*1024):.1f} MB) in {time.time()-t0:.1f}s")

    logger.info("Verifying row count and net revenue logic from Parquet...")
    verify_df = con.execute(f"""
    SELECT 
        count(*) AS row_cnt,
        sum(total_price) AS gross_rev,
        sum(COALESCE(refund_amount, 0)) AS refund_tot,
        sum(net_revenue) AS net_rev,
        count(*) FILTER (WHERE is_refunded) AS ref_cnt,
        count(*) FILTER (WHERE is_fcc_member) AS fcc_cnt
    FROM read_parquet('{parquet_path.as_posix()}')
    """).df()

    row_cnt = int(verify_df["row_cnt"].iloc[0])
    gross_rev = int(verify_df["gross_rev"].iloc[0])
    refund_tot = int(verify_df["refund_tot"].iloc[0])
    net_rev = int(verify_df["net_rev"].iloc[0])

    logger.info(f"Verified rows: {row_cnt:,} (Expected: {EXPECTED_ROW_COUNT:,})")
    logger.info(f"Gross: IDR {gross_rev:,} | Refunds: IDR {refund_tot:,} | Net: IDR {net_rev:,}")
    if row_cnt != EXPECTED_ROW_COUNT:
        raise ValueError(f"Row count mismatch! Expected {EXPECTED_ROW_COUNT}, got {row_cnt}")
    if net_rev != gross_rev - refund_tot:
        raise ValueError(f"Net revenue financial check failed: {net_rev} != {gross_rev - refund_tot}")

    logger.info("Exporting CSV Gzip directly from Parquet...")
    t1 = time.time()
    con.execute(f"COPY (SELECT * FROM read_parquet('{parquet_path.as_posix()}')) TO '{csv_gz_path.as_posix()}' (FORMAT CSV, HEADER, COMPRESSION GZIP);")
    logger.info(f"CSV.gz exported: {csv_gz_path} ({csv_gz_path.stat().st_size / (1024*1024):.1f} MB) in {time.time()-t1:.1f}s")
    logger.info("Analytics mart build completed successfully.")


def main():
    parser = argparse.ArgumentParser(description="Build wide analytics mart for HST Synthetic Dataset.")
    parser.add_argument("--data-dir", type=Path, default=Path("output"), help="Base directory containing CSV stages.")
    parser.add_argument("--out-dir", type=Path, default=Path("."), help="Output directory for generated datasets.")
    parser.add_argument("--version", type=str, default="v0.3.0", help="Release version tag.")
    args = parser.parse_args()

    build_analytics_mart(args.data_dir, args.out_dir, args.version)


if __name__ == "__main__":
    main()
