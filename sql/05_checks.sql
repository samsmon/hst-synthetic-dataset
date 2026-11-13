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
        AND h.job_position_id = ANY (CASE s.sales_channel_id WHEN 1 THEN ARRAY[1, 2, 3] WHEN 2 THEN ARRAY[10] ELSE ARRAY[8] END));

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
