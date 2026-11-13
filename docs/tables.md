# Table reference

What each table is, what it is for, and where its shape comes from.

Origin legend:

- **GTV**: group-ticket verification app (`kcic-ia-payroll`): `dokumen_bak`, `dokumen_bak_detail`, `data_ticketsales`, `dokumen_rekeningkoran`.
- **FCC**: frequent customer card admin app (`fcc-admin-system`): `maindata`, `subdata`.
- **New**: added for this dataset.
- **Derived**: computed from the OLTP layer when the warehouse is loaded.

## OLTP schema (`oltp`)

### Reference

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `stasiun` | The four stations (Halim, Karawang, Padalarang, Tegalluar) | Valid values for ticket origin and destination | New. Station names appear as free text in GTV tickets |
| `rute` | Route codes `01` Jaban (Jakarta-Bandung), `02` Jaka (Jakarta-Karawang), `03` Kaban (Karawang-Bandung) | Route of a card and of a BAK | FCC (`relasi_fcc` codes 01/02/03). Names confirmed by the project owner |
| `promo` | Promo campaigns with a date window and discount percent | Explains why a ticket got a discount: seasonal, company anniversary, group tier, loyalty | New. Discounts exist only as a price effect in GTV |

### Parties

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `perusahaan` | Fictional companies, agencies, schools, institutions | Second party of a BAK and sender in the bank statement. Lets one company book repeatedly | New. GTV only stores the name as text in `nama_pihak_kedua` |
| `pelanggan` | A synthetic person with a fake NIK and a segment (`komuter`, `sesekali`, `sekali`) | Single identity shared by tickets and cards, so repeat travel can be tracked. Segment drives churn and frequency models | New. GTV and FCC only keep name and ID number per row |

### Frequent customer card

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `fcc_kartu` | One card per row: owner, registration and expiry date, route, type G or S, remaining quota | Models loyalty. Quota and expiry follow the app rules (G: 10 trips, 60 days; S: 6 trips, 30 days) | FCC `maindata`. Added `pelanggan_id` (link to the person) and `kuota_awal` (initial quota, to check usage) |
| `fcc_redeem` | One quota use: order id, card, departure date, staff name, redeem time | Shows which tickets came from a card. `id_pesanan` equals the ticket `order_no`, so the redeem and the ticket can be joined | FCC `subdata`. Added `id_ticketsales` (direct link to the ticket) |

### Group booking and tickets

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `bak` | One group booking agreement (BAK) with a company: period, document number, route, passenger count, total value, total discount, status | Header of a group. A BAK is `pending` until its tickets are classified, then `checked` | GTV `dokumen_bak` (renamed). Added `perusahaan_id`, `kode_rute`, `jumlah_penumpang`, `total_nilai`, `total_diskon`. `bukti_transfer` and `manifest` became booleans |
| `bak_detail` | Departure dates of a BAK, one row per date | The date list used to match tickets to a BAK | GTV `dokumen_bak_detail` (renamed). Added a unique pair of BAK and date |
| `ticketsales` | One ticket per row. Main fact of the dataset (target 1,000,000 rows) | Core of ML and BI. Holds passenger, route, dates, class, base price, discount, tax and final price | GTV `data_ticketsales` (renamed). Dates became `date` and `time`. Price split into `base_price`, `discount_pct`, `discount_amount`, `tax`. Added `pelanggan_id`, `kode_promo`. the `bak` column is renamed `bak_id` and is now a real foreign key |

### Money

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `rekening_koran` | One bank statement line: date, account, credit or debit, amount, balance, sender name, sender account, bank, message | Evidence of group payments. Messages are free text and sometimes messy, so matching a line to a BAK is a real task | GTV `dokumen_rekeningkoran` held only file metadata. Rebuilt as transaction level |
| `pembayaran_bak` | Answer key linking a statement line to a BAK, with the payment kind (`lunas`, `dp`, `pelunasan`, `cicilan`, `lebih_bayar`) | Ground truth for payment matching and late-payment models. Not visible to the operational app | New |
| `label_anomali` | Marks rows that were deliberately corrupted (entity, id, kind) | Labels for anomaly detection. Kept apart so the main tables stay clean | New |

## Warehouse schema (`dwh`)

All warehouse tables are **Derived** from the OLTP schema.

### Dimensions

| Table | What it is | Purpose |
|---|---|---|
| `dim_date` | One row per calendar day with year, month, weekend, holiday, Lebaran window, school holiday and COVID phase | Time axis for every fact. Carries the calendar features used by forecasting |
| `dim_station` | Stations | Origin and destination of a ticket |
| `dim_route` | Route codes and city pairs | Grouping by route |
| `dim_customer` | Customers with age group, city, segment, card flag. Slowly changing (type 2) | Segment can change over time, so history is kept (`valid_from`, `valid_to`, `is_current`) |
| `dim_company` | Companies | Group booking analysis per company |
| `dim_promo` | Promos, with row `0` meaning no promo | Discount analysis by campaign |
| `dim_seat_class` | Seat classes | Price and mix by class |
| `dim_payment_method` | Payment methods | Payment mix |

### Facts

| Table | Grain | Purpose |
|---|---|---|
| `fact_ticket` | One ticket | Revenue, discount, lead days, group or card flags. Main fact for BI and ML |
| `fact_bak` | One BAK | Value, paid amount, payment gap, days to full payment, late flag. Target table for late-payment prediction |
| `fact_payment` | One bank statement line | Payment timing per company and BAK |
| `fact_fcc_redeem` | One card redeem | Card usage, quota left, redeem versus departure date |

### Aggregate

| Object | Grain | Purpose |
|---|---|---|
| `mv_daily_route_demand` | Departure day and route | Ready target for demand forecasting: tickets, revenue, average discount, group and card tickets |
