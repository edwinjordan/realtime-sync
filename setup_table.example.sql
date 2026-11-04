-- Contoh struktur tabel MySQL.
-- SESUAIKAN nama kolom & tipe data dengan kolom yang ada di file Excel Anda.
-- Kolom pertama (id) HARUS cocok dengan isi kolom ID di Excel, dan harus UNIQUE.

CREATE TABLE IF NOT EXISTS data_excel (
    id           VARCHAR(50) PRIMARY KEY,   -- harus sama dengan kolom "ID" di Excel
    nama         VARCHAR(255),
    kategori     VARCHAR(100),
    jumlah       DECIMAL(15,2),
    tanggal      DATE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Buat user MySQL khusus untuk sinkronisasi, dengan hak akses terbatas
-- (hanya SELECT dan INSERT ke tabel ini, demi keamanan)
CREATE USER IF NOT EXISTS 'sync_user'@'%' IDENTIFIED BY 'GANTI_PASSWORD_INI';
GRANT SELECT, INSERT ON nama_database.data_excel TO 'sync_user'@'%';
FLUSH PRIVILEGES;
