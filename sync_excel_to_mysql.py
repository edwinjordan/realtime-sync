"""
Sinkronisasi Excel (di shared network drive) ke MySQL.

Cara kerja:
1. Baca semua ID yang sudah ada di tabel MySQL.
2. Buka file Excel, baca semua baris yang punya nilai di kolom ID.
3. Bandingkan -> ambil baris yang ID-nya belum ada di MySQL (baris baru).
4. Insert baris baru tersebut ke MySQL.
5. Catat hasilnya ke log file.

Script ini didesain untuk dijalankan berkala (Task Scheduler / cron),
bukan terus-menerus jalan (polling loop). Ini lebih stabil untuk file
di shared network drive yang bisa saja sedang dibuka user lain.
"""

import argparse
import json
import logging
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError

import openpyxl
import mysql.connector
from openpyxl.utils.datetime import from_excel
from mysql.connector import Error as MySQLError

CONFIG_PATH = Path(__file__).parent / "config.json"


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    if not config_path.exists():
        print(
            f"[ERROR] File konfigurasi tidak ditemukan di {config_path}.\n"
            "Pastikan path konfigurasi benar dan sesuaikan isinya."
        )
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_logging(log_file: str):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def read_excel_rows(excel_cfg: dict, retries: int = 3, delay_sec: int = 5):
    """
    Baca semua baris dari Excel sebagai list of dict {header: value}.
    Retry beberapa kali kalau file sedang lock (dibuka user lain / sync OneDrive dsb).
    """
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            wb = openpyxl.load_workbook(
                excel_cfg["file_path"], data_only=True, read_only=True
            )
            sheet = wb[excel_cfg["sheet_name"]]

            header_row_num = excel_cfg["header_row"]
            rows_iter = sheet.iter_rows(min_row=header_row_num)
            headers = [cell.value for cell in next(rows_iter)]

            rows = []
            for row in rows_iter:
                values = [cell.value for cell in row]
                # Lewati baris yang kosong total
                if all(v is None for v in values):
                    continue
                row_dict = dict(zip(headers, values))
                rows.append(row_dict)

            wb.close()
            return rows

        except PermissionError as e:
            last_error = e
            logging.warning(
                f"File Excel sedang terkunci (percobaan {attempt}/{retries}). "
                f"Coba lagi dalam {delay_sec} detik..."
            )
            time.sleep(delay_sec)
        except Exception as e:
            last_error = e
            logging.error(f"Gagal membaca Excel: {e}")
            break

    raise RuntimeError(f"Tidak bisa membaca file Excel setelah beberapa percobaan: {last_error}")


def get_existing_ids(mysql_cfg: dict, table_cfg: dict) -> set:
    conn = mysql.connector.connect(**mysql_cfg)
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT `{table_cfg['id_column']}` FROM `{table_cfg['name']}`")
        ids = {str(row[0]) for row in cursor.fetchall()}
        cursor.close()
        return ids
    finally:
        conn.close()


def get_existing_keys(mysql_cfg: dict, table_cfg: dict, key_columns: list) -> set:
    conn = mysql.connector.connect(**mysql_cfg)
    try:
        cursor = conn.cursor()
        selected_columns = ", ".join(f"`{column}`" for column in key_columns)
        cursor.execute(f"SELECT {selected_columns} FROM `{table_cfg['name']}`")
        keys = {
            tuple(str(value) for value in row)
            for row in cursor.fetchall()
            if all(value is not None for value in row)
        }
        cursor.close()
        return keys
    finally:
        conn.close()


def get_table_column_types(mysql_cfg: dict, table_cfg: dict) -> dict:
    conn = mysql.connector.connect(**mysql_cfg)
    try:
        cursor = conn.cursor()
        cursor.execute(f"SHOW COLUMNS FROM `{table_cfg['name']}`")
        column_types = {row[0]: row[1] for row in cursor.fetchall()}
        cursor.close()
        return column_types
    finally:
        conn.close()


def normalize_column_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return re.sub(r"^gen_([1-5])_", r"gen\1_", normalized)


def normalize_database_value(value, column_type: str):
    if value is None or "date" not in column_type.lower() and "time" not in column_type.lower():
        return value

    if isinstance(value, str):
        if value.strip().lower() in {"", "0", "0.0", "0000-00-00"}:
            return None
        return value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 0:
            return None
        converted = from_excel(value)
        if isinstance(converted, datetime):
            return converted.date() if column_type.lower().startswith("date") else converted
        return converted

    return value


def map_row_to_table(
    row: dict, table_cfg: dict, db_columns: set = None, db_column_types: dict = None
) -> dict:
    field_map = table_cfg.get("field_map", {}) or {}
    excluded_columns = set(table_cfg.get("insert_exclude_columns", []))

    if db_columns is not None:
        normalized_columns = {normalize_column_name(column): column for column in db_columns}
        mapped = {
            normalized_columns[normalize_column_name(source)]: value
            for source, value in row.items()
            if normalize_column_name(source) in normalized_columns
        }
        mapped.update(
            {
                target: row[source]
                for target, source in field_map.items()
                if source in row and target in db_columns
            }
        )
    elif field_map:
        mapped = {
            target: row[source]
            for target, source in field_map.items()
            if source in row
        }
    else:
        mapped = dict(row)

    return {
        column: normalize_database_value(value, db_column_types[column])
        if db_column_types and column in db_column_types
        else value
        for column, value in mapped.items()
        if column not in excluded_columns
    }


def build_row_key(row: dict, key_columns: list):
    values = [row.get(column) for column in key_columns]
    if any(value is None or value == "" for value in values):
        return None
    return tuple(str(value) for value in values)


def select_new_rows(rows: list, existing_keys: set, key_columns: list) -> list:
    new_rows = []
    for row in rows:
        key = build_row_key(row, key_columns)
        if key is not None and key not in existing_keys:
            new_rows.append(row)
            existing_keys.add(key)
    return new_rows


def build_chemical_transaction_payload(row: dict, api_cfg: dict) -> dict:
    field_map = api_cfg.get("field_map", {}) or {}
    defaults = api_cfg.get("defaults", {}) or {}

    payload = {}
    for target_field, source_field in field_map.items():
        if source_field in row and row[source_field] is not None:
            payload[target_field] = row[source_field]
        elif target_field in defaults:
            payload[target_field] = defaults[target_field]

    for target_field, default_value in defaults.items():
        payload.setdefault(target_field, default_value)

    return payload


def send_chemical_transaction_api(api_cfg: dict, row: dict) -> tuple[bool, str]:
    payload = build_chemical_transaction_payload(row, api_cfg)
    logging.debug(f"Payload untuk API: {payload}")
    url = api_cfg.get("url")
    if not url:
        return False, "URL API belum dikonfigurasi"

    headers = dict(api_cfg.get("headers", {}) or {})
    if "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=api_cfg.get("timeout_sec", 30)) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            return True, response_body
    except HTTPError as e:
        response_body = e.read().decode("utf-8", errors="replace")
        return False, f"HTTP {e.code}: {response_body}"
    except URLError as e:
        return False, f"URL error: {e.reason}"
    except Exception as e:
        return False, f"Unexpected error: {e}"


def sync_rows_to_api(api_cfg: dict, rows: list) -> int:
    if not rows:
        return 0
    success_count = 0
    for row in rows:

        success, response_body = send_chemical_transaction_api(api_cfg, row)
        if success:
            success_count += 1
            logging.info(f"Berhasil mengirim ke API: {response_body}")
        else:
            logging.error(f"Gagal mengirim ke API untuk baris {row}: {response_body}")

    return success_count


def insert_new_rows(mysql_cfg: dict, table_cfg: dict, rows: list):
    if not rows:
        return 0, []

    conn = mysql.connector.connect(**mysql_cfg)
    inserted = 0
    inserted_rows = []
    try:
        cursor = conn.cursor()
        columns = list(dict.fromkeys(column for row in rows for column in row))
        col_names = ", ".join(f"`{c}`" for c in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        sql = f"INSERT INTO `{table_cfg['name']}` ({col_names}) VALUES ({placeholders})"

        for row in rows:
            values = [row.get(column) for column in columns]
            try:
                cursor.execute(sql, values)
                inserted += 1
                inserted_rows.append(row)
            except MySQLError as e:
                logging.error(f"Gagal insert baris {row}: {e}")

        conn.commit()
        cursor.close()
    finally:
        conn.close()

    return inserted, inserted_rows


def upsert_rows(mysql_cfg: dict, table_cfg: dict, rows: list, key_columns: list, existing_keys: set):
    if not rows:
        return 0, 0, 0

    conn = mysql.connector.connect(**mysql_cfg)
    inserted = 0
    updated = 0
    failed = 0
    excluded_from_update = set(key_columns) | {"id", "created_at", "updated_at"}
    cursor = None
    try:
        cursor = conn.cursor()
        for row in rows:
            key = build_row_key(row, key_columns)
            if key is None:
                failed += 1
                continue

            columns = list(row)
            update_columns = [column for column in columns if column not in excluded_from_update]
            try:
                if key in existing_keys:
                    if update_columns:
                        set_clause = ", ".join(f"`{column}` = %s" for column in update_columns)
                        where_clause = " AND ".join(f"`{column}` = %s" for column in key_columns)
                        values = [row[column] for column in update_columns]
                        values.extend(row[column] for column in key_columns)
                        cursor.execute(
                            f"UPDATE `{table_cfg['name']}` SET {set_clause} WHERE {where_clause}",
                            values,
                        )
                    updated += 1
                    continue

                col_names = ", ".join(f"`{column}`" for column in columns)
                placeholders = ", ".join(["%s"] * len(columns))
                values = [row[column] for column in columns]
                cursor.execute(
                    f"INSERT INTO `{table_cfg['name']}` ({col_names}) VALUES ({placeholders})",
                    values,
                )
                existing_keys.add(key)
                inserted += 1
            except MySQLError as error:
                failed += 1
                logging.error(f"Gagal upsert baris {row}: {error}")

        conn.commit()
    finally:
        if cursor is not None:
            cursor.close()
        conn.close()

    return inserted, updated, failed


def main():
    parser = argparse.ArgumentParser(description="Sinkronisasi Excel ke MySQL")
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="Path file konfigurasi JSON",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    setup_logging(config.get("log_file", "sync_log.txt"))

    logging.info("=== Mulai sinkronisasi Excel -> MySQL ===")

    excel_cfg = config["excel"]
    mysql_cfg = config["mysql"]
    table_cfg = config["table"]
    id_column_excel = excel_cfg.get("id_column")
    api_cfg = config.get("api") or {}

    try:
        excel_rows = read_excel_rows(excel_cfg)
        logging.info(f"Jumlah baris terbaca dari Excel: {len(excel_rows)}")

        unique_columns = table_cfg.get("unique_columns") or []
        if unique_columns:
            db_column_types = get_table_column_types(mysql_cfg, table_cfg) if table_cfg.get(
                "auto_map_columns", False
            ) else None
            db_columns = set(db_column_types) if db_column_types is not None else None
            if db_columns is not None:
                missing_key_columns = set(unique_columns) - db_columns
                if missing_key_columns:
                    raise ValueError(
                        "Kolom kunci tidak ada di tabel MySQL: "
                        + ", ".join(sorted(missing_key_columns))
                    )

            prepared_rows = [
                map_row_to_table(row, table_cfg, db_columns, db_column_types)
                for row in excel_rows
            ]
            missing_mapped_keys = set(unique_columns) - set().union(
                *(row.keys() for row in prepared_rows)
            ) if prepared_rows else set(unique_columns)
            if missing_mapped_keys:
                raise ValueError(
                    "Kolom kunci belum dipetakan dari header Excel: "
                    + ", ".join(sorted(missing_mapped_keys))
                    + ". Periksa header Excel atau table.field_map."
                )

            existing_keys = get_existing_keys(mysql_cfg, table_cfg, unique_columns)
            new_rows = select_new_rows(prepared_rows, set(existing_keys), unique_columns)
            logging.info(f"Jumlah kunci data yang sudah ada di MySQL: {len(existing_keys)}")
        else:
            existing_ids = get_existing_ids(mysql_cfg, table_cfg)
            logging.info(f"Jumlah data yang sudah ada di MySQL: {len(existing_ids)}")
            new_rows = [
                row for row in excel_rows
                if id_column_excel
                and row.get(id_column_excel) is not None
                and str(row[id_column_excel]) not in existing_ids
            ]

        # logging.info(f"Baris data: {new_rows}")

        logging.info(f"Baris baru yang perlu disinkron: {len(new_rows)}")

        if unique_columns and table_cfg.get("update_existing", False):
            inserted_count, updated_count, failed_count = upsert_rows(
                mysql_cfg, table_cfg, prepared_rows, unique_columns, existing_keys
            )
            logging.info(
                f"Berhasil insert {inserted_count} baris baru dan update {updated_count} baris lama"
            )
            if api_cfg.get("enabled", False):
                synced_to_api_count = sync_rows_to_api(api_cfg, new_rows)
                logging.info(f"Berhasil mengirim {synced_to_api_count} baris ke API")
            else:
                logging.info("Fitur API sinkronisasi dinonaktifkan pada config")
        else:
            inserted_count, inserted_rows = insert_new_rows(mysql_cfg, table_cfg, new_rows)
            updated_count = 0
            failed_count = len(new_rows) - inserted_count
            logging.info(f"Berhasil insert {inserted_count} baris baru ke MySQL")
            if api_cfg.get("enabled", False):
                synced_to_api_count = sync_rows_to_api(api_cfg, inserted_rows)
                logging.info(f"Berhasil mengirim {synced_to_api_count} baris ke API")
            else:
                logging.info("Fitur API sinkronisasi dinonaktifkan pada config")

    except Exception as e:
        logging.error(f"Sinkronisasi gagal: {e}")
        sys.exit(1)

    logging.info("=== Selesai ===\n")


if __name__ == "__main__":
    main()
