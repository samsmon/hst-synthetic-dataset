# Column mapping

How source names (Indonesian or mixed) map to the English names used here. Columns that mean the same thing now share one name in every table.

## Table names

| Source | Here |
|---|---|
| `dokumen_bak` | `group_booking` |
| `dokumen_bak_detail` | `group_booking_detail` |
| `data_ticketsales` | `ticket_sales` |
| `dokumen_rekeningkoran` | `bank_statement` |
| `maindata` | `fcc_card` |
| `subdata` | `fcc_redemption` |

## Unified columns

| Concept | Source names | Here |
|---|---|---|
| Order reference | `id_pesanan` (redeem), `order_no` (ticket) | `order_id` |
| ID number | `id_num` (card), `nik_passport_no` (ticket) | `id_number`, `passenger_id_number` on tickets |
| Card reference | `id_fwc`, `id_fcc` | `card_no` on the card, `card_id` (foreign key) elsewhere |
| Booking reference | `bak`, `dokumen_bak_id` | `group_booking_id` |
| Period | `periode` | `period` |
| Departure date | `tgl_departure`, `departure_date`, `tanggal_keberangkatan` | `departure_date` |
| Registration and expiry | `tgl_reg`, `tgl_exp` | `registration_date`, `expiry_date` |
| Discount | `total_diskon` (booking), none (ticket) | `discount_amount` in both tables |
| Total money | `total_nilai` (booking), `after_tax_price` (ticket) | `total_amount` (booking), `total_price` (ticket) |
| Who did it | `user` text, `operator_name` text | `<verb>_by_employee_id` foreign keys |

## Other renames

| Source | Here |
|---|---|
| `nama`, `kota`, `no_hp`, `keterangan` | `name`, `city`, `phone`, `notes` |
| `nama_pihak_kedua` | `counterparty_name` |
| `no_dokumen`, `tanggal_dokumen` | `booking_no`, `document_date` |
| `jumlah_penumpang` | `passenger_count` |
| `bukti_transfer`, `manifest` | `has_transfer_proof`, `has_manifest` |
| `relasi_fwc`, `jenis_fwc`, `kuota` | `route_id`, `card_type`, `remaining_quota` (plus new `initial_quota`) |
| `nomor_rekening`, `berita` | `account_no`, `message` |
| `trade_no`, `plat_trade_no` | `payment_ref`, `platform_payment_ref` |

## Value changes

| Column | Source or earlier value | Here |
|---|---|---|
| `customer.segment` | komuter, sesekali, sekali | `commuter`, `occasional`, `one_time` |
| `ticket_sales.seat_class` | ekonomi, bisnis | `economy`, `business` (plus `premium`, `first`) |
| `bank_statement.direction` | CR, DB | `credit`, `debit` |
| `group_booking_payment.payment_type` | lunas, dp, pelunasan, cicilan, lebih_bayar | `full`, `deposit`, `final`, `instalment`, `overpayment` |
| `dim_date.covid_phase` | ppkm | `restrictions` |

People and company names stay Indonesian (generated with an Indonesian locale) for realism. Everything else, including column names, values and transfer messages, is English.
