# Field Audit API

API HTTP untuk membaca dan menyimpan data pada tabel MySQL `field_audit` yang digunakan oleh proses sinkronisasi Excel.

## Persyaratan

- Python 3.10 atau lebih baru.
- MySQL dapat diakses dari komputer yang menjalankan API.
- File konfigurasi JSON dengan bagian `mysql` dan `table.name`, misalnya `config.field_audit.example.json`.

Install dependency dari folder proyek:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Menjalankan API

Jalankan untuk akses dari komputer yang sama:

```powershell
.\.venv\Scripts\python.exe field_audit_api.py --config config.field_audit.example.json
```

Default alamat API adalah `http://127.0.0.1:8000`. Buka dokumentasi interaktif FastAPI di:

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

Opsi command line:

| Opsi | Default | Keterangan |
|---|---|---|
| `--config` | `config.field_audit.example.json` di folder script | File konfigurasi MySQL dan tabel |
| `--host` | `127.0.0.1` | Alamat network interface untuk bind server |
| `--port` | `8000` | Port HTTP API |

Host dan port juga dapat diset dengan environment variable `FIELD_AUDIT_API_HOST` dan `FIELD_AUDIT_API_PORT`. Argumen command line akan mengesampingkan nilai environment.

Pada Windows, API menggunakan Selector event loop. Jika server berjalan dengan
Proactor, API hanya mengabaikan `ConnectionResetError` WinError 10054 dari
callback penutupan koneksi Proactor yang sudah dikenal; exception lainnya
tetap dilaporkan. Hal ini tidak mengubah response endpoint. Selector tidak
mendukung asyncio subprocess dan memiliki batas jumlah socket yang lebih
rendah.

## Endpoint

### Cek kesehatan

```http
GET /health
```

Respons `200 OK`:

```json
{
  "status": "ok"
}
```

Endpoint ini memeriksa bahwa proses API aktif. Koneksi MySQL diuji saat endpoint data dipanggil.

### Daftar data

```http
GET /api/field-audit
```

Parameter query:

| Parameter | Tipe | Default | Batas / perilaku |
|---|---|---:|---|
| `limit` | integer | `100` | 1 sampai 500 |
| `offset` | integer | `0` | 0 atau lebih |
| `season` | string | tidak ada | Filter sama persis pada kolom `season` |
| `field_number` | string | tidak ada | Filter sama persis pada kolom `field_number` |
| `farmer_name` | string | tidak ada | Filter sama persis pada kolom `farmer_name` |
| `order_by` | string | `id` | Kolom pengurutan; hanya huruf, angka, dan underscore |
| `order` | string | `desc` | Arah pengurutan: `asc` atau `desc` |

Filter dapat digabung; semua filter yang diberikan harus cocok. Pengurutan
default menggunakan `id` terbaru lebih dulu. Parameter `order_by` dan `order`
juga tersedia pada semua endpoint daftar data fase.
Semua endpoint data mengecualikan baris dengan `flagging_final = 'PLD'`,
termasuk endpoint untuk mengambil satu baris.

Contoh URL:

```text
http://127.0.0.1:8000/api/field-audit?limit=50&offset=0&season=2026&field_number=F-001&order_by=season&order=asc
```

Contoh request PowerShell:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/field-audit?limit=50&offset=0&season=2026'
```

Contoh request cURL:

```bash
curl "http://127.0.0.1:8000/api/field-audit?limit=50&offset=0&season=2026"
```

Respons `200 OK` berbentuk:

```json
{
  "items": [
    {
      "id": 123,
      "season": "2026",
      "field_number": "F-001",
      "farmer_name": "Nama Petani",
      "audit_date": "2026-01-15",
      "created_at": "2026-01-15T10:30:00",
      "updated_at": "2026-01-15T10:30:00"
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

Setiap objek di `items` berisi semua kolom tabel yang tersedia, termasuk kolom audit generasi dan panen. Contoh di atas hanya menampilkan beberapa kolom. `total` adalah jumlah baris yang cocok dengan filter sebelum pagination diterapkan.

Ambil halaman selanjutnya dengan menambah `offset`, misalnya `offset=50` untuk halaman kedua jika `limit=50`.

### Ambil satu data berdasarkan ID

```http
GET /api/field-audit/{id}
```

Contoh PowerShell:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/field-audit/123'
```

Contoh cURL:

```bash
curl http://127.0.0.1:8000/api/field-audit/123
```

Respons sukses adalah satu objek yang berisi semua kolom tabel. Jika ID tidak ditemukan, API merespons `404 Not Found`.

### Data Fase Vegetative

```http
GET /api/field-audit/vegetative
GET /api/field-audit/fase-vegetative
```

Endpoint ini khusus mengembalikan 50 kolom audit pada fase vegetatif tanaman jagung (tanpa kolom generasi, pra-panen, dan panen).

Parameter query:

| Parameter | Tipe | Default | Batas / perilaku |
|---|---|---:|---|
| `limit` | integer | `100` | 1 sampai 500 |
| `offset` | integer | `0` | 0 atau lebih |
| `season` | string | tidak ada | Filter sama persis pada kolom `season` |
| `field_number` | string | tidak ada | Filter sama persis pada kolom `field_number` |
| `farmer_name` | string | tidak ada | Filter sama persis pada kolom `farmer_name` |

Alternatif: Anda juga dapat menambahkan parameter `phase=vegetative` pada endpoint utama:
`GET /api/field-audit?phase=vegetative`

Sorting juga dapat dipakai pada endpoint daftar fase, misalnya:
`GET /api/field-audit/fase-preharvest?order_by=pre_harvest_audit_date&order=asc`.

Contoh URL:
```text
http://127.0.0.1:8000/api/field-audit/vegetative?limit=50&field_number=DC6715080
```

Contoh cURL:
```bash
curl "http://127.0.0.1:8000/api/field-audit/vegetative?field_number=DC6715080"
```

Contoh PowerShell:
```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/field-audit/vegetative?field_number=DC6715080'
```

### Ambil Satu Data Fase Vegetative

```http
GET /api/field-audit/vegetative/{identifier}
GET /api/field-audit/fase-vegetative/{identifier}
```

Parameter `{identifier}` dapat berupa ID baris database (`18855`) atau nomor field (`DC6715080`). Alternatif: `GET /api/field-audit/{id}?phase=vegetative`.

Contoh cURL:
```bash
curl "http://127.0.0.1:8000/api/field-audit/vegetative/DC6715080"
```

Contoh respons `200 OK` (Schema Fase Vegetative):
```json
{
  "season": "DS26",
  "type_corn": "Field Corn",
  "field_number": "DC6715080",
  "farmer_name": "pak mashud tebu",
  "grower": "Fitrianingsasi",
  "hybrid": "AX09",
  "actual_area_planted": 0.16,
  "discard_area_ha": 0,
  "effective_area_ha": 0.16,
  "previous_crop_corn": "Not Corn",
  "planting_ratio": "04:02:00",
  "planting_space": "60x18",
  "split_planting": "-3,0,0",
  "female_planting_date_actual": "2026-04-24",
  "hamlet": null,
  "village": null,
  "sub_district": null,
  "district": null,
  "province": null,
  "flagging_final": "GF",
  "field_assistant": "Chairunnisa Faza Nabillah",
  "supervisor": "Alfian Dwi Purnomo",
  "manager": "Anggi Yanuar Yanto",
  "region": "Region 3",
  "corr_tagging": "-7.992958,112.747986",
  "qa_spv": "Tonny Andhi Jaya",
  "qa_fi": "David Billy Jepryanto",
  "co_detasseling": "Nisa jep",
  "audit_date": "2026-05-18",
  "audit_week": "21.0",
  "field_size_ha": 0.16,
  "male_split": "Yes",
  "sowing_ratio": "05:02:00",
  "split_field": "No",
  "previous_crop": "Not Corn",
  "one_seed_hole": "Yes",
  "isolation_problem": "No",
  "crop_uniformity": "Fair",
  "crop_health": "Poor",
  "roguing_status": "On Going",
  "lsv_status": "Moderate",
  "offtype_m": "0.0",
  "offtype_f": ">0",
  "poi_accuracy": "Not Valid",
  "rev_planting_date": "2026-04-24",
  "decision": "Pass with Note",
  "action_needed": "Roguing",
  "pld_reason": null,
  "flagging": "GF",
  "remarks": "-"
}
```

### Data Fase Pra-Panen

```http
GET /api/field-audit/preharvest
GET /api/field-audit/fase-preharvest
```

Endpoint ini menerima parameter pagination dan filter yang sama dengan daftar
data utama. Alternatif: `GET /api/field-audit?phase=preharvest`.

Untuk hanya mengambil data yang sudah memiliki tanggal audit pre-harvest,
gunakan parameter `pre_harvest_audit_date_not_null=true`. Secara default,
parameter ini bernilai `false` dan data dengan tanggal kosong tetap disertakan.

Contoh:

```text
http://127.0.0.1:8000/api/field-audit/preharvest?limit=50&offset=0
```

Contoh hanya dengan tanggal audit yang tidak `NULL`:

```text
http://127.0.0.1:8000/api/field-audit/preharvest?pre_harvest_audit_date_not_null=true
```

### Sinkronkan Excel ke MySQL

```http
POST /api/field-audit
```

Request ini tidak membutuhkan body. API membaca workbook, sheet, dan header
yang ditentukan pada `excel` di file konfigurasi saat server dijalankan.
Kolom Excel dipetakan ke schema tabel dengan aturan sinkronisasi yang sama
dengan `sync_excel_to_mysql.py`.

Contoh PowerShell:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/field-audit' `
  -Method Post
```

Contoh cURL:

```bash
curl -X POST http://127.0.0.1:8000/api/field-audit
```

Jika autentikasi API key diaktifkan, tambahkan header `X-API-Key` seperti pada
contoh akses jaringan di bawah.

API membaca semua baris Excel yang berisi data. Jika `table.update_existing`
bernilai `true`, baris dengan kunci dari `table.unique_columns` yang sudah ada
di MySQL akan di-update memakai nilai dari Excel. Kunci yang belum ada akan
di-insert. Kolom kunci, `id`, `created_at`, dan `updated_at` tidak ikut diubah
saat update. Baris dengan nilai kunci kosong dilewati. Nilai tanggal dan
sentinel seperti `0.0` diproses dengan aturan yang sama dengan script sync.

Contoh respons `200 OK`:

```json
{
  "status": "completed",
  "excel_rows": 120,
  "valid_key_rows": 118,
  "skipped_rows": 2,
  "new_rows": 18,
  "inserted_rows": 18,
  "updated_rows": 100,
  "failed_rows": 0
}
```

`new_rows` dan `inserted_rows` menghitung record berkunci baru. `updated_rows`
menghitung baris Excel yang cocok dengan kunci yang sudah ada dan dikirim ke
perintah update. `failed_rows` menghitung insert atau update yang gagal. Jika
ada request sync lain yang masih berjalan, API mengembalikan `409 Conflict`.

## Akses dari komputer lain

API default hanya menerima koneksi lokal. Untuk membukanya di jaringan lokal:

1. Buat API key acak yang panjang dan simpan sebagai environment variable `FIELD_AUDIT_API_KEY` pada komputer server. Jangan commit atau menaruh key di file konfigurasi.
2. Jalankan server dengan host `0.0.0.0`.
3. Batasi port API di firewall agar hanya komputer/jaringan yang diperlukan yang dapat mengaksesnya.
4. Kirim key pada header `X-API-Key` untuk semua endpoint, termasuk `/health`.

Contoh menjalankan pada PowerShell:

```powershell
$env:FIELD_AUDIT_API_KEY = '<GANTI_DENGAN_KEY_ACAK_PANJANG>'
.\.venv\Scripts\python.exe field_audit_api.py --config config.field_audit.example.json --host 0.0.0.0 --port 8000
```

Dari komputer client, gunakan alamat IP komputer server, bukan `127.0.0.1`:

```powershell
$headers = @{ 'X-API-Key' = '<API_KEY_YANG_SAMA>' }
Invoke-RestMethod 'http://<IP_SERVER>:8000/api/field-audit?limit=50' -Headers $headers
```

```bash
curl -H "X-API-Key: <API_KEY_YANG_SAMA>" \
  "http://<IP_SERVER>:8000/api/field-audit?limit=50"
```

Jika API key tidak diset, autentikasi tidak diwajibkan pada bind loopback. Server menolak bind ke interface jaringan seperti `0.0.0.0` jika `FIELD_AUDIT_API_KEY` belum diset. Jangan mengekspos server HTTP ini langsung ke internet; gunakan VPN atau reverse proxy HTTPS dan aturan firewall yang sesuai.

## Kode respons

| Status | Arti |
|---:|---|
| `200` | Request berhasil |
| `401` | API key tidak ada atau salah saat autentikasi diaktifkan |
| `404` | ID data tidak ditemukan |
| `409` | Request sync lain sedang berjalan |
| `422` | Parameter request tidak valid, misalnya `limit` di luar 1-500 |
| `503` | Database tidak dapat diakses atau query database gagal |

Contoh error:

```json
{
  "detail": "Field audit row not found"
}
```

## Batasan

- API menyediakan baca (`GET`) dan pemicu sinkronisasi Excel ke MySQL (`POST`). Tidak ada endpoint untuk menghapus data.
- Atur `table.update_existing` ke `true` untuk memperbarui baris yang kuncinya sudah ada; `false` mempertahankan perilaku insert-only. Kolom non-kunci yang dipetakan dari Excel akan ditimpa termasuk dengan `NULL` jika sel Excel kosong.
- Pastikan `table.unique_columns` sesuai dengan kunci sumber dan tambahkan unique index yang sama di MySQL agar tidak terjadi duplikasi jika API dan scheduler berjalan bersamaan.
- Filter menggunakan pencocokan persis, bukan pencarian sebagian.
- Maksimum satu request daftar mengembalikan 500 baris. Gunakan `offset` untuk melanjutkan halaman.
- API menggunakan kredensial MySQL dari file konfigurasi yang dipilih saat server dijalankan.
