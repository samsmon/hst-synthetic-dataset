-- Checks that table constraints cannot express. Run after the data is loaded.
-- Every query returns one row; a value other than 0 means a problem.
-- psql -f sql/05_checks.sql

SELECT 'tickets above trip capacity' AS check_name, count(*) AS problems
FROM (SELECT trip_id, count(*) AS n FROM oltp.ticket_sales GROUP BY trip_id) x
JOIN oltp.trip t ON t.id = x.trip_id
WHERE x.n > t.seat_capacity;

SELECT 'ticket date differs from its trip', count(*)
FROM oltp.ticket_sales s JOIN oltp.trip t ON t.id = s.trip_id
WHERE s.departure_date <> t.service_date;

SELECT 'station order does not match trip direction', count(*)
FROM oltp.ticket_sales s JOIN oltp.trip t ON t.id = s.trip_id
WHERE (t.direction = 'to_bandung' AND s.origin_station_id > s.destination_station_id)
   OR (t.direction = 'to_jakarta' AND s.origin_station_id < s.destination_station_id);

SELECT 'staffed channel without employee or station', count(*)
FROM oltp.ticket_sales
WHERE sales_channel_id IN (1, 2, 3) AND (issued_by_employee_id IS NULL OR issue_station_id IS NULL);

SELECT 'self-service channel with an employee', count(*)
FROM oltp.ticket_sales
WHERE sales_channel_id IN (4, 5, 6) AND (issued_by_employee_id IS NOT NULL OR issue_station_id IS NOT NULL);

SELECT 'issuer not on duty in the right role and station', count(*)
FROM oltp.ticket_sales s
WHERE s.issued_by_employee_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM oltp.employee_history h
      WHERE h.employee_id = s.issued_by_employee_id
        AND h.valid_from <= s.purchase_date AND (h.valid_to IS NULL OR h.valid_to > s.purchase_date)
        AND h.home_station_id = s.issue_station_id
        AND h.job_position_id = ANY (CASE s.sales_channel_id WHEN 1 THEN ARRAY[1, 2, 3] WHEN 2 THEN ARRAY[10] ELSE ARRAY[8] END))
  AND NOT EXISTS (
      SELECT 1 FROM oltp_truth.anomaly_label a
      WHERE a.entity_type = 'ticket_sales' AND a.entity_id = s.id AND a.anomaly_type = 'inactive_issuer');

SELECT 'individual promo outside its window or audience', count(*)
FROM oltp.ticket_sales s JOIN oltp.promo p ON p.id = s.promo_id
WHERE s.group_booking_id IS NULL
  AND NOT EXISTS (SELECT 1 FROM oltp_truth.ticket_group_truth t WHERE t.ticket_sales_id = s.id)   -- not a ticket of a pending booking
  AND (s.purchase_date NOT BETWEEN p.start_date AND p.end_date
       OR p.applies_to = 'group' OR (p.applies_to = 'fcc' AND s.sales_channel_id <> 3));

SELECT 'booking promo outside window or below minimum passengers', count(*)
FROM oltp.group_booking b JOIN oltp.promo p ON p.id = b.promo_id
WHERE b.document_date NOT BETWEEN p.start_date AND p.end_date
   OR b.passenger_count < COALESCE(p.min_pax, 0) OR p.applies_to NOT IN ('group', 'all');

WITH group_tickets AS (
    SELECT s.id, COALESCE(s.group_booking_id, t.group_booking_id) AS booking_id, s.departure_date, s.total_price
    FROM oltp.ticket_sales s
    LEFT JOIN oltp_truth.ticket_group_truth t ON t.ticket_sales_id = s.id
    WHERE s.group_booking_id IS NOT NULL OR t.ticket_sales_id IS NOT NULL)
SELECT 'booking total differs from its ticket prices', count(*)
FROM oltp.group_booking b
JOIN (SELECT booking_id, sum(total_price) AS total FROM group_tickets GROUP BY booking_id) g ON g.booking_id = b.id
WHERE b.total_amount <> g.total;

WITH group_tickets AS (
    SELECT COALESCE(s.group_booking_id, t.group_booking_id) AS booking_id, s.departure_date
    FROM oltp.ticket_sales s
    LEFT JOIN oltp_truth.ticket_group_truth t ON t.ticket_sales_id = s.id
    WHERE s.group_booking_id IS NOT NULL OR t.ticket_sales_id IS NOT NULL)
SELECT 'tickets per booking date differ from passenger count', count(*)
FROM (SELECT booking_id, departure_date, count(*) AS n FROM group_tickets GROUP BY 1, 2) g
JOIN oltp.group_booking b ON b.id = g.booking_id
WHERE g.n <> b.passenger_count;

SELECT 'booking detail dates differ from ticket dates', count(*)
FROM oltp.group_booking_detail d
WHERE NOT EXISTS (SELECT 1 FROM oltp.ticket_sales s
                  LEFT JOIN oltp_truth.ticket_group_truth t ON t.ticket_sales_id = s.id
                  WHERE COALESCE(s.group_booking_id, t.group_booking_id) = d.group_booking_id
                    AND s.departure_date = d.departure_date);

SELECT 'pending booking with a classified ticket', count(*)
FROM oltp.ticket_sales s JOIN oltp.group_booking b ON b.id = s.group_booking_id
WHERE b.status = 'pending';

SELECT 'customer without a ticket', count(*)
FROM oltp.customer c WHERE NOT EXISTS (SELECT 1 FROM oltp.ticket_sales s WHERE s.customer_id = c.id);

SELECT 'customer created after the first purchase', count(*)
FROM oltp.customer c
JOIN (SELECT customer_id, min(purchase_date) AS first_purchase FROM oltp.ticket_sales
      WHERE customer_id IS NOT NULL GROUP BY customer_id) f ON f.customer_id = c.id
WHERE c.created_at::date > f.first_purchase;

-- ------------------------------------------------------------- stage 4 checks
SELECT 'redemption outside card validity or quota exceeded', count(*)
FROM (
    SELECT r.card_id, count(*) AS cnt, c.initial_quota,
           min(r.redeemed_at::date) AS min_red, max(r.redeemed_at::date) AS max_red,
           c.registration_date, c.expiry_date
    FROM oltp.fcc_redemption r
    JOIN oltp.fcc_card c ON c.id = r.card_id
    GROUP BY r.card_id, c.initial_quota, c.registration_date, c.expiry_date
) x
WHERE x.cnt > x.initial_quota
   OR x.min_red < x.registration_date
   OR x.max_red > x.expiry_date;

SELECT 'card remaining quota mismatch', count(*)
FROM oltp.fcc_card c
LEFT JOIN (
    SELECT card_id, count(*) AS cnt FROM oltp.fcc_redemption GROUP BY card_id
) r ON r.card_id = c.id
WHERE c.remaining_quota <> (c.initial_quota - COALESCE(r.cnt, 0));

SELECT 'card route differs from ticket route', count(*)
FROM oltp.fcc_redemption r
JOIN oltp.fcc_card c ON c.id = r.card_id
JOIN oltp.ticket_sales t ON t.id = r.ticket_sales_id
WHERE c.route_id <> t.route_id;

SELECT 'refund date after departure date or before purchase date', count(*)
FROM oltp.refund r
JOIN oltp.ticket_sales t ON t.id = r.ticket_sales_id
WHERE r.refund_date > t.departure_date OR r.refund_date < t.purchase_date;

SELECT 'refund amount exceeds total price', count(*)
FROM oltp.refund r
JOIN oltp.ticket_sales t ON t.id = r.ticket_sales_id
WHERE r.refund_amount > t.total_price;

SELECT 'refunded ticket without refund row', count(*)
FROM oltp.ticket_sales t
LEFT JOIN oltp.refund r ON r.ticket_sales_id = t.id
WHERE t.status = 'refunded' AND r.id IS NULL;

SELECT 'non-refunded ticket with refund row', count(*)
FROM oltp.ticket_sales t
JOIN oltp.refund r ON r.ticket_sales_id = t.id
WHERE t.status <> 'refunded';

SELECT 'discontinuous bank balance', count(*)
FROM (
    SELECT account_no, transaction_date, id, direction, amount, balance,
           LAG(balance) OVER (PARTITION BY account_no ORDER BY transaction_date, id) AS prev_balance
    FROM oltp.bank_statement
) x
WHERE prev_balance IS NOT NULL
  AND balance <> (CASE WHEN direction = 'credit' THEN prev_balance + amount ELSE prev_balance - amount END);

SELECT 'clean booking payments differ from total amount', count(*)
FROM oltp.group_booking b
LEFT JOIN (
    SELECT group_booking_id, sum(allocated_amount) AS total_paid
    FROM oltp_truth.group_booking_payment
    GROUP BY group_booking_id
) p ON p.group_booking_id = b.id
WHERE b.status = 'checked'
  AND NOT EXISTS (
      SELECT 1 FROM oltp_truth.anomaly_label a
      WHERE a.entity_type = 'group_booking' AND a.entity_id = b.id AND a.anomaly_type IN ('underpayment', 'overpayment'))
  AND COALESCE(p.total_paid, 0) <> b.total_amount;

SELECT 'bank credit over-allocated', count(*)
FROM oltp.bank_statement s
JOIN (
    SELECT bank_statement_id, sum(allocated_amount) AS total_alloc
    FROM oltp_truth.group_booking_payment
    GROUP BY bank_statement_id
) p ON p.bank_statement_id = s.id
WHERE p.total_alloc > s.amount;

-- ------------------------------------------------------------- stage 5 checks
SELECT 'anomaly label referencing non-existent ticket', count(*)
FROM oltp_truth.anomaly_label a
LEFT JOIN oltp.ticket_sales t ON t.id = a.entity_id
WHERE a.entity_type = 'ticket_sales' AND t.id IS NULL;

SELECT 'anomaly label referencing non-existent booking', count(*)
FROM oltp_truth.anomaly_label a
LEFT JOIN oltp.group_booking b ON b.id = a.entity_id
WHERE a.entity_type = 'group_booking' AND b.id IS NULL;

SELECT 'anomaly label referencing non-existent bank statement', count(*)
FROM oltp_truth.anomaly_label a
LEFT JOIN oltp.bank_statement s ON s.id = a.entity_id
WHERE a.entity_type = 'bank_statement' AND s.id IS NULL;

SELECT 'underpayment booking not actually underpaid', count(*)
FROM oltp_truth.anomaly_label a
JOIN oltp.group_booking b ON b.id = a.entity_id
LEFT JOIN (
    SELECT group_booking_id, sum(allocated_amount) AS total_paid
    FROM oltp_truth.group_booking_payment
    GROUP BY group_booking_id
) p ON p.group_booking_id = b.id
WHERE a.entity_type = 'group_booking' AND a.anomaly_type = 'underpayment'
  AND COALESCE(p.total_paid, 0) >= b.total_amount;

SELECT 'overpayment booking not actually overpaid', count(*)
FROM oltp_truth.anomaly_label a
JOIN oltp.group_booking b ON b.id = a.entity_id
LEFT JOIN (
    SELECT group_booking_id, sum(allocated_amount) AS total_paid
    FROM oltp_truth.group_booking_payment
    GROUP BY group_booking_id
) p ON p.group_booking_id = b.id
WHERE a.entity_type = 'group_booking' AND a.anomaly_type = 'overpayment'
  AND COALESCE(p.total_paid, 0) <= b.total_amount;

SELECT 'duplicate ticket without a duplicate partner', count(*)
FROM oltp_truth.anomaly_label a
JOIN oltp.ticket_sales t ON t.id = a.entity_id
WHERE a.entity_type = 'ticket_sales' AND a.anomaly_type = 'duplicate_ticket'
  AND NOT EXISTS (
      SELECT 1 FROM oltp.ticket_sales o
      WHERE o.id <> t.id AND o.passenger_id_number = t.passenger_id_number AND o.trip_id = t.trip_id
  );


