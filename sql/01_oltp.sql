-- OLTP layer for the synthetic HST dataset (PostgreSQL 14+).
-- Table names of the two source apps are kept (bak, ticketsales,
-- maindata -> fcc_kartu, subdata -> fcc_redeem). Dates are real date columns,
-- money is integer rupiah (numeric where a statement balance is needed).

CREATE SCHEMA IF NOT EXISTS oltp;
SET search_path TO oltp;

-- ---------------------------------------------------------------- reference
CREATE TABLE stasiun (
    kode_stasiun char(3) PRIMARY KEY,
    nama         text NOT NULL,
    kota         text NOT NULL
);

CREATE TABLE rute (
    kode_rute  char(2) PRIMARY KEY CHECK (kode_rute IN ('01', '02', '03')),
    nama       text NOT NULL,          -- Jaban, Jaka, Kaban
    kota_asal  text NOT NULL,
    kota_tujuan text NOT NULL
);

CREATE TABLE promo (
    kode_promo  text PRIMARY KEY,
    nama        text NOT NULL,
    jenis       text NOT NULL CHECK (jenis IN ('hut', 'musiman', 'grup', 'loyalitas')),
    diskon_pct  numeric(5,2) NOT NULL CHECK (diskon_pct BETWEEN 0 AND 100),
    tgl_mulai   date NOT NULL,
    tgl_selesai date NOT NULL,
    CHECK (tgl_selesai >= tgl_mulai)
);

-- ------------------------------------------------------------------ parties
CREATE TABLE perusahaan (
    id             bigserial PRIMARY KEY,
    kode           text NOT NULL UNIQUE,
    nama           text NOT NULL,
    jenis          text NOT NULL CHECK (jenis IN ('travel', 'korporat', 'sekolah', 'instansi', 'komunitas')),
    kota           text NOT NULL,
    tgl_bergabung  date NOT NULL
);

CREATE TABLE pelanggan (
    id           bigserial PRIMARY KEY,
    nik          varchar(16) NOT NULL UNIQUE,   -- synthetic, never a real NIK
    nama         text NOT NULL,
    jenis_kelamin char(1) CHECK (jenis_kelamin IN ('L', 'P')),
    tgl_lahir    date,
    email        text,
    no_hp        text,
    kota         text,
    kewarganegaraan text NOT NULL DEFAULT 'ID',
    segmen       text NOT NULL CHECK (segmen IN ('komuter', 'sesekali', 'sekali')),
    created_at   timestamptz NOT NULL DEFAULT now()
);

-- ------------------------------------------------------- frequent card (FCC)
CREATE TABLE fcc_kartu (
    id          bigserial PRIMARY KEY,
    id_fcc      text NOT NULL UNIQUE,
    pelanggan_id bigint NOT NULL REFERENCES pelanggan(id),
    nama        text NOT NULL,
    id_num      text NOT NULL,
    email       text,
    no_hp       text,
    tgl_reg     date NOT NULL,
    tgl_exp     date NOT NULL,
    relasi_fcc  char(2) NOT NULL REFERENCES rute(kode_rute),
    jenis_fcc   char(1) NOT NULL CHECK (jenis_fcc IN ('G', 'S')),   -- G: 10 quota/60d, S: 6/30d
    kuota_awal  int NOT NULL CHECK (kuota_awal > 0),
    kuota       int NOT NULL CHECK (kuota >= 0),
    CHECK (tgl_exp > tgl_reg),
    CHECK (kuota <= kuota_awal)
);

-- ------------------------------------------------------------ group booking
CREATE TABLE bak (
    id               bigserial PRIMARY KEY,
    no_dokumen       text NOT NULL UNIQUE,
    perusahaan_id    bigint NOT NULL REFERENCES perusahaan(id),
    nama_pihak_kedua text NOT NULL,
    periode          char(7) NOT NULL CHECK (periode ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    tanggal_dokumen  date NOT NULL,
    kode_rute        char(2) NOT NULL REFERENCES rute(kode_rute),
    jumlah_penumpang int NOT NULL CHECK (jumlah_penumpang > 0),
    total_nilai      bigint NOT NULL CHECK (total_nilai >= 0),
    total_diskon     bigint NOT NULL DEFAULT 0 CHECK (total_diskon >= 0),
    status           text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'checked')),
    bukti_transfer   boolean NOT NULL DEFAULT false,
    manifest         boolean NOT NULL DEFAULT false,
    keterangan       text,
    file_name        text,
    file_path        text,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_bak_periode ON bak (periode);
CREATE INDEX ix_bak_perusahaan ON bak (perusahaan_id);

CREATE TABLE bak_detail (
    id                    bigserial PRIMARY KEY,
    bak_id        bigint NOT NULL REFERENCES bak(id) ON DELETE CASCADE,
    tanggal_keberangkatan date NOT NULL,
    UNIQUE (bak_id, tanggal_keberangkatan)
);

-- ------------------------------------------------------------------ tickets
CREATE TABLE ticketsales (
    id_ticketsales  bigserial PRIMARY KEY,
    seq_no          int NOT NULL,
    periode         char(7) NOT NULL CHECK (periode ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    passenger_name  text NOT NULL,
    nik_passport_no text NOT NULL,
    pelanggan_id    bigint REFERENCES pelanggan(id),
    bak_id          bigint REFERENCES bak(id),   -- NULL until classified
    nationality     text NOT NULL DEFAULT 'ID',
    order_no        text NOT NULL,
    ticket_no       text NOT NULL UNIQUE,
    operator_name   text NOT NULL,
    purchase_date   date NOT NULL,
    departure_date  date NOT NULL,
    departure_time  time NOT NULL,
    origin          char(3) NOT NULL REFERENCES stasiun(kode_stasiun),
    destination     char(3) NOT NULL REFERENCES stasiun(kode_stasiun),
    arrival_date    date NOT NULL,
    arrival_time    time NOT NULL,
    seat_class      text NOT NULL CHECK (seat_class IN ('ekonomi', 'premium', 'bisnis', 'first')),
    base_price      int NOT NULL CHECK (base_price > 0),
    discount_pct    numeric(5,2) NOT NULL DEFAULT 0 CHECK (discount_pct BETWEEN 0 AND 100),
    discount_amount int NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    tax             int NOT NULL CHECK (tax >= 0),
    after_tax_price int NOT NULL CHECK (after_tax_price > 0),
    kode_promo      text REFERENCES promo(kode_promo),
    payment_method  text NOT NULL,
    trade_no        text,
    plat_trade_no   text,
    CHECK (origin <> destination),
    CHECK (purchase_date <= departure_date),
    CHECK (arrival_date >= departure_date),
    CHECK (after_tax_price = base_price - discount_amount + tax)
);
CREATE INDEX ix_ticket_departure ON ticketsales (departure_date);
CREATE INDEX ix_ticket_periode ON ticketsales (periode);
CREATE INDEX ix_ticket_bak ON ticketsales (bak_id);
CREATE INDEX ix_ticket_nik ON ticketsales (nik_passport_no);
CREATE INDEX ix_ticket_order ON ticketsales (order_no);

CREATE TABLE fcc_redeem (
    id             bigserial PRIMARY KEY,
    id_pesanan     text NOT NULL UNIQUE,                -- equals ticketsales.order_no
    id_fcc         text NOT NULL REFERENCES fcc_kartu(id_fcc),
    id_ticketsales bigint REFERENCES ticketsales(id_ticketsales),
    tgl_departure  date NOT NULL,
    petugas        text NOT NULL,                       -- staff who redeemed
    created_at     timestamptz NOT NULL                 -- redeem time
);
CREATE INDEX ix_redeem_fcc ON fcc_redeem (id_fcc);

-- ----------------------------------------------------------- bank statement
CREATE TABLE rekening_koran (
    id                 bigserial PRIMARY KEY,
    nomor_rekening     text NOT NULL,
    tanggal            date NOT NULL,
    tipe               char(2) NOT NULL CHECK (tipe IN ('CR', 'DB')),
    jumlah             numeric(14,2) NOT NULL CHECK (jumlah > 0),
    saldo              numeric(16,2) NOT NULL,
    nama_pengirim      text,
    rekening_pengirim  text,
    bank_pengirim      text,
    berita             text                              -- free-text transfer message
);
CREATE INDEX ix_rk_tanggal ON rekening_koran (tanggal);

-- ---------------------------------------------------------- ground truth
-- Not visible to the operational app: it is the answer key for matching
-- bank lines to BAK documents and for anomaly detection.
CREATE TABLE pembayaran_bak (
    rekening_koran_id bigint PRIMARY KEY REFERENCES rekening_koran(id),
    bak_id    bigint NOT NULL REFERENCES bak(id),
    jenis             text NOT NULL CHECK (jenis IN ('lunas', 'dp', 'pelunasan', 'cicilan', 'lebih_bayar'))
);
CREATE INDEX ix_pembayaran_bak ON pembayaran_bak (bak_id);

CREATE TABLE label_anomali (
    id         bigserial PRIMARY KEY,
    entitas    text NOT NULL CHECK (entitas IN ('ticket', 'bak', 'rekening_koran', 'redeem')),
    entitas_id bigint NOT NULL,
    jenis      text NOT NULL,   -- e.g. underpayment, duplicate, name_mismatch
    UNIQUE (entitas, entitas_id, jenis)
);
