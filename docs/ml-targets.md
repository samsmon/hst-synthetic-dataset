# ML targets

Task definitions for the dataset. Every task is built from the tables in schema `oltp`; labels that the operational data hides come from schema `oltp_truth`. All splits are by time, never random: the COVID shock changes the data regime, so a random split would leak the future.

## Leakage rules

- The `oltp_truth` tables are labels only. They are never features: `customer_truth`, `ticket_group_truth`, `group_booking_payment`, `anomaly_label`.
- `customer_truth.segment` and `churn_date` are generator facts. A segment used as a feature must be derived from ticket behaviour (recency, frequency, value) up to the snapshot date.
- Features use only information available at prediction time. Aggregates (for example a company's past lateness) are computed from rows before that time.

## Derived quantities

Quantities used by several tasks, all computed from `oltp`:

| Quantity | Definition |
|---|---|
| Daily demand | Count of `ticket_sales` per `departure_date` and `route_id`, excluding `status = 'cancelled'` |
| Calendar features | From the date, `calendar_event`, `covid_phase` and the Lebaran date (H-7 to H+7 window) |
| Scheduled capacity | Sum of `trip.seat_capacity` per `service_date` and direction |
| Paid amount of a booking | Sum of credit lines in `bank_statement` allocated to it. Only the labelled allocation in `oltp_truth.group_booking_payment` gives the exact amount, so tasks 4 and 5 use it as the label side |
| Late payment (`is_late`) | The booking is fully paid after `group_booking.payment_due_date`, or still unpaid at the end of the data after that date |
| Behaviour segment | From a customer's tickets before the snapshot date: new (first trip within 90 days), regular (2 to 5 trips in 12 months), frequent (6 or more), lapsed (no trip in 180 days) |

## Tasks

| # | Task | Unit and label | Features | Split | Metric |
|---|---|---|---|---|---|
| 1 | Demand forecasting | Daily demand per route, horizon 1 to 28 days | Calendar features, lags of daily demand, active promo flag (`promo` date window), scheduled capacity | Train 2021-10 to 2024-06, validate 2024-07 to 2024-12, test 2025. Extra stress test on 2020 to 2021 | WAPE |
| 2 | Discount prediction | `ticket_sales.discount_pct` per ticket | `lead_days` (departure minus purchase), channel, route, seat class, group size, calendar features, demand index from tasks 1. Not `discount_amount` or `total_price` | Same as task 1 | MAE |
| 3 | Customer churn | At each month-end snapshot S, customers with at least 2 tickets in the 12 months before S. Label 1 if no ticket in the 180 days after S | Behaviour segment, recency, frequency, value, route mix, lead days, card usage, refunds, all up to S | Train snapshots 2021-12 to 2023-12, validate 2024, test 2025-01 to 2025-06 (last snapshot with a full horizon) | PR-AUC |
| 4 | Late payment | One group booking, label `is_late` | Company type and its past lateness, `total_amount`, `passenger_count`, promo, days from `document_date` to first departure, month. Known at document date | By `document_date`, last year as test | PR-AUC, recall at fixed precision |
| 5 | Payment matching | Bank credit line to booking(s), label `oltp_truth.group_booking_payment` | Amount, date gap, name similarity between `sender_name` and company, message text, company history. Candidates are open bookings | By `transaction_date` | Top-1 accuracy, F1 |
| 6 | Group ticket classification | Ticket with NULL `group_booking_id` to its booking, label `oltp_truth.ticket_group_truth` | Departure date against `group_booking_detail` dates, route, passenger counts, company | Pending bookings are the test set | Accuracy |
| 7 | Anomaly detection | Row flag, label `oltp_truth.anomaly_label` | Row features plus aggregates, no label columns | By time, last year as test | PR-AUC (anomalies are 1 to 3 percent) |

## Notes

- Positive rates differ by task and period (churn is low in 2020 to 2021 because few customers exist). Report metrics per period as well as overall.
- The 2020 lockdown refund spike is a deliberate regime change. Keep it in the stress test, not in the main training window.
- Sizes are in [design.md](design.md); column meanings in [data-dictionary.md](data-dictionary.md).
