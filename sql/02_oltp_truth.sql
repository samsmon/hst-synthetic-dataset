-- Answer keys in their own schema (PostgreSQL 14+). Run after 01_oltp.sql.
--
-- These tables hold what the generator knows and the operational data hides:
-- true links, generator parameters and injected errors. They are labels for ML
-- and checks only. A pipeline that reads schema oltp never loads them.

CREATE SCHEMA IF NOT EXISTS oltp_truth;
SET search_path TO oltp_truth;

-- One transfer may pay several bookings, so the key is (statement line, booking).
CREATE TABLE group_booking_payment (
    bank_statement_id bigint NOT NULL REFERENCES oltp.bank_statement(id),
    group_booking_id  bigint NOT NULL REFERENCES oltp.group_booking(id),
    payment_type      text NOT NULL CHECK (payment_type IN ('full', 'deposit', 'final', 'instalment', 'overpayment')),
    allocated_amount  numeric(14,2) NOT NULL CHECK (allocated_amount > 0),
    PRIMARY KEY (bank_statement_id, group_booking_id)
);
CREATE INDEX ix_gbp_booking ON group_booking_payment (group_booking_id);

-- The true booking of every group ticket, also while oltp shows NULL.
CREATE TABLE ticket_group_truth (
    ticket_sales_id  bigint PRIMARY KEY REFERENCES oltp.ticket_sales(id),
    group_booking_id bigint NOT NULL REFERENCES oltp.group_booking(id)
);

-- Generator parameters per customer. Never use these as features.
CREATE TABLE customer_truth (
    customer_id bigint PRIMARY KEY REFERENCES oltp.customer(id),
    segment     text NOT NULL CHECK (segment IN ('commuter', 'occasional', 'one_time')),
    churn_date  date                                   -- date the customer stopped travelling, NULL if never
);

CREATE TABLE anomaly_label (
    id           bigserial PRIMARY KEY,
    entity_type  text NOT NULL CHECK (entity_type IN ('ticket_sales', 'group_booking', 'bank_statement', 'fcc_redemption')),
    entity_id    bigint NOT NULL,
    anomaly_type text NOT NULL,   -- e.g. underpayment, duplicate_ticket, name_mismatch
    UNIQUE (entity_type, entity_id, anomaly_type)
);
