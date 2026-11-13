-- Fixed reference rows for the oltp schema. Run after 01_oltp.sql.
-- Coordinates are approximate. The operator is fictional, so opened_date and
-- all fares are fictional too. Promos are not seeded here: the generator
-- creates them (see docs/design.md, "Promos").

SET search_path TO oltp;

INSERT INTO station (id, station_code, name, city, province, address, latitude, longitude, opened_date, platform_count, has_ticket_counter) VALUES
    (1, 'HLM', 'Halim',      'East Jakarta',    'DKI Jakarta', 'Halim Perdanakusuma area, East Jakarta',  -6.2660, 106.8910, '2019-12-01', 4, true),
    (2, 'KRW', 'Karawang',   'Karawang',        'West Java',   'Karawang',                                -6.3480, 107.3070, '2019-12-01', 2, true),
    (3, 'PDL', 'Padalarang', 'West Bandung',    'West Java',   'Padalarang, West Bandung',                -6.8420, 107.4660, '2019-12-01', 2, true),
    (4, 'TGL', 'Tegalluar',  'Bandung Regency', 'West Java',   'Tegalluar, Bandung Regency',              -6.9500, 107.7500, '2019-12-01', 4, true);

INSERT INTO route (id, route_code, name, origin_city, destination_city) VALUES
    (1, '01', 'Jakarta - Bandung',   'Jakarta',  'Bandung'),
    (2, '02', 'Jakarta - Karawang',  'Jakarta',  'Karawang'),
    (3, '03', 'Karawang - Bandung',  'Karawang', 'Bandung');

-- Allowed ticket segments, both directions. Padalarang - Tegalluar is not sold.
INSERT INTO route_segment (route_id, origin_station_id, destination_station_id) VALUES
    (1, 1, 3), (1, 3, 1), (1, 1, 4), (1, 4, 1),
    (2, 1, 2), (2, 2, 1),
    (3, 2, 3), (3, 3, 2), (3, 2, 4), (3, 4, 2);

-- Fictional fares. Version 1 runs 2020-2022, version 2 (+10 percent, rounded
-- to Rp 1,000) from 2023.
INSERT INTO fare (id, route_id, seat_class, base_price, valid_from, valid_to) VALUES
    (1,  1, 'economy',  200000, '2020-01-01', '2022-12-31'),
    (2,  1, 'premium',  250000, '2020-01-01', '2022-12-31'),
    (3,  1, 'business', 350000, '2020-01-01', '2022-12-31'),
    (4,  1, 'first',    500000, '2020-01-01', '2022-12-31'),
    (5,  2, 'economy',  100000, '2020-01-01', '2022-12-31'),
    (6,  2, 'premium',  130000, '2020-01-01', '2022-12-31'),
    (7,  2, 'business', 180000, '2020-01-01', '2022-12-31'),
    (8,  2, 'first',    260000, '2020-01-01', '2022-12-31'),
    (9,  3, 'economy',  150000, '2020-01-01', '2022-12-31'),
    (10, 3, 'premium',  190000, '2020-01-01', '2022-12-31'),
    (11, 3, 'business', 270000, '2020-01-01', '2022-12-31'),
    (12, 3, 'first',    390000, '2020-01-01', '2022-12-31');

INSERT INTO fare (id, route_id, seat_class, base_price, valid_from, valid_to)
SELECT id + 12, route_id, seat_class, (round(base_price * 1.1 / 1000) * 1000)::int, DATE '2023-01-01', NULL
FROM fare;

INSERT INTO sales_channel (id, code, name, is_staffed) VALUES
    (1, 'COUNTER', 'Station ticket counter', true),
    (2, 'GROUP',   'Group sales desk',       true),
    (3, 'FCC',     'FCC redemption desk',    true),
    (4, 'AGENT',   'Travel agent portal',    false),
    (5, 'APP',     'Mobile app',             false),
    (6, 'WEB',     'Website',                false);

INSERT INTO covid_phase (phase, start_date, end_date) VALUES
    ('pre',          '2019-12-01', '2020-02-29'),
    ('lockdown',     '2020-03-01', '2020-12-31'),
    ('restrictions', '2021-01-01', '2021-09-30'),
    ('recovery',     '2021-10-01', '2022-12-31'),
    ('normal',       '2023-01-01', '2025-12-31');

-- Fixed-date holidays and the Lebaran day. The full list of movable holidays
-- and collective leave days is added when the generator is written.
INSERT INTO calendar_event (event_date, name, type)
SELECT make_date(y, m, d), n, 'public_holiday'
FROM generate_series(2020, 2025) AS y,
     (VALUES (1, 1, 'New Year'), (5, 1, 'Labour Day'), (6, 1, 'Pancasila Day'),
             (8, 17, 'Independence Day'), (12, 25, 'Christmas Day')) AS h(m, d, n);

INSERT INTO calendar_event (event_date, name, type) VALUES
    ('2020-05-24', 'Lebaran', 'lebaran'),
    ('2021-05-13', 'Lebaran', 'lebaran'),
    ('2022-05-02', 'Lebaran', 'lebaran'),
    ('2023-04-22', 'Lebaran', 'lebaran'),
    ('2024-04-10', 'Lebaran', 'lebaran'),
    ('2025-03-31', 'Lebaran', 'lebaran');

INSERT INTO department (id, name) VALUES
    (1, 'Ticketing'),
    (2, 'Station Operations'),
    (3, 'Customer Service'),
    (4, 'Sales'),
    (5, 'Finance');

INSERT INTO job_position (id, title, grade, department_id) VALUES
    (1,  'Ticketing Agent',               3, 1),
    (2,  'Senior Ticketing Agent',        4, 1),
    (3,  'Ticketing Supervisor',          5, 1),
    (4,  'Ticketing Manager',             7, 1),
    (5,  'Platform Officer',              3, 2),
    (6,  'Station Duty Manager',          6, 2),
    (7,  'Station Master',                7, 2),
    (8,  'Customer Service Officer',      3, 3),
    (9,  'Customer Service Supervisor',   5, 3),
    (10, 'Group Sales Officer',           4, 4),
    (11, 'Sales Manager',                 7, 4),
    (12, 'Verification Officer',          4, 5),
    (13, 'Finance Officer',               4, 5),
    (14, 'Finance Analyst',               5, 5),
    (15, 'Finance Manager',               7, 5);
