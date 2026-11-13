# Table reference

What each table is, what it is for, and where its shape comes from. Column details are in [data-dictionary.md](data-dictionary.md); column-level renames are in [column-mapping.md](column-mapping.md).

Origin legend:

- **GTV**: group-ticket verification app (`kcic-ia-payroll`): `dokumen_bak`, `dokumen_bak_detail`, `data_ticketsales`, `dokumen_rekeningkoran`.
- **FCC**: frequent customer card admin app (`fcc-admin-system`): `maindata`, `subdata`.
- **New**: added for this dataset.

Conventions: every table has a surrogate key `id`, foreign keys are `<entity>_id`, employee roles are `<verb>_by_employee_id`, and one concept keeps one column name everywhere (for example `order_id`, `id_number`, `period`). Answer keys live in the separate schema `oltp_truth` (last section), so a pipeline that reads `oltp` never loads them.

## OLTP schema (`oltp`)

### Reference

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `station` | Four stations with city, province, address, coordinates, platforms, counter flag | Origin, destination and issue station of a ticket, home station of an employee | New (GTV had names as free text) |
| `route` | Route codes `01` Jakarta-Bandung (alias Jaban), `02` Jakarta-Karawang (Jaka), `03` Karawang-Bandung (Kaban) | Route of a ticket, card and booking | FCC (codes 01/02/03) |
| `route_segment` | Allowed station pairs per route and direction | Derives and enforces a ticket's route from its stations | New |
| `fare` | Base price per route and seat class with a validity window | Reference price; `ticket_sales.fare_id` points here | New |
| `promo` | Campaigns: type, who it applies to, minimum passengers, route, discount, dates | Explains discounts, for example a monthly deal for groups of at least 20 | New |
| `sales_channel` | Counter, group desk, FCC desk, agent portal, app, website, with a staffed flag | Tells whether an employee issued the ticket | New |
| `covid_phase` | Date windows of the COVID phases | Input of the demand model | New |
| `calendar_event` | Holidays and the Lebaran date per year | Calendar features. Only fixed-date holidays for now | New |

### Employees

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `department` | Ticketing, Station Operations, Customer Service, Sales, Finance | Organisation structure | New |
| `job_position` | Job titles with grade and department | Job detail for employees | New |
| `employee` | Current state of an employee: `nip`, name, gender, birth date, contact, hire and end date, status, position, home station, supervisor | Identifies who issued a ticket, handled a booking, registered a card, redeemed a quota or processed a refund | New (sources kept a staff name as text) |
| `employee_history` | One row per period of holding a position at a station | Career history: promotions and transfers | New |

### Parties

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `company` | Fictional agencies, corporates, schools, institutions, communities | Counterparty of a group booking and sender in the bank statement | New (GTV kept a name text) |
| `customer` | A synthetic person with a fake ID number (starts with 99) | One identity shared by tickets and cards, so repeat travel can be tracked | New |

### Frequent customer card

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `fcc_card` | One card: customer, registration and expiry date, route, type G or S, initial and remaining quota, registering employee | Models loyalty. Quota and expiry follow the app rules (G: 10 trips, 60 days; S: 6 trips, 30 days) | FCC `maindata`. Owner name, ID number and contact moved to `customer`; added `customer_id`, `initial_quota`, `registered_by_employee_id` |
| `fcc_redemption` | One quota use: order, card, ticket, departure date, employee, time | Shows which tickets came from a card. `order_id` equals the ticket `order_id` | FCC `subdata`. Staff name text became an employee link; added `ticket_sales_id` |

### Group booking, trips and tickets

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `group_booking` | One group booking agreement (BAK in the source), at least 20 passengers: company, period, dates, route, amounts, promo, status, employees | Header of a group. `pending` until its tickets are classified, then `checked` | GTV `dokumen_bak`. Added company, route, counts, amounts, promo, due date, employees |
| `group_booking_detail` | Departure dates of a booking | Date list used to match tickets to a booking | GTV `dokumen_bak_detail` |
| `trip` | One scheduled train run on a date with direction and seat capacity | Capacity and load factor; ties tickets to a run | New |
| `ticket_sales` | One ticket per row. Main table (about 10.8 million rows) | Core of ML and BI: passenger, trip, route, stations, dates, class, fare, base price, discount, service fee, total, status, channel, issuing employee and station | GTV `data_ticketsales`. Dates became `date` and `time`; price split into base, discount, fee and total; operator text replaced by employee link; added trip, route, fare, status |
| `refund` | Refund of a ticket: date, amount, fee, reason, processing employee | Cancellation analysis; turns a ticket into `refunded` | The GTV code read a `data_refund` table that its migrations never created |

### Money

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `bank_statement` | One bank line: date, code, direction, amount, running balance, sender, message | Evidence of payments, with unrelated lines (settlement, fees, interest, refund payouts) so matching is a real task | GTV `dokumen_rekeningkoran` held only file metadata; rebuilt at transaction level |

## Answer keys (`oltp_truth`)

Labels for ML and checks. They hold what the generator knows and the operational data hides. Never use them as features.

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `customer_truth` | Generator segment (`commuter`, `occasional`, `one_time`) and churn date per customer | Ground truth for churn tasks and for checking the data | New |
| `ticket_group_truth` | True booking of every group ticket | Label for classifying tickets of pending bookings (their `ticket_sales.group_booking_id` is NULL) | New |
| `group_booking_payment` | Allocation of a bank line to a booking, with payment type and amount. One line may pay several bookings | Ground truth for payment matching and late-payment checks | New |
| `anomaly_label` | Rows that were deliberately corrupted (entity type, id, anomaly type) | Labels for anomaly detection | New |
