# ML targets

Task definitions for the dataset. All splits are by time, never random: the COVID shock changes the data regime, so a random split would leak the future.

## Leakage rules

- Answer-key tables (`customer_truth`, `ticket_group_truth`, `group_booking_payment`, `anomaly_label`) are labels only. They are never features.
- `customer_truth.segment` and `churn_date` are generator facts. The warehouse segment (`dim_customer.segment`) is derived from behaviour up to the snapshot date.
- Features use only information available at prediction time. Aggregates (for example a company's past lateness) are computed from rows before that time.

## Tasks

| # | Task | Unit and label | Features | Split | Metric |
|---|---|---|---|---|---|
| 1 | Demand forecasting | Tickets per departure day and route (`mv_daily_route_demand.tickets`), horizon 1 to 28 days | Calendar and COVID phase from `dim_date`, lags, active promo flag, scheduled trip capacity | Train 2021-10 to 2024-06, validate 2024-07 to 2024-12, test 2025. Extra stress test on 2020 to 2021 | WAPE |
| 2 | Discount prediction | `ticket_sales.discount_pct` per ticket | Lead days, channel, route, seat class, group size, demand index, calendar. Not `discount_amount` or `total_price` | Same as task 1 | MAE |
| 3 | Customer churn | At each month-end snapshot S, customers with at least 2 tickets in the 12 months before S. Label 1 if no ticket in the 180 days after S | Recency, frequency, value, route mix, lead days, card usage, refunds up to S | Train snapshots 2021-12 to 2023-12, validate 2024, test 2025-01 to 2025-06 (last snapshot with a full horizon) | PR-AUC |
| 4 | Late payment | One group booking, label `fact_group_booking.is_late` | Company type and past lateness, amount, passengers, promo, lead time to departure, month. Known at document date | By `document_date`, last year as test | PR-AUC, recall at fixed precision |
| 5 | Payment matching | Bank credit line to booking(s), label `group_booking_payment` | Amount, date gap, name similarity, message text, company history. Candidates are open bookings | By `transaction_date` | Top-1 accuracy, F1 |
| 6 | Group ticket classification | Ticket with NULL booking to its booking, label `ticket_group_truth` | Departure date against booking dates, route, passenger counts, company | Pending bookings are the test set | Accuracy |
| 7 | Anomaly detection | Row flag, label `anomaly_label` | Row features plus aggregates, no label columns | By time, last year as test | PR-AUC (anomalies are 1 to 3 percent) |

## Notes

- Positive rates differ by task and period (churn is low in 2020 to 2021 because few customers exist). Report metrics per period as well as overall.
- The 2020 lockdown refund spike is a deliberate regime change. Keep it in the stress test, not in the main training window.
- Sizes are in [design.md](design.md); column meanings in [data-dictionary.md](data-dictionary.md).
