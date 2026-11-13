-- DWH layer: star schema built from the oltp schema (PostgreSQL 14+).
-- Dimensions use surrogate "<dim>_key" columns; facts keep the oltp id as a
-- degenerate key. Column names match the oltp layer where the concept is the same.

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
    covid_phase       text NOT NULL CHECK (covid_phase IN ('pre', 'lockdown', 'restrictions', 'recovery', 'normal'))
);

CREATE TABLE dim_station (
    station_key    smallint PRIMARY KEY,
    station_id     smallint NOT NULL,             -- oltp.station.id
    station_code   char(3) NOT NULL UNIQUE,
    name           text NOT NULL,
    city           text NOT NULL,
    province       text NOT NULL,
    latitude       numeric(9,6),
    longitude      numeric(9,6),
    platform_count smallint NOT NULL
);

CREATE TABLE dim_route (
    route_key        smallint PRIMARY KEY,
    route_code       char(2) NOT NULL UNIQUE,
    name             text NOT NULL,
    origin_city      text NOT NULL,
    destination_city text NOT NULL
);

-- Segment can change over time, so this dimension is SCD type 2.
CREATE TABLE dim_customer (
    customer_key bigint PRIMARY KEY,
    customer_id  bigint NOT NULL,                 -- oltp.customer.id
    id_number    varchar(20) NOT NULL,
    name         text NOT NULL,
    gender       char(1),
    age_group    text,
    city         text,
    segment      text NOT NULL,
    has_fcc_card boolean NOT NULL DEFAULT false,
    valid_from   date NOT NULL,
    valid_to     date,
    is_current   boolean NOT NULL DEFAULT true
);
CREATE INDEX ix_dim_customer_id ON dim_customer (customer_id, is_current);

CREATE TABLE dim_company (
    company_key  bigint PRIMARY KEY,
    company_id   bigint NOT NULL,                 -- oltp.company.id
    company_code text NOT NULL,
    name         text NOT NULL,
    type         text NOT NULL,
    city         text NOT NULL
);

-- Position and department are flattened in. SCD type 2: a promotion or a move
-- to another station creates a new row.
CREATE TABLE dim_employee (
    employee_key       bigint PRIMARY KEY,
    employee_id        bigint NOT NULL,           -- oltp.employee.id
    nip                varchar(18) NOT NULL,
    full_name          text NOT NULL,
    gender             char(1),
    position_title     text NOT NULL,
    grade              smallint NOT NULL,
    department         text NOT NULL,
    employment_status  text NOT NULL,
    home_station_key   smallint REFERENCES dim_station(station_key),
    hire_date          date NOT NULL,
    end_date           date,
    valid_from         date NOT NULL,
    valid_to           date,
    is_current         boolean NOT NULL DEFAULT true
);
CREATE INDEX ix_dim_employee_id ON dim_employee (employee_id, is_current);

CREATE TABLE dim_promo (
    promo_key    smallint PRIMARY KEY,            -- 0 = no promo
    promo_code   text UNIQUE,
    name         text NOT NULL,
    type         text NOT NULL,
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

CREATE TABLE dim_sales_channel (
    sales_channel_key smallint PRIMARY KEY,
    code              text NOT NULL UNIQUE,
    name              text NOT NULL,
    is_staffed        boolean NOT NULL
);

-- -------------------------------------------------------------------- facts
CREATE TABLE fact_ticket (
    ticket_sales_id        bigint PRIMARY KEY,    -- oltp.ticket_sales.id
    order_id               text NOT NULL,
    purchase_date_key      int NOT NULL REFERENCES dim_date(date_key),
    departure_date_key     int NOT NULL REFERENCES dim_date(date_key),
    origin_station_key     smallint NOT NULL REFERENCES dim_station(station_key),
    destination_station_key smallint NOT NULL REFERENCES dim_station(station_key),
    issue_station_key      smallint REFERENCES dim_station(station_key),
    route_key              smallint NOT NULL REFERENCES dim_route(route_key),
    customer_key           bigint REFERENCES dim_customer(customer_key),
    company_key            bigint REFERENCES dim_company(company_key),
    employee_key           bigint REFERENCES dim_employee(employee_key),   -- issuing employee
    promo_key              smallint NOT NULL REFERENCES dim_promo(promo_key),
    seat_class_key         smallint NOT NULL REFERENCES dim_seat_class(seat_class_key),
    payment_method_key     smallint NOT NULL REFERENCES dim_payment_method(payment_method_key),
    sales_channel_key      smallint NOT NULL REFERENCES dim_sales_channel(sales_channel_key),
    group_booking_id       bigint,                -- degenerate, NULL for individual tickets
    is_group               boolean NOT NULL,
    is_fcc_redemption      boolean NOT NULL,
    lead_days              int NOT NULL,          -- departure - purchase
    base_price             int NOT NULL,
    discount_pct           numeric(5,2) NOT NULL,
    discount_amount        int NOT NULL,
    tax_amount             int NOT NULL,
    total_price            int NOT NULL
);
CREATE INDEX ix_ft_departure ON fact_ticket (departure_date_key);
CREATE INDEX ix_ft_customer ON fact_ticket (customer_key);
CREATE INDEX ix_ft_employee ON fact_ticket (employee_key);
CREATE INDEX ix_ft_route ON fact_ticket (route_key, departure_date_key);

CREATE TABLE fact_group_booking (
    group_booking_id      bigint PRIMARY KEY,     -- oltp.group_booking.id
    company_key           bigint NOT NULL REFERENCES dim_company(company_key),
    document_date_key     int NOT NULL REFERENCES dim_date(date_key),
    first_departure_key   int REFERENCES dim_date(date_key),
    route_key             smallint NOT NULL REFERENCES dim_route(route_key),
    created_by_employee_key  bigint REFERENCES dim_employee(employee_key),
    verified_by_employee_key bigint REFERENCES dim_employee(employee_key),
    passenger_count       int NOT NULL,
    total_amount          bigint NOT NULL,
    discount_amount       bigint NOT NULL,
    paid_amount           bigint NOT NULL,
    payment_gap           bigint NOT NULL,        -- total_amount - paid_amount
    days_to_full_payment  int,                    -- NULL while unpaid
    is_late               boolean,
    status                text NOT NULL
);

CREATE TABLE fact_payment (
    bank_statement_id bigint PRIMARY KEY,         -- oltp.bank_statement.id
    date_key          int NOT NULL REFERENCES dim_date(date_key),
    company_key       bigint REFERENCES dim_company(company_key),
    group_booking_id  bigint,                     -- from oltp.group_booking_payment
    payment_type      text,
    amount            numeric(14,2) NOT NULL,
    days_after_booking int
);
CREATE INDEX ix_fp_booking ON fact_payment (group_booking_id);

CREATE TABLE fact_fcc_redemption (
    fcc_redemption_id  bigint PRIMARY KEY,        -- oltp.fcc_redemption.id
    customer_key       bigint REFERENCES dim_customer(customer_key),
    employee_key       bigint REFERENCES dim_employee(employee_key),
    redeemed_date_key  int NOT NULL REFERENCES dim_date(date_key),
    departure_date_key int NOT NULL REFERENCES dim_date(date_key),
    route_key          smallint NOT NULL REFERENCES dim_route(route_key),
    card_type          char(1) NOT NULL,
    remaining_quota    int NOT NULL
);

-- ------------------------------------------------------- ML-ready aggregate
-- Daily demand per route: the target table for demand forecasting.
CREATE MATERIALIZED VIEW mv_daily_route_demand AS
SELECT t.departure_date_key,
       t.route_key,
       count(*)                                    AS tickets,
       sum(t.total_price)                          AS revenue,
       avg(t.discount_pct)                         AS avg_discount_pct,
       count(*) FILTER (WHERE t.is_group)          AS group_tickets,
       count(*) FILTER (WHERE t.is_fcc_redemption) AS fcc_tickets
FROM fact_ticket t
GROUP BY t.departure_date_key, t.route_key;

CREATE UNIQUE INDEX ix_mv_daily_route ON mv_daily_route_demand (departure_date_key, route_key);

-- Tickets issued per employee per month: workload and performance analysis.
CREATE MATERIALIZED VIEW mv_employee_monthly_sales AS
SELECT t.employee_key,
       d.year,
       d.month,
       count(*)           AS tickets_issued,
       sum(t.total_price) AS revenue
FROM fact_ticket t
JOIN dim_date d ON d.date_key = t.purchase_date_key
WHERE t.employee_key IS NOT NULL
GROUP BY t.employee_key, d.year, d.month;

CREATE UNIQUE INDEX ix_mv_employee_monthly ON mv_employee_monthly_sales (employee_key, year, month);
