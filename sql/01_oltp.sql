-- OLTP layer for the synthetic HST dataset (PostgreSQL 14+).
--
-- Naming conventions
--   * every table has a surrogate primary key named "id"
--   * foreign keys are "<entity>_id"; people-role foreign keys are
--     "<verb>_by_employee_id"
--   * the same concept has the same column name in every table
--     (order_id, id_number, period, departure_date, ...)
--   * natural keys end in _code or _no
--   * money is integer rupiah, except bank amounts (numeric)
--   * the answer keys (labels for ML and checks) live in the separate schema
--     oltp_truth, see 02_oltp_truth.sql

CREATE SCHEMA IF NOT EXISTS oltp;
SET search_path TO oltp;

-- ---------------------------------------------------------------- reference
CREATE TABLE station (
    id                 smallint PRIMARY KEY,
    station_code       char(3) NOT NULL UNIQUE,
    name               text NOT NULL,
    city               text NOT NULL,
    province           text NOT NULL,
    address            text,
    latitude           numeric(9,6),
    longitude          numeric(9,6),
    opened_date        date NOT NULL,
    platform_count     smallint NOT NULL CHECK (platform_count > 0),
    has_ticket_counter boolean NOT NULL
);

CREATE TABLE route (
    id               smallint PRIMARY KEY,
    route_code       char(2) NOT NULL UNIQUE CHECK (route_code IN ('01', '02', '03')),
    name             text NOT NULL,
    origin_city      text NOT NULL,
    destination_city text NOT NULL
);

-- Station pairs that may be sold as a ticket, per route (both directions).
CREATE TABLE route_segment (
    route_id               smallint NOT NULL REFERENCES route(id),
    origin_station_id      smallint NOT NULL REFERENCES station(id),
    destination_station_id smallint NOT NULL REFERENCES station(id),
    PRIMARY KEY (route_id, origin_station_id, destination_station_id),
    CHECK (origin_station_id <> destination_station_id)
);

CREATE TABLE fare (
    id         smallint PRIMARY KEY,
    route_id   smallint NOT NULL REFERENCES route(id),
    seat_class text NOT NULL CHECK (seat_class IN ('economy', 'premium', 'business', 'first')),
    base_price int NOT NULL CHECK (base_price > 0),
    valid_from date NOT NULL,
    valid_to   date,                                  -- NULL = still valid
    UNIQUE (route_id, seat_class, valid_from),
    UNIQUE (id, route_id, seat_class),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

-- Campaigns. Example: "HST February Deals", 20 percent off all group trips,
-- minimum 20 passengers.
CREATE TABLE promo (
    id           smallint PRIMARY KEY,
    promo_code   text NOT NULL UNIQUE,
    name         text NOT NULL,
    type         text NOT NULL CHECK (type IN ('monthly_deal', 'anniversary', 'seasonal', 'group', 'loyalty')),
    applies_to   text NOT NULL CHECK (applies_to IN ('all', 'group', 'individual', 'fcc')),
    min_pax      smallint CHECK (min_pax IS NULL OR min_pax >= 1),   -- NULL = no minimum
    route_id     smallint REFERENCES route(id),                      -- NULL = all routes
    discount_pct numeric(5,2) NOT NULL CHECK (discount_pct BETWEEN 0 AND 100),
    start_date   date NOT NULL,
    end_date     date NOT NULL,
    CHECK (end_date >= start_date),
    CHECK (applies_to <> 'group' OR min_pax >= 20)
);

CREATE TABLE sales_channel (
    id         smallint PRIMARY KEY,
    code       text NOT NULL UNIQUE,
    name       text NOT NULL,
    is_staffed boolean NOT NULL      -- false: self service, no employee issues the ticket
);

CREATE TABLE covid_phase (
    phase      text PRIMARY KEY CHECK (phase IN ('pre', 'lockdown', 'restrictions', 'recovery', 'normal')),
    start_date date NOT NULL,
    end_date   date NOT NULL,
    CHECK (end_date >= start_date)
);

CREATE TABLE calendar_event (
    id         serial PRIMARY KEY,
    event_date date NOT NULL,
    name       text NOT NULL,
    type       text NOT NULL CHECK (type IN ('public_holiday', 'collective_leave', 'lebaran', 'school_holiday')),
    UNIQUE (event_date, name)
);

-- ---------------------------------------------------------------- employees
CREATE TABLE department (
    id   smallint PRIMARY KEY,
    name text NOT NULL UNIQUE
);

CREATE TABLE job_position (
    id            smallint PRIMARY KEY,
    title         text NOT NULL UNIQUE,
    grade         smallint NOT NULL CHECK (grade BETWEEN 1 AND 10),
    department_id smallint NOT NULL REFERENCES department(id)
);

-- Current state. The latest employee_history row must match this row.
CREATE TABLE employee (
    id                 bigserial PRIMARY KEY,
    nip                varchar(18) NOT NULL UNIQUE,   -- employee number (synthetic)
    full_name          text NOT NULL,
    gender             char(1) CHECK (gender IN ('M', 'F')),
    birth_date         date NOT NULL,
    email              text,
    phone              text,
    hire_date          date NOT NULL,
    end_date           date,                           -- NULL while employed
    employment_status  text NOT NULL CHECK (employment_status IN ('permanent', 'contract')),
    job_position_id    smallint NOT NULL REFERENCES job_position(id),
    home_station_id    smallint REFERENCES station(id),
    supervisor_id      bigint REFERENCES employee(id),
    CHECK (end_date IS NULL OR end_date > hire_date)
);
CREATE INDEX ix_employee_station ON employee (home_station_id);
CREATE INDEX ix_employee_position ON employee (job_position_id);

-- Promotions and transfers. One row per period of holding a position at a station.
CREATE TABLE employee_history (
    id              bigserial PRIMARY KEY,
    employee_id     bigint NOT NULL REFERENCES employee(id),
    job_position_id smallint NOT NULL REFERENCES job_position(id),
    home_station_id smallint REFERENCES station(id),
    valid_from      date NOT NULL,
    valid_to        date,                              -- NULL = current
    UNIQUE (employee_id, valid_from),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

-- ------------------------------------------------------------------ parties
CREATE TABLE company (
    id           bigserial PRIMARY KEY,
    company_code text NOT NULL UNIQUE,
    name         text NOT NULL,
    type         text NOT NULL CHECK (type IN ('travel_agency', 'corporate', 'school', 'government', 'community')),
    city         text NOT NULL,
    joined_date  date NOT NULL
);

CREATE TABLE customer (
    id          bigserial PRIMARY KEY,
    id_number   varchar(20) NOT NULL UNIQUE,   -- synthetic; Indonesian IDs start with 99 so they never match a real NIK
    name        text NOT NULL,
    gender      char(1) CHECK (gender IN ('M', 'F')),
    birth_date  date,
    email       text,
    phone       text,
    city        text,
    nationality text NOT NULL DEFAULT 'ID',
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (nationality <> 'ID' OR id_number ~ '^99[0-9]{14}$')
);

-- ---------------------------------------------- frequent customer card (FCC)
-- Owner name, ID number and contact live on customer (single source).
CREATE TABLE fcc_card (
    id                        bigserial PRIMARY KEY,
    card_no                   text NOT NULL UNIQUE,
    customer_id               bigint NOT NULL REFERENCES customer(id),
    registration_date         date NOT NULL,
    expiry_date               date NOT NULL,
    route_id                  smallint NOT NULL REFERENCES route(id),
    card_type                 char(1) NOT NULL CHECK (card_type IN ('G', 'S')),  -- G: 10 trips/60 days, S: 6 trips/30 days
    initial_quota             int NOT NULL CHECK (initial_quota > 0),
    remaining_quota           int NOT NULL CHECK (remaining_quota >= 0),
    registered_by_employee_id bigint REFERENCES employee(id),
    CHECK (expiry_date > registration_date),
    CHECK (remaining_quota <= initial_quota)
);
CREATE INDEX ix_fcc_card_customer ON fcc_card (customer_id);

-- ------------------------------------------------------------ group booking
-- A group has at least 20 passengers. period = month of the first departure.
CREATE TABLE group_booking (
    id                      bigserial PRIMARY KEY,
    booking_no              text NOT NULL UNIQUE,
    company_id              bigint NOT NULL REFERENCES company(id),
    counterparty_name       text NOT NULL,            -- name as written on the document (may differ from company.name)
    period                  char(7) NOT NULL CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    document_date           date NOT NULL,
    payment_due_date        date NOT NULL,
    route_id                smallint NOT NULL REFERENCES route(id),
    passenger_count         int NOT NULL CHECK (passenger_count >= 20),
    total_amount            bigint NOT NULL CHECK (total_amount >= 0),
    discount_amount         bigint NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    promo_id                smallint REFERENCES promo(id),
    status                  text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'checked')),
    has_transfer_proof      boolean NOT NULL DEFAULT false,
    has_manifest            boolean NOT NULL DEFAULT false,
    notes                   text,
    file_name               text,
    file_path               text,
    created_by_employee_id  bigint REFERENCES employee(id),
    verified_by_employee_id bigint REFERENCES employee(id),
    created_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, route_id),
    CHECK (payment_due_date >= document_date)
);
CREATE INDEX ix_group_booking_period ON group_booking (period);
CREATE INDEX ix_group_booking_company ON group_booking (company_id);

CREATE TABLE group_booking_detail (
    id               bigserial PRIMARY KEY,
    group_booking_id bigint NOT NULL REFERENCES group_booking(id) ON DELETE CASCADE,
    departure_date   date NOT NULL,
    UNIQUE (group_booking_id, departure_date)
);

-- ------------------------------------------------------------------- trips
CREATE TABLE trip (
    id            bigserial PRIMARY KEY,
    trip_no       text NOT NULL,
    service_date  date NOT NULL,
    direction     text NOT NULL CHECK (direction IN ('to_bandung', 'to_jakarta')),
    departure_time time NOT NULL,
    arrival_time  time NOT NULL,
    seat_capacity int NOT NULL CHECK (seat_capacity > 0),
    UNIQUE (trip_no, service_date)
);
CREATE INDEX ix_trip_date ON trip (service_date);

-- ------------------------------------------------------------------ tickets
CREATE TABLE ticket_sales (
    id                     bigserial PRIMARY KEY,
    seq_no                 int NOT NULL,
    period                 char(7) NOT NULL CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),   -- month of departure_date
    passenger_name         text NOT NULL,
    passenger_id_number    varchar(20) NOT NULL,
    customer_id            bigint REFERENCES customer(id),
    group_booking_id       bigint,                    -- NULL for individual tickets and for pending bookings
    nationality            text NOT NULL DEFAULT 'ID',
    order_id               text NOT NULL,
    ticket_no              text NOT NULL UNIQUE,
    status                 text NOT NULL DEFAULT 'issued' CHECK (status IN ('issued', 'used', 'cancelled', 'refunded')),
    trip_id                bigint NOT NULL REFERENCES trip(id),
    route_id               smallint NOT NULL REFERENCES route(id),
    purchase_date          date NOT NULL,
    departure_date         date NOT NULL,
    departure_time         time NOT NULL,
    origin_station_id      smallint NOT NULL REFERENCES station(id),
    destination_station_id smallint NOT NULL REFERENCES station(id),
    arrival_date           date NOT NULL,
    arrival_time           time NOT NULL,
    seat_class             text NOT NULL CHECK (seat_class IN ('economy', 'premium', 'business', 'first')),
    fare_id                smallint NOT NULL,
    base_price             int NOT NULL CHECK (base_price > 0),     -- fare price, plus a peak uplift in crowded windows
    discount_pct           numeric(5,2) NOT NULL DEFAULT 0 CHECK (discount_pct BETWEEN 0 AND 100),
    discount_amount        int NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    service_fee_amount     int NOT NULL DEFAULT 0 CHECK (service_fee_amount >= 0),   -- admin fee by channel, after discount
    total_price            int NOT NULL CHECK (total_price > 0),
    promo_id               smallint REFERENCES promo(id),
    payment_method         text NOT NULL,
    payment_ref            text,
    platform_payment_ref   text,
    sales_channel_id       smallint NOT NULL REFERENCES sales_channel(id),
    issued_by_employee_id  bigint REFERENCES employee(id),        -- NULL for self-service channels
    issue_station_id       smallint REFERENCES station(id),       -- NULL for online channels
    FOREIGN KEY (route_id, origin_station_id, destination_station_id)
        REFERENCES route_segment (route_id, origin_station_id, destination_station_id),
    FOREIGN KEY (fare_id, route_id, seat_class) REFERENCES fare (id, route_id, seat_class),
    FOREIGN KEY (group_booking_id, route_id) REFERENCES group_booking (id, route_id),
    CHECK (purchase_date <= departure_date),
    CHECK (arrival_date >= departure_date),
    CHECK (period = to_char(departure_date, 'YYYY-MM')),
    CHECK (total_price = base_price - discount_amount + service_fee_amount)
);
CREATE INDEX ix_ticket_departure ON ticket_sales (departure_date);
CREATE INDEX ix_ticket_period ON ticket_sales (period);
CREATE INDEX ix_ticket_group_booking ON ticket_sales (group_booking_id);
CREATE INDEX ix_ticket_id_number ON ticket_sales (passenger_id_number);
CREATE INDEX ix_ticket_order ON ticket_sales (order_id);
CREATE INDEX ix_ticket_employee ON ticket_sales (issued_by_employee_id);
CREATE INDEX ix_ticket_trip ON ticket_sales (trip_id);

CREATE TABLE refund (
    id                      bigserial PRIMARY KEY,
    ticket_sales_id         bigint NOT NULL UNIQUE REFERENCES ticket_sales(id),
    refund_date             date NOT NULL,
    refund_amount           int NOT NULL CHECK (refund_amount >= 0),
    refund_fee              int NOT NULL DEFAULT 0 CHECK (refund_fee >= 0),
    reason                  text NOT NULL CHECK (reason IN ('schedule_change', 'customer_request', 'illness', 'duplicate_booking', 'other')),
    processed_by_employee_id bigint REFERENCES employee(id)
);

CREATE TABLE fcc_redemption (
    id                      bigserial PRIMARY KEY,
    order_id                text NOT NULL UNIQUE,               -- equals ticket_sales.order_id
    card_id                 bigint NOT NULL REFERENCES fcc_card(id),
    ticket_sales_id         bigint REFERENCES ticket_sales(id),
    departure_date          date NOT NULL,
    redeemed_by_employee_id bigint REFERENCES employee(id),
    redeemed_at             timestamptz NOT NULL
);
CREATE INDEX ix_fcc_redemption_card ON fcc_redemption (card_id);

-- ----------------------------------------------------------- bank statement
-- Besides group payments the statement has unrelated lines (gateway
-- settlement, bank fee, interest, refund payout), so matching is not trivial.
CREATE TABLE bank_statement (
    id                bigserial PRIMARY KEY,
    account_no        text NOT NULL,
    transaction_date  date NOT NULL,
    transaction_code  text NOT NULL CHECK (transaction_code IN ('TRF', 'SETTLE', 'FEE', 'INT', 'REFUND', 'OTHER')),
    direction         text NOT NULL CHECK (direction IN ('credit', 'debit')),
    amount            numeric(14,2) NOT NULL CHECK (amount > 0),
    balance           numeric(16,2) NOT NULL,          -- running balance per account, in date and id order
    sender_name       text,
    sender_account_no text,
    sender_bank       text,
    message           text                              -- free-text transfer message
);
CREATE INDEX ix_bank_statement_date ON bank_statement (transaction_date);
