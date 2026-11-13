-- Table and column comments for the oltp and oltp_truth schemas.
-- Run after 01_oltp.sql and 02_oltp_truth.sql.
-- scripts/build_dictionary.py turns these into docs/data-dictionary.md.

SET search_path TO oltp;

COMMENT ON TABLE station IS 'The four stations with location and facility data.';
COMMENT ON TABLE route IS 'Route product: 01 Jakarta-Bandung (Jaban), 02 Jakarta-Karawang (Jaka), 03 Karawang-Bandung (Kaban).';
COMMENT ON TABLE route_segment IS 'Station pairs that can be sold as a ticket, per route and direction.';
COMMENT ON TABLE fare IS 'Base price per route and seat class with a validity window.';
COMMENT ON TABLE promo IS 'Discount campaigns, for example a monthly deal for group trips with a passenger minimum.';
COMMENT ON TABLE sales_channel IS 'Where a ticket was sold. Staffed channels record the issuing employee.';
COMMENT ON TABLE covid_phase IS 'Date windows of the COVID phases used by the demand model.';
COMMENT ON TABLE calendar_event IS 'Holidays and the Lebaran date per year (fixed-date holidays only for now).';
COMMENT ON TABLE department IS 'Organisation departments.';
COMMENT ON TABLE job_position IS 'Job titles with grade and department.';
COMMENT ON TABLE employee IS 'Employees, current state. Latest employee_history row must match.';
COMMENT ON TABLE employee_history IS 'Position and station history of each employee (promotions, transfers).';
COMMENT ON TABLE company IS 'Fictional organisations that book group trips and pay by bank transfer.';
COMMENT ON TABLE customer IS 'A synthetic person. Segment and churn are generator facts kept in oltp_truth.customer_truth.';
COMMENT ON TABLE fcc_card IS 'Frequent customer card with route, quota and validity.';
COMMENT ON TABLE group_booking IS 'Group booking agreement (BAK in the source app). At least 20 passengers.';
COMMENT ON TABLE group_booking_detail IS 'Departure dates of a group booking, one row per date.';
COMMENT ON TABLE trip IS 'One scheduled train run on a date with its seat capacity.';
COMMENT ON TABLE ticket_sales IS 'One ticket per row. Main table of the dataset.';
COMMENT ON TABLE refund IS 'Refund of a ticket. The ticket status becomes refunded.';
COMMENT ON TABLE fcc_redemption IS 'One use of a card quota; order_id equals the ticket order_id.';
COMMENT ON TABLE bank_statement IS 'Bank account lines, including lines unrelated to group bookings.';
COMMENT ON TABLE oltp_truth.group_booking_payment IS 'ANSWER KEY. Which bank line paid which booking, and how much of it.';
COMMENT ON TABLE oltp_truth.ticket_group_truth IS 'ANSWER KEY. True booking of every group ticket.';
COMMENT ON TABLE oltp_truth.customer_truth IS 'ANSWER KEY. Generator segment and churn date per customer.';
COMMENT ON TABLE oltp_truth.anomaly_label IS 'ANSWER KEY. Rows that were deliberately corrupted.';

COMMENT ON COLUMN promo.applies_to IS 'all, group, individual or fcc.';
COMMENT ON COLUMN promo.min_pax IS 'Minimum passengers of a group booking to qualify; at least 20 when applies_to is group.';
COMMENT ON COLUMN promo.route_id IS 'NULL means the promo covers all routes.';
COMMENT ON COLUMN fare.valid_to IS 'NULL means the fare is still valid.';
COMMENT ON COLUMN sales_channel.is_staffed IS 'False for self-service channels where no employee issues the ticket.';
COMMENT ON COLUMN employee.nip IS 'Employee number (NIP), synthetic.';
COMMENT ON COLUMN employee.end_date IS 'Last employment date; NULL while employed.';
COMMENT ON COLUMN customer.id_number IS 'Synthetic ID or passport number. Indonesian IDs start with 99 so they never match a real NIK.';
COMMENT ON COLUMN fcc_card.card_type IS 'G: quota 10, 60 days. S: quota 6, 30 days. Meaning of the letters unconfirmed.';
COMMENT ON COLUMN group_booking.period IS 'Month (YYYY-MM) of the first departure.';
COMMENT ON COLUMN group_booking.counterparty_name IS 'Name as written on the document; may differ from company.name.';
COMMENT ON COLUMN group_booking.payment_due_date IS 'A booking is late when fully paid after this date.';
COMMENT ON COLUMN group_booking.status IS 'pending until its tickets are classified, then checked.';
COMMENT ON COLUMN trip.direction IS 'to_bandung or to_jakarta.';
COMMENT ON COLUMN ticket_sales.period IS 'Month (YYYY-MM) of departure_date, enforced by a CHECK.';
COMMENT ON COLUMN ticket_sales.group_booking_id IS 'NULL for individual tickets and for tickets of pending bookings (truth in oltp_truth.ticket_group_truth).';
COMMENT ON COLUMN ticket_sales.status IS 'issued, used, cancelled or refunded.';
COMMENT ON COLUMN ticket_sales.route_id IS 'Derived from the origin and destination pair through route_segment.';
COMMENT ON COLUMN ticket_sales.base_price IS 'Fare price plus a peak uplift in crowded windows, rounded to Rp 1,000.';
COMMENT ON COLUMN ticket_sales.discount_pct IS 'Combined demand, group tier and promo discount, capped at 40.';
COMMENT ON COLUMN ticket_sales.service_fee_amount IS 'Admin fee by channel, added after the discount. Tax is not modelled (assumed inside the fare).';
COMMENT ON COLUMN ticket_sales.total_price IS 'base_price - discount_amount + service_fee_amount.';
COMMENT ON COLUMN ticket_sales.issued_by_employee_id IS 'NULL for self-service channels.';
COMMENT ON COLUMN ticket_sales.issue_station_id IS 'Station of the issuing employee; NULL for online channels.';
COMMENT ON COLUMN refund.reason IS 'schedule_change, customer_request, illness, duplicate_booking or other.';
COMMENT ON COLUMN bank_statement.transaction_code IS 'TRF transfer, SETTLE gateway settlement, FEE bank fee, INT interest, REFUND payout, OTHER.';
COMMENT ON COLUMN bank_statement.balance IS 'Running balance per account, in date and id order.';
COMMENT ON COLUMN bank_statement.message IS 'Free-text transfer message; sometimes abbreviated or misspelled.';
COMMENT ON COLUMN oltp_truth.group_booking_payment.allocated_amount IS 'Part of the bank line applied to this booking; one line may pay several bookings.';
COMMENT ON COLUMN oltp_truth.customer_truth.churn_date IS 'Date the customer stopped travelling; NULL if the customer never churned.';
COMMENT ON COLUMN oltp_truth.anomaly_label.anomaly_type IS 'underpayment, overpayment, duplicate_payment, name_mismatch, duplicate_ticket, date_outlier or inactive_issuer.';
