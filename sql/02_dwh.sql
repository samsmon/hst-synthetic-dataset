-- DWH layer: star schema built from the oltp schema (PostgreSQL 14+).
-- Dimensions use surrogate keys; facts keep the oltp id as a degenerate key.

CREATE SCHEMA IF NOT EXISTS dwh;
SET search_path TO dwh;

-- --------------------------------------------------------------- dimensions
CREATE TABLE dim_date (
    date_key          int PRIMARY KEY,            -- yyyymmdd
    full_date         date NOT NULL UNIQUE,
    year              smallint NOT NULL,
    quarter           smallint NOT NULL,
    month             smallint NOT NULL,
    month_name        text NOT NULL,
    day               smallint NOT NULL,
    day_of_week       smallint NOT NULL,          -- 1 = Monday
    is_weekend        boolean NOT NULL,
    is_holiday        boolean NOT NULL,
    holiday_name      text,
    is_lebaran_window boolean NOT NULL,           -- H-7 .. H+7
    is_school_holiday boolean NOT NULL,
    covid_phase       text NOT NULL CHECK (covid_phase IN ('pre', 'lockdown', 'ppkm', 'recovery', 'normal'))
);

CREATE TABLE dim_station (
    station_key  smallint PRIMARY KEY,
    station_code char(3) NOT NULL UNIQUE,
    station_name text NOT NULL,
    city         text NOT NULL
);

CREATE TABLE dim_route (
    route_key  smallint PRIMARY KEY,
    route_code char(2) NOT NULL UNIQUE,
    route_name text NOT NULL,
    origin_city text NOT NULL,
    destination_city text NOT NULL
);

-- Customer segment can change over time, so this dimension is SCD type 2.
CREATE TABLE dim_customer (
    customer_key bigint PRIMARY KEY,
    customer_id  bigint NOT NULL,                 -- oltp.pelanggan.id
    nik          varchar(16) NOT NULL,
    name         text NOT NULL,
    gender       char(1),
    age_group    text,
    city         text,
    segment      text NOT NULL,
    has_fcc      boolean NOT NULL DEFAULT false,
    valid_from   date NOT NULL,
    valid_to     date,
    is_current   boolean NOT NULL DEFAULT true
);
CREATE INDEX ix_dim_customer_id ON dim_customer (customer_id, is_current);

CREATE TABLE dim_company (
    company_key  bigint PRIMARY KEY,
    company_id   bigint NOT NULL,                 -- oltp.perusahaan.id
    code         text NOT NULL,
    name         text NOT NULL,
    company_type text NOT NULL,
    city         text NOT NULL
);

CREATE TABLE dim_promo (
    promo_key   smallint PRIMARY KEY,
    promo_code  text UNIQUE,                      -- NULL row key 0 = "no promo"
    promo_name  text NOT NULL,
    promo_type  text NOT NULL,
    discount_pct numeric(5,2) NOT NULL
);

CREATE TABLE dim_seat_class (
    seat_class_key smallint PRIMARY KEY,
    seat_class     text NOT NULL UNIQUE
);

CREATE TABLE dim_payment_method (
    payment_method_key smallint PRIMARY KEY,
    payment_method     text NOT NULL UNIQUE
);

-- -------------------------------------------------------------------- facts
CREATE TABLE fact_ticket (
    ticket_key          bigint PRIMARY KEY,       -- oltp.ticketsales.id_ticketsales
    order_no            text NOT NULL,
    purchase_date_key   int NOT NULL REFERENCES dim_date(date_key),
    departure_date_key  int NOT NULL REFERENCES dim_date(date_key),
    origin_station_key  smallint NOT NULL REFERENCES dim_station(station_key),
    dest_station_key    smallint NOT NULL REFERENCES dim_station(station_key),
    route_key           smallint NOT NULL REFERENCES dim_route(route_key),
    customer_key        bigint REFERENCES dim_customer(customer_key),
    company_key         bigint REFERENCES dim_company(company_key),
    promo_key           smallint NOT NULL REFERENCES dim_promo(promo_key),
    seat_class_key      smallint NOT NULL REFERENCES dim_seat_class(seat_class_key),
    payment_method_key  smallint NOT NULL REFERENCES dim_payment_method(payment_method_key),
    bak_id              bigint,                   -- degenerate, NULL for individual tickets
    is_group            boolean NOT NULL,
    is_fcc_redeem       boolean NOT NULL,
    lead_days           int NOT NULL,             -- departure - purchase
    base_price          int NOT NULL,
    discount_pct        numeric(5,2) NOT NULL,
    discount_amount     int NOT NULL,
    tax                 int NOT NULL,
    net_price           int NOT NULL
);
CREATE INDEX ix_ft_departure ON fact_ticket (departure_date_key);
CREATE INDEX ix_ft_customer ON fact_ticket (customer_key);
CREATE INDEX ix_ft_route ON fact_ticket (route_key, departure_date_key);

CREATE TABLE fact_bak (
    bak_id                bigint PRIMARY KEY,     -- oltp.bak.id
    company_key           bigint NOT NULL REFERENCES dim_company(company_key),
    document_date_key     int NOT NULL REFERENCES dim_date(date_key),
    first_departure_key   int REFERENCES dim_date(date_key),
    route_key             smallint NOT NULL REFERENCES dim_route(route_key),
    passengers            int NOT NULL,
    total_value           bigint NOT NULL,
    total_discount        bigint NOT NULL,
    paid_amount           bigint NOT NULL,
    payment_gap           bigint NOT NULL,        -- total_value - paid_amount
    days_to_full_payment  int,                    -- NULL while unpaid
    is_late               boolean,
    status                text NOT NULL
);

CREATE TABLE fact_payment (
    payment_key   bigint PRIMARY KEY,             -- oltp.rekening_koran.id
    date_key      int NOT NULL REFERENCES dim_date(date_key),
    company_key   bigint REFERENCES dim_company(company_key),
    bak_id        bigint,                         -- from oltp.pembayaran_bak
    payment_type  text,
    amount        numeric(14,2) NOT NULL,
    days_after_bak int
);
CREATE INDEX ix_fp_bak ON fact_payment (bak_id);

CREATE TABLE fact_fcc_redeem (
    redeem_key      bigint PRIMARY KEY,           -- oltp.fcc_redeem.id
    customer_key    bigint REFERENCES dim_customer(customer_key),
    redeem_date_key int NOT NULL REFERENCES dim_date(date_key),
    departure_date_key int NOT NULL REFERENCES dim_date(date_key),
    route_key       smallint NOT NULL REFERENCES dim_route(route_key),
    card_type       char(1) NOT NULL,
    quota_left      int NOT NULL
);

-- ------------------------------------------------------- ML-ready aggregate
-- Daily demand per route: the target table for demand forecasting.
CREATE MATERIALIZED VIEW mv_daily_route_demand AS
SELECT t.departure_date_key,
       t.route_key,
       count(*)                          AS tickets,
       sum(t.net_price)                  AS revenue,
       avg(t.discount_pct)               AS avg_discount_pct,
       count(*) FILTER (WHERE t.is_group) AS group_tickets,
       count(*) FILTER (WHERE t.is_fcc_redeem) AS fcc_tickets
FROM fact_ticket t
GROUP BY t.departure_date_key, t.route_key;

CREATE UNIQUE INDEX ix_mv_daily_route ON mv_daily_route_demand (departure_date_key, route_key);
