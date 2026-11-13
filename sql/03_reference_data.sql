-- Fixed reference rows for the oltp schema. Run after 01_oltp.sql.
-- Coordinates are approximate. The operator is fictional, so opened_date is
-- also fictional (the whole network is assumed open from 2019-12-01).

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

INSERT INTO sales_channel (id, code, name, is_staffed) VALUES
    (1, 'COUNTER', 'Station ticket counter', true),
    (2, 'GROUP',   'Group sales desk',       true),
    (3, 'FCC',     'FCC redemption desk',    true),
    (4, 'AGENT',   'Travel agent portal',    false),
    (5, 'APP',     'Mobile app',             false),
    (6, 'WEB',     'Website',                false);

INSERT INTO department (id, name) VALUES
    (1, 'Ticketing'),
    (2, 'Station Operations'),
    (3, 'Customer Service'),
    (4, 'Sales'),
    (5, 'Finance');

INSERT INTO position (id, title, grade, department_id) VALUES
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
