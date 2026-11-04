# Sinkronisasi Excel → MySQL

Script ini membaca file Excel di shared network drive secara berkala, mendeteksi
baris baru berdasarkan kolom ID unik, dan memasukkannya ke tabel MySQL.

## 1. Persiapan Excel

- Pastikan ada kolom **ID unik** di setiap baris (misal `ID`: 1, 2, 3, ... atau kode unik lain).
  Ini penting agar script bisa tahu baris mana yang belum pernah disinkron,
  meskipun ada baris yang disisipkan di tengah.
- Header kolom ada di baris tertentu (default baris 1) dan tidak berubah posisi/urutan.
- Contoh struktur:

  | ID | nama    | kategori | jumlah | tanggal    |
  |----|---------|----------|--------|------------|
  | 1  | Budi    | A        | 100000 | 2026-07-01 |
  | 2  | Siti    | B        | 250000 | 2026-07-05 |

## 2. Persiapan MySQL

1. Buat tabel dengan struktur yang **cocok** dengan kolom Excel. Lihat contoh di
   `setup_table.example.sql` — ubah nama tabel/kolom sesuai kebutuhan Anda, lalu jalankan
   di MySQL (misal lewat phpMyAdmin, MySQL Workbench, atau `mysql` CLI).
2. Sebaiknya buat user MySQL khusus dengan hak akses terbatas (`SELECT` + `INSERT` saja),
   jangan pakai user `root` untuk script otomatis ini.

## 3. Instalasi

```bash
pip install -r requirements.txt
```

## 4. Konfigurasi

1. Salin `config.example.json` menjadi `config.json`.
2. Edit `config.json`:
   - `excel.file_path` → path lengkap ke file Excel di network drive
     (contoh Windows: `\\\\NAMA-SERVER\\folder\\data.xlsx`)
   - `excel.sheet_name` → nama sheet yang berisi data
   - `excel.header_row` → nomor baris header (biasanya 1)
   - `excel.id_column` → nama kolom ID unik di Excel (harus sama persis, case-sensitive)
   - `mysql.*` → kredensial database Anda
   - `table.name` → nama tabel MySQL tujuan
   - `table.id_column` → nama kolom ID di tabel MySQL

   **Penting:** nama kolom lain di Excel (misal `nama`, `kategori`, `jumlah`) harus
   PERSIS SAMA dengan nama kolom di tabel MySQL, karena script mengambil nama kolom
   otomatis dari header Excel.

## 5. Coba jalankan manual dulu

```bash
python sync_excel_to_mysql.py
```

Cek `sync_log.txt` untuk melihat hasilnya. Pastikan tidak ada error sebelum
dijadwalkan otomatis.

## Sinkronisasi tabel `field_audit`

Schema `field_audit` memakai `id` auto-increment, jadi gunakan kunci sumber
gabungan `season` dan `field_number` untuk mencegah baris yang sama dimasukkan
lagi. Contoh konfigurasi ada di `config.field_audit.example.json`; sesuaikan
lokasi Excel dan koneksi MySQL, lalu jalankan dengan:

```bash
python sync_excel_to_mysql.py --config config.field_audit.example.json
```

Dengan `auto_map_columns` aktif, header Excel dinormalisasi saat dicocokkan ke
nama kolom tabel, sehingga `Field Number` cocok dengan `field_number` dan
`Gen 1 Audit Date` cocok dengan `gen1_audit_date`. Kolom `id`, `created_at`, dan
`updated_at` dibiarkan dikelola MySQL. Untuk header yang tidak cocok otomatis,
isi `table.field_map` dengan pemetaan nama kolom tabel ke nama header Excel.
`table.update_existing: true` membuat sinkronisasi memperbarui baris dengan
kunci yang sudah ada; baris berkunci baru tetap di-insert. Nilai kolom non-kunci
diambil dari Excel, termasuk sel kosong yang akan mengosongkan nilai MySQL.

## API baca `field_audit`

Install dependency lalu jalankan API dengan konfigurasi tabel audit:

```bash
pip install -r requirements.txt
python field_audit_api.py --config config.field_audit.example.json
```

Secara default API hanya bind ke komputer lokal. Dokumentasi interaktif tersedia
di `http://127.0.0.1:8000/docs`.
Panduan lengkap endpoint, request, response, dan akses jaringan ada di
`field_audit_api.md`.

- `GET /api/field-audit?limit=100&offset=0` mengambil data berhalaman.
- Filter opsional: `season`, `field_number`, dan `farmer_name`.
- `GET /api/field-audit/vegetative` (atau alias `/api/field-audit/fase-vegetative`) mengambil data 50 kolom khusus fase vegetatif.
- `GET /api/field-audit/vegetative/{id_atau_field_number}` mengambil satu data fase vegetatif.
- `GET /api/field-audit/{id}` mengambil satu baris berdasarkan ID (semua kolom).
- `POST /api/field-audit` membaca Excel dari konfigurasi dan menyinkronkan baris baru ke MySQL (tanpa body JSON).
- `GET /health` mengecek bahwa API aktif.

Untuk akses dari komputer lain, set environment variable `FIELD_AUDIT_API_KEY`
dan jalankan dengan `--host 0.0.0.0`. Sertakan nilai key tersebut dalam header
`X-API-Key` pada setiap request, dan batasi akses jaringan lewat firewall.
Jangan publikasikan port API langsung ke internet.

## 6. Jadwalkan otomatis

### Windows (Task Scheduler)
1. Edit `run_sync.bat`, sesuaikan path folder project dan path `python.exe`.
2. Buka **Task Scheduler** → Create Task.
3. Trigger: **Repeat every 5 minutes**, duration indefinitely.
4. Action: jalankan `run_sync.bat`.
5. Centang "Run whether user is logged on or not" agar tetap jalan meski tidak login.

### Linux (cron)
```bash
crontab -e
```
Tambahkan baris (jalan setiap 5 menit):
```
*/5 * * * * cd /path/ke/excel-mysql-sync && /usr/bin/python3 sync_excel_to_mysql.py
```

## 7. Catatan penting

- **Jangan ubah urutan/nama kolom** di Excel setelah sinkron berjalan, karena
  script memetakan kolom berdasarkan nama header.
- Kalau file sedang dibuka orang lain saat script jalan, script akan **retry otomatis**
  3 kali dengan jeda 5 detik. Kalau masih gagal, akan tercatat di log dan dicoba lagi
  di eksekusi berikutnya (tidak ada data yang hilang, karena Excel-nya tetap ada).
- Script tidak menghapus data. Secara default hanya menambahkan baris baru, tetapi
  `table.update_existing: true` akan memperbarui kolom non-kunci dari Excel pada
  record yang sudah ada. Sel kosong dari Excel juga akan menimpa nilai kolom menjadi
  `NULL`; pastikan workbook memang menjadi sumber data untuk kolom-kolom tersebut.
- Update dan insert menggunakan `table.unique_columns` untuk menemukan record yang
  cocok. Buat unique index MySQL pada kolom-kolom kunci tersebut agar aman dari
  duplikasi jika API dan Task Scheduler berjalan bersamaan.
- Jalankan script dari komputer/server yang punya akses baca ke network drive tersebut.
