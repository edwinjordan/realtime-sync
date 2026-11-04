# Dokumentasi API: POST Chemical Transaction

Dokumentasi API untuk menyimpan data transaksi kimia ke tabel master `chemical_trans` dan detail `chemical_trans_detail`.

---

## 1. POST `/api/chemical-transaction/flat`

Endpoint khusus untuk menyimpan transaksi kimia dengan format **flat payload**.

### Information
- **Method**: `POST`
- **Path**: `/api/chemical-transaction/flat`
- **Content-Type**: `application/json`
- **Auth**: `Bearer Token` (Opsional / Tergantung konfigurasi middleware)

### Request Body (Flat Payload)

| Parameter | Tipe Data | Mandatory | Keterangan |
|---|---|---|---|
| `chemical_trans_bulan` | `string` | Ya | Nama/kode bulan (contoh: `"Januari"`, `"01"`) |
| `chemical_trans_detail_chemical` | `string` | Tidak | ID / Kode bahan kimia (contoh: `"CHEM-001"`) |
| `chemical_trans_detail_jumlah` | `number` | Ya | Jumlah / quantity pemakaian bahan kimia (contoh: `100.5`) |
| `chemical_trans_detail_chemical_nama` | `string` | Ya | Nama bahan kimia (contoh: `"Pestisida A"`) |
| `chemical_trans_region` | `string` | Ya | Region / Wilayah transaksi (contoh: `"Region 1"`) |
| `chemical_trans_tahun` | `integer` | Ya | Tahun / Season transaksi (contoh: `2026`) |

#### Contoh JSON Request:
```json
{
  "chemical_trans_bulan": "Januari",
  "chemical_trans_detail_chemical": "CHEM-001",
  "chemical_trans_detail_jumlah": 100,
  "chemical_trans_detail_chemical_nama": "Pestisida A",
  "chemical_trans_region": "1",
  "chemical_trans_tahun": 2026
}
```

### Response Success (`200 OK`)

```json
{
  "error": false,
  "message": "Berhasil menyimpan data",
  "data": {
    "chemical_trans_id": "c6a8f1b2-3e4d-5f6a-7b8c-9d0e1f2a3b4c",
    "chemical_trans_season": 2026,
    "chemical_trans_region": "1",
    "chemical_trans_bulan": "Januari",
    "chemical_trans_created_at": "2026-07-27T15:00:00+07:00",
    "details": [
      {
        "chemical_trans_detail_id": "d1e2f3a4-5b6c-7d8e-9f0a-1b2c3d4e5f6a",
        "chemical_trans_detail_parent": "c6a8f1b2-3e4d-5f6a-7b8c-9d0e1f2a3b4c",
        "chemical_trans_detail_chemical": "CHEM-001",
        "chemical_trans_detail_jumlah": 100,
        "chemical_trans_detail_chemical_nama": "Pestisida A"
      }
    ]
  }
}
```

---

## 2. POST `/api/chemical-transaction`

Endpoint universal yang mendukung format **flat payload** maupun **nested payload**.

### Information
- **Method**: `POST`
- **Path**: `/api/chemical-transaction`
- **Content-Type**: `application/json`

### Option A: Flat Payload
Sama dengan endpoint `/api/chemical-transaction/flat`:

```json
{
  "chemical_trans_bulan": "Januari",
  "chemical_trans_detail_chemical": "CHEM-001",
  "chemical_trans_detail_jumlah": 100,
  "chemical_trans_detail_chemical_nama": "Pestisida A",
  "chemical_trans_region": "1",
  "chemical_trans_tahun": 2026
}
```

### Option B: Nested Payload (Multiple Details)

```json
{
  "chemical_trans_season": 2026,
  "chemical_trans_region": "1",
  "chemical_trans_bulan": "Januari",
  "details": [
    {
      "chemical_trans_detail_chemical": "CHEM-001",
      "chemical_trans_detail_jumlah": 100,
      "chemical_trans_detail_chemical_nama": "Pestisida A"
    },
    {
      "chemical_trans_detail_chemical": "CHEM-002",
      "chemical_trans_detail_jumlah": 50,
      "chemical_trans_detail_chemical_nama": "Fungisida B"
    }
  ]
}
```

---

## Data Mapping Ke Database Table

Proses pencatatan dilakukan secara **atomic** dalam 1 skema Database Transaction (`BEGIN ... COMMIT`):

### 1. Master Table (`chemical_trans`)
| Column Database | Source Field Payload |
|---|---|
| `chemical_trans_id` | Auto-generated UUID |
| `chemical_trans_season` | `chemical_trans_tahun` / `chemical_trans_season` |
| `chemical_trans_region` | `chemical_trans_region` |
| `chemical_trans_bulan` | `chemical_trans_bulan` |
| `chemical_trans_created_at` | `NOW()` (Timestamp waktu penyimpanan) |

### 2. Detail Table (`chemical_trans_detail`)
| Column Database | Source Field Payload |
|---|---|
| `chemical_trans_detail_id` | Auto-generated UUID |
| `chemical_trans_detail_parent` | `chemical_trans_id` (FK to Master) |
| `chemical_trans_detail_chemical` | `chemical_trans_detail_chemical` |
| `chemical_trans_detail_jumlah` | `chemical_trans_detail_jumlah` |
| `chemical_trans_detail_chemical_nama` | `chemical_trans_detail_chemical_nama` |

---

## Response Error Codes

### `400 Bad Request`
Terjadi jika payload JSON tidak valid atau field wajib tidak diisi.

```json
{
  "error": true,
  "message": "chemical_trans_tahun is required",
  "data": null
}
```

### `500 Internal Server Error`
Terjadi jika terdapat kegagalan koneksi database atau kueri SQL.

```json
{
  "error": true,
  "message": "Internal server error details",
  "data": null
}
```

---

## Contoh cURL Command

```bash
curl -X POST http://localhost:8080/api/chemical-transaction/flat \
  -H "Content-Type: application/json" \
  -d '{
    "chemical_trans_bulan": "Januari",
    "chemical_trans_detail_chemical": "CHEM-001",
    "chemical_trans_detail_jumlah": 100,
    "chemical_trans_detail_chemical_nama": "Pestisida A",
    "chemical_trans_region": "1",
    "chemical_trans_tahun": 2026
  }'
```
