# HST Synthetic Dataset v0.2.0 — High-Speed Train Ticketing Dataset (10.8M Tickets, 2020–2025)

We are proud to announce the **v0.2.0** milestone release of the **HST Synthetic Dataset** — an enterprise-scale relational synthetic dataset modelling 6 full years (2020 through 2025) of operations for a high-speed passenger railway operator running between Jakarta and Bandung.

Designed specifically for machine learning, data engineering, fraud detection, and database benchmark workloads, this release packages over **18 million records** across 17 relational database tables and reference files, complete with relational integrity, realistic economic shocks, seasonal dynamics, and isolated ground-truth keys.

---

## Dataset Overview

- **Time Horizon**: 2020-01-01 to 2025-12-31 (6 calendar years / 2,192 operating days).
- **Primary Volume**: 10,815,864 individual and group ticket sales, 2,554,016 unique passenger identities, and 34,113 scheduled train trips.
- **Relational Architecture**: 17 tables structured into 2 PostgreSQL schemas:
  - `oltp`: Operational database schema capturing ticketing, corporate bookings, Frequent Customer Cards (FCC), refunds, employees, and bank cash transactions.
  - `oltp_truth`: Segregated evaluation schema holding ground-truth labels for customer segmentation, churn, true booking linkages, and 58,676 injected operational and financial anomalies.
- **Data Parity**: Identical data exported as both standalone CSV files and an all-in-one compressed PostgreSQL database dump.

---

## Table Breakdown & Storage Profiles

### Schema `oltp` (Operational Layer)

| Table | Rows | Uncompressed CSV Size | Description |
|---|---|---|---|
| `oltp.ticket_sales` | 10,815,864 | 2.38 GB | Complete individual & group ticket transaction records across all channels |
| `oltp.customer` | 2,554,016 | 301.05 MB | Master customer identities with synthetic NIKs, demographic profiles, and registration dates |
| `oltp.fcc_redemption` | 1,022,908 | 74.04 MB | Loyalty quota redemption ledger linking tickets to subscription cards |
| `oltp.bank_statement` | 224,071 | 24.44 MB | Operational bank account ledger (TRF, SETTLE, REFUND, FEE, INT) |
| `oltp.refund` | 152,037 | 8.03 MB | Processed cancellations, ticket returns, fee retentions, and reason codes |
| `oltp.fcc_card` | 128,944 | 7.46 MB | Frequent Customer Cards issued (Gold 50-trip and Silver 20-trip commuter packages) |
| `oltp.group_booking_detail` | 64,472 | 1.45 MB | Outbound and return travel legs per corporate group booking |
| `oltp.group_booking` | 48,562 | 9.30 MB | Group reservation contracts, quotation statuses, and verified pax counts |
| `oltp.trip` | 34,113 | 1.88 MB | Scheduled train services with train capacities (300, 450, 600 seats) and load factors |
| `oltp.company` | 4,000 | 277.81 KB | Registered corporate clients, travel agencies, educational institutions, and government bodies |
| `oltp.employee_history` | 732 | 20.78 KB | Career progressions, promotions, and station transfer audit logs |
| `oltp.employee` | 612 | 79.14 KB | Operations, customer service, sales, and ticketing workforce |
| `oltp.promo` | 90 | 8.35 KB | Seasonal, anniversary, and targeted discount campaigns |

### Schema `oltp_truth` (Ground Truth & Machine Learning Evaluation)

| Table | Rows | Uncompressed CSV Size | Description |
|---|---|---|---|
| `oltp_truth.customer_truth` | 2,554,016 | 47.08 MB | Generator segments (`commuter`, `occasional`, `one_time`), lifetime trips, and churn flags |
| `oltp_truth.ticket_group_truth` | 110,525 | 1.64 MB | Ground-truth mapping of group passengers to individual booking headers |
| `oltp_truth.group_booking_payment` | 70,050 | 2.04 MB | Exact ledger allocation linking bank transfer credits to corporate bookings |
| `oltp_truth.anomaly_label` | 58,676 | 2.41 MB | Benchmark ground truth for ML Task 7 (injected operational and financial defects) |

### Auxiliary Reference Data

| File | Rows | Size | Description |
|---|---|---|---|
| `reference/stage1_demand.csv` | 6,576 | 172.35 KB | Daily route-level passenger demand profile across baseline COVID phases |
| `reference/trip_hidden.csv` | 34,113 | 744.39 KB | Internal schedule generation seeds and planned demand matrices |
| `reference/company_hidden.csv` | 4,000 | 241.89 KB | Latent behavioral factors: booking propensity, payment promptness, cancellation rates |

---

## Realistic Dynamics & Fun Facts

This dataset is generated using calibrated behavioural and operational models mimicking the real Jakarta–Bandung corridor:

### 1. The COVID-19 Shock & 2020 Lockdown Refund Surge
In March 2020, as the pandemic emerged, passenger volumes collapsed from ~2,300/day to fewer than 950/day. The refund rate skyrocketed to 15–25% of all active bookings between March and June 2020. Under emergency pandemic response policies, 100% of cancellation fees were waived for passengers citing `schedule_change`, leaving only operational cost deductions for voluntary passenger requests.

### 2. Mudik Bans & The Delta Wave Plunge
During the annual Eid al-Fitr (Lebaran) periods of 2020 and 2021, the Indonesian government enforced nationwide travel restrictions (*Larangan Mudik*). Instead of the traditional multi-fold holiday surge, daily ticket volumes plunged to record lows (under 350 tickets/day during Lebaran 2020). In July 2021, the Delta variant outbreak led to strict emergency restrictions (PPKM Darurat), dropping ridership to just 24% of normalized capacity.

### 3. Lebaran Eid Rush: Asymmetric Directional Swings
Once travel normalized from 2022 onwards, the Lebaran holiday displays massive directional asymmetry:
- **Pre-Eid Rush (H-7 to H-1)**: Outbound departures from Jakarta (Halim) towards West Java (Padalarang / Tegalluar) spike by **+60%** above baseline, peaking sharply at H-3.
- **Eid Day (1 Shawwal)**: A steep mid-holiday trough as families gather at home.
- **Return Rush (H+3 to H+7)**: Inbound trains returning to Jakarta swell by **+50%**, peaking around H+5.
- The single busiest travel day in the 6-year history occurred on **April 7, 2024 (H-3 of Lebaran 1445 H)** with **14,796 passengers** across 45 daily train services.

### 4. Year-End Holiday Double Peaks
Every December, holiday demand exhibits characteristic double peaks: the Christmas travel surge (peaking on **December 24–25**) followed by a brief lull and a second New Year's Eve wave (peaking on **December 31–January 1**), averaging over 8,500 passengers per day.

### 5. Friday Evening & Sunday Night Commuter Rhythms
The weekly profile demonstrates distinct commuter habits between Jakarta and the Bandung metropolitan area:
- **Friday afternoons and evenings**: Passenger traffic surges by **+25%** as office workers and university students leave Jakarta for weekend breaks in Bandung.
- **Sunday evenings**: A **+15%** return spike back to Jakarta ahead of the Monday morning workweek.
- Tuesdays and Wednesdays remain quiet baseline days (~5,500 passengers/day).

### 6. The Commuter Economy: Frequent Customer Cards (FCC)
Approximately 35% of regular individual riders hold a subscription card under the Frequent Customer Card programme:
- **Gold Cards (G)**: 50 prepaid trips valid for 6 months (83,766 cards issued, 65% share).
- **Silver Cards (S)**: 20 prepaid trips valid for 3 months (45,178 cards issued, 35% share).
- FCC redemptions account for **1,022,908 train boardings**, with cardholders actively tracking remaining quotas before expiry dates.

### 7. Corporate Group Payment Behaviors
The 4,000 corporate clients exhibit distinctive settlement characteristics:
- **Travel agencies** and **corporate accounts**: Prompt payment behaviour, often clearing invoices in single full transfers within 2 to 5 business days.
- **Government entities** and **schools/universities**: Longer bureaucratic payment cycles, multi-stage instalment schedules, and frequent split bank transfers across multiple branches.

### 8. 58,676 Injected Operational & Financial Anomalies
To provide an authentic training ground for unsupervised and supervised anomaly detection models, Stage 5 injected 58,676 real-world operational and financial irregularities:
- **23,677 Date Outliers**: Tickets booked with issuance or travel dates violating calendar constraints.
- **16,888 Duplicate Tickets**: Accidental duplicate seat issuances in sales channels.
- **15,236 Inactive Issuers**: Tickets logged under employee NIPs outside their active employment date windows.
- **1,022 Name Mismatches**: Bank statement sender names that fail fuzzy reconciliation with company legal names.
- **699 Underpayments**: Group booking bank transfers falling short of contracted totals.
- **688 Duplicate Bank Credits**: Redundant wire transfer entries on bank ledgers.
- **466 Overpayments**: Transfers exceeding the agreed contract price requiring reconciliation.

All anomalies are indexed in `oltp_truth.anomaly_label` as evaluation ground truth.

---

## Release Assets

| Asset File | Size | SHA256 Checksum | Description |
|---|---|---|---|
| `hst_dataset_csv_v0.2.0.tar.gz` | 644.36 MB (675,663,043 B) | `2cee9d4c6400379b111cd0509943506beff7c98c5d3fee5b8498e381d1c9d2ce` | Structured CSV files organised by schema folder (`oltp/`, `oltp_truth/`, `reference/`) |
| `hst_dataset_postgres_v0.2.0.sql.gz` | 651.22 MB (682,854,748 B) | `bd49de2bb7b1787df1d8f76561c33b1b5d6a046e899b61de4e6086db6946d976` | Full PostgreSQL dump (DDL, constraints, table comments, and COPY data for all 17 tables) |
| `checksums.txt` | 199 B | - | Cryptographic SHA256 hashes for archive integrity verification |

---

## Quickstart: Restoring into PostgreSQL

To load the full dataset directly into an existing PostgreSQL instance:

```bash
# 1. Create a clean database
createdb -h localhost -p 5432 -U postgres hst_dataset

# 2. Restore schema, data, and comments in one step
gunzip -c hst_dataset_postgres_v0.2.0.sql.gz | psql -h localhost -p 5432 -U postgres -d hst_dataset
```

Or extract the CSV files to explore in DuckDB, Polars, or pandas:

```bash
tar -xzf hst_dataset_csv_v0.2.0.tar.gz
```

---

*Generated by the HST Synthetic Dataset Pipeline.*
