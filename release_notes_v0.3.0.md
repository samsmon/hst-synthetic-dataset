# HST Synthetic Dataset v0.3.0: Analytics Mart & DWBI Edition

Release **v0.3.0** introduces a production-ready, denormalized analytics dataset specifically tailored for **Data Warehousing & Business Intelligence (DWBI)** courses, academic capstone projects (Tugas Besar), dashboard engineers, and data analysts.

Instead of joining across 17 normalized OLTP tables, this release packages all **10,815,864 ticket sales records** spanning 6 operational years (2020 through 2025) into a unified, high-performance wide dimensional mart.

---

## What's New in v0.3.0

- **Denormalized Wide Analytics Mart**:
  - Full history denormalized across Customers, Trips, Promos, Corporate Groups, Loyalty Cards (FCC), and Refunds.
  - Exported in columnar **Parquet (ZSTD)** (220 MB) and universal **CSV (GZIP)** (394 MB).
- **Precomputed Analytical & DWBI Dimensions**:
  - `lead_time_days`: Advance booking window from purchase to departure.
  - `season_type`: Calendar seasonality segments (`lebaran_mudik`, `lebaran_balik`, `nataru`, `school_holiday`, `covid_restriction`, `normal`).
  - `time_slot`: Diurnal operating windows (`morning_commute`, `afternoon`, `evening_commute`, `night`).
  - `travel_direction`: Network orientation (`outbound` east toward Bandung vs `inbound` west toward Jakarta).
  - `net_revenue`: Realized operator revenue after accounting for ticket cancellations and refund fees.
  - `is_fcc_member` & `fcc_card_type`: Loyalty tier flags and card types.
  - `is_refunded` & `refund_amount`: Direct cancellation measures.
- **Comprehensive DWBI Guide & Course Materials**:
  - Detailed star schema architecture (Fact `fact_ticket_sales` and Dimensions `dim_customer`, `dim_trip`, `dim_station`, `dim_date`, `dim_channel`, `dim_promo`, `dim_company`).
  - 43-column data dictionary with data types, dimensional roles, descriptions, and example values.
  - 5 practical, copy-paste SQL analytics queries for DuckDB, PostgreSQL, BigQuery, Snowflake, and Power BI.

---

## Release Assets

| File Name | Format | Size | SHA256 | Description |
|---|---|---|---|---|
| `hst_analytics_wide_v0.3.0.parquet` | Apache Parquet (ZSTD) | 220 MB | `6ffd096975dbcedfb4f99d94907c304487b78ac634b0a06c3f9a6a577e80dfab` | Recommended for DuckDB, Polars, Pandas, BigQuery, and Power BI. Sub-second queries on 10.8M rows. |
| `hst_analytics_wide_v0.3.0.csv.gz` | Compressed CSV (GZIP) | 394 MB | `7238827827cc6ca81e41db4c4e9516d4ed7a487b2e3ca3b6823b36d7d9d40e30` | Universal interoperability for PostgreSQL `COPY`, MySQL, Excel, and legacy BI engines. |
| `checksums.txt` | Text | 148 B | — | SHA256 cryptographic verification hashes. |

---

## Quickstart: Querying 10.8M Rows in Seconds

### DuckDB / Python
```python
import duckdb

# Query load factor and net revenue directly from Parquet
duckdb.sql("""
SELECT 
    season_type,
    travel_direction,
    COUNT(*) AS total_passengers,
    ROUND(SUM(net_revenue) / 1e9, 2) AS net_revenue_billion_idr
FROM 'hst_analytics_wide_v0.3.0.parquet'
WHERE ticket_status = 'used'
GROUP BY 1, 2
ORDER BY 3 DESC;
""").show()
```

### PostgreSQL
```sql
-- Direct stream restore into PostgreSQL
CREATE TABLE fact_ticket_sales_wide (...);
gunzip -c hst_analytics_wide_v0.3.0.csv.gz | psql -U postgres -d hst_dataset -c "COPY fact_ticket_sales_wide FROM STDIN WITH (FORMAT csv, HEADER true);"
```

See the full [DWBI Guide](docs/dwbi-guide.md) for star schema models, schema diagrams, and course tutorials.
