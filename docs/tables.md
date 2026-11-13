# Table reference

What each table is, what it is for, and where its shape comes from. Column-level renames are in [column-mapping.md](column-mapping.md).

Origin legend:

- **GTV**: group-ticket verification app (`kcic-ia-payroll`): `dokumen_bak`, `dokumen_bak_detail`, `data_ticketsales`, `dokumen_rekeningkoran`.
- **FCC**: frequent customer card admin app (`fcc-admin-system`): `maindata`, `subdata`.
- **New**: added for this dataset.
- **Derived**: computed from the OLTP layer when the warehouse is loaded.

Conventions: every table has a surrogate key `id`, foreign keys are `<entity>_id`, employee roles are `<verb>_by_employee_id`, and one concept keeps one column name everywhere (for example `order_id`, `id_number`, `period`).

## OLTP schema (`oltp`)

### Reference

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `station` | The four stations with city, province, address, coordinates, platform count, counter flag | Valid origin, destination and issue station of a ticket, and home station of an employee | New (GTV had station names as free text) |
| `route` | Route codes `01` Jakarta-Bandung (local alias Jaban), `02` Jakarta-Karawang (Jaka), `03` Karawang-Bandung (Kaban) | Route of a card and of a group booking | FCC (codes 01/02/03) |
| `promo` | Campaigns with a date window and discount percent (anniversary, seasonal, group, loyalty) | Explains why a ticket got a discount | New |
| `sales_channel` | Counter, group desk, FCC desk, agent portal, app, website, with a staffed flag | Tells whether an employee issued the ticket | New |

### Employees

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `department` | Ticketing, Station Operations, Customer Service, Sales, Finance | Organisation structure | New |
| `position` | Job titles with grade and department | Job detail for employees | New |
| `employee` | One employee: `nip`, name, gender, birth date, contact, hire and end date, status, position, home station, supervisor | Identifies who issued a ticket, created or verified a booking, registered a card or redeemed a quota. Hire and end dates keep activity consistent over time | New (FCC and GTV only kept a staff name as text) |

### Parties

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `company` | Fictional agencies, corporates, schools, institutions, communities | Counterparty of a group booking and sender in the bank statement | New (GTV kept only a name text) |
| `customer` | A synthetic person with a fake ID number and a segment (`commuter`, `occasional`, `one_time`) | One identity shared by tickets and cards, so repeat travel can be tracked | New |

### Frequent customer card

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `fcc_card` | One card: owner, registration and expiry date, route, type G or S, initial and remaining quota, registering employee | Models loyalty. Quota and expiry follow the app rules (G: 10 trips, 60 days; S: 6 trips, 30 days) | FCC `maindata`. Added `customer_id`, `initial_quota`, `registered_by_employee_id` |
| `fcc_redemption` | One quota use: order, card, ticket, departure date, redeeming employee, time | Shows which tickets came from a card. `order_id` equals the ticket `order_id` | FCC `subdata`. Staff name text replaced by `redeemed_by_employee_id`; added `ticket_sales_id` |

### Group booking and tickets

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `group_booking` | One group booking agreement (BAK in the source) with a company: period, number, route, passenger count, total and discount amount, status, creating and verifying employee | Header of a group. `pending` until its tickets are classified, then `checked` | GTV `dokumen_bak`. Added company, route, counts, amounts, employees |
| `group_booking_detail` | Departure dates of a booking, one row per date | Date list used to match tickets to a booking | GTV `dokumen_bak_detail` |
| `ticket_sales` | One ticket per row. Main table of the dataset (target 1,000,000 rows) | Core of ML and BI. Passenger, route, dates, class, base price, discount, tax, total, channel, issuing employee and station | GTV `data_ticketsales`. Dates became `date` and `time`; price split into base, discount, tax and total; operator name replaced by the employee link |

### Money

| Table | What it is | Purpose | Origin |
|---|---|---|---|
| `bank_statement` | One bank line: date, account, credit or debit, amount, balance, sender name, sender account, bank, message | Evidence of group payments. Messages are free text and sometimes messy, so matching to a booking is a real task | GTV `dokumen_rekeningkoran` held only file metadata; rebuilt at transaction level |
| `group_booking_payment` | Answer key linking a statement line to a booking, with the payment type (`full`, `deposit`, `final`, `instalment`, `overpayment`) | Ground truth for payment matching and late-payment models. Not visible to the operational app | New |
| `anomaly_label` | Marks rows that were deliberately corrupted (entity type, id, anomaly type) | Labels for anomaly detection, kept apart so the main tables stay clean | New |

## Warehouse schema (`dwh`)

All warehouse tables are **Derived** from the OLTP schema.

### Dimensions

| Table | What it is | Purpose |
|---|---|---|
| `dim_date` | One row per day with year, month, weekend, holiday, Lebaran window, school holiday, COVID phase | Time axis for every fact and the calendar features for forecasting |
| `dim_station` | Stations with city, province, coordinates | Origin, destination and issue station |
| `dim_route` | Routes and city pairs | Grouping by route |
| `dim_customer` | Customers with age group, city, segment, card flag. SCD type 2 | Keeps segment history |
| `dim_company` | Companies | Group booking analysis per company |
| `dim_employee` | Employees with position, grade, department, status, home station. SCD type 2 | Sales and workload by employee, keeping history of promotions and moves |
| `dim_promo` | Promos, row `0` meaning no promo | Discount analysis by campaign |
| `dim_seat_class` | Seat classes | Price and mix by class |
| `dim_payment_method` | Payment methods | Payment mix |
| `dim_sales_channel` | Sales channels | Channel mix and staffed versus self-service |

### Facts

| Table | Grain | Purpose |
|---|---|---|
| `fact_ticket` | One ticket | Revenue, discount, lead days, flags, issuing employee and station. Main fact for BI and ML |
| `fact_group_booking` | One group booking | Value, paid amount, payment gap, days to full payment, late flag, creating and verifying employee |
| `fact_payment` | One bank statement line | Payment timing per company and booking |
| `fact_fcc_redemption` | One card redemption | Card usage, quota left, redeeming employee |

### Aggregates

| Object | Grain | Purpose |
|---|---|---|
| `mv_daily_route_demand` | Departure day and route | Target for demand forecasting: tickets, revenue, average discount, group and card tickets |
| `mv_employee_monthly_sales` | Employee and month | Tickets issued and revenue per employee, for workload and performance analysis |
