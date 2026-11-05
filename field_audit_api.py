"""HTTP API for reading and inserting rows in the configured field_audit table."""

import argparse
import hmac
import ipaddress
import json
import logging
import os
import re
from pathlib import Path
from threading import Lock

import mysql.connector
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import APIKeyHeader
from mysql.connector import Error as MySQLError

import sync_excel_to_mysql as sync_service
import vegetative_api
import generative_api
import pre_harvest_api
import harvest_api

DEFAULT_CONFIG = Path(__file__).parent / "config.field_audit.example.json"
MYSQL_CONFIG = None
TABLE_NAME = None
UNIQUE_COLUMNS = []
EXCEL_CONFIG = None
TABLE_CONFIG = None
SYNC_LOCK = Lock()

# Re-export vegetative API components for backward compatibility
VEGETATIVE_COLUMNS = vegetative_api.VEGETATIVE_COLUMNS
format_vegetative_row = vegetative_api.format_vegetative_row
normalize_pagination = vegetative_api.normalize_pagination
query_vegetative_items = vegetative_api.query_vegetative_items
fetch_field_audit_vegetative = vegetative_api.fetch_field_audit_vegetative
list_field_audit_vegetative = vegetative_api.list_field_audit_vegetative
get_field_audit_vegetative = vegetative_api.get_field_audit_vegetative

# Re-export generative API components for backward compatibility
GENERATIVE_COLUMNS = generative_api.GENERATIVE_COLUMNS
format_generative_row = generative_api.format_generative_row
query_generative_items = generative_api.query_generative_items
fetch_field_audit_generative = generative_api.fetch_field_audit_generative
list_field_audit_generative = generative_api.list_field_audit_generative
get_field_audit_generative = generative_api.get_field_audit_generative

# Re-export preharvest API components for backward compatibility
PREHARVEST_COLUMNS = pre_harvest_api.PREHARVEST_COLUMNS
format_preharvest_row = pre_harvest_api.format_preharvest_row
query_preharvest_items = pre_harvest_api.query_preharvest_items
fetch_field_audit_preharvest = pre_harvest_api.fetch_field_audit_preharvest
list_field_audit_preharvest = pre_harvest_api.list_field_audit_preharvest
get_field_audit_preharvest = pre_harvest_api.get_field_audit_preharvest

# Re-export harvest API components for backward compatibility
HARVEST_COLUMNS = harvest_api.HARVEST_COLUMNS
format_harvest_row = harvest_api.format_harvest_row
query_harvest_items = harvest_api.query_harvest_items
fetch_field_audit_harvest = harvest_api.fetch_field_audit_harvest
list_field_audit_harvest = harvest_api.list_field_audit_harvest
get_field_audit_harvest = harvest_api.get_field_audit_harvest

app = FastAPI(title="Field Audit API", version="1.1.0")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(provided_key: str = Depends(api_key_header)):
    expected_key = os.getenv("FIELD_AUDIT_API_KEY")
    if expected_key and (
        not provided_key or not hmac.compare_digest(provided_key, expected_key)
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def get_database_connection():
    if MYSQL_CONFIG is None or TABLE_NAME is None:
        raise HTTPException(status_code=503, detail="API database is not configured")
    try:
        return mysql.connector.connect(**MYSQL_CONFIG)
    except MySQLError:
        logging.exception("Failed to connect to the field_audit database")
        raise HTTPException(status_code=503, detail="Database is unavailable") from None


def run_query(sql: str, values: tuple = (), fetch_one: bool = False):
    connection = get_database_connection()
    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(sql, values)
        return cursor.fetchone() if fetch_one else cursor.fetchall()
    except MySQLError:
        logging.exception("Field audit query failed")
        raise HTTPException(status_code=503, detail="Database query failed") from None
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def sync_excel_to_database():
    if EXCEL_CONFIG is None or TABLE_CONFIG is None or MYSQL_CONFIG is None:
        raise HTTPException(status_code=503, detail="API sync is not configured")
    if not UNIQUE_COLUMNS:
        raise HTTPException(status_code=503, detail="table.unique_columns must be configured for sync")

    try:
        excel_rows = sync_service.read_excel_rows(EXCEL_CONFIG)
        if not excel_rows:
            return {
                "status": "completed",
                "excel_rows": 0,
                "valid_key_rows": 0,
                "duplicate_rows": 0,
                "skipped_rows": 0,
                "new_rows": 0,
                "inserted_rows": 0,
                "failed_rows": 0,
            }

        column_types = sync_service.get_table_column_types(MYSQL_CONFIG, TABLE_CONFIG)
        db_columns = set(column_types)
        missing_db_keys = set(UNIQUE_COLUMNS) - db_columns
        if missing_db_keys:
            raise ValueError(
                "Unique key columns do not exist in MySQL: "
                + ", ".join(sorted(missing_db_keys))
            )

        mapped_rows = [
            sync_service.map_row_to_table(row, TABLE_CONFIG, db_columns, column_types)
            for row in excel_rows
        ]
        mapped_columns = set().union(*(row.keys() for row in mapped_rows)) if mapped_rows else set()
        missing_excel_keys = set(UNIQUE_COLUMNS) - mapped_columns
        if missing_excel_keys:
            raise ValueError(
                "Unique key columns are missing from the Excel headers: "
                + ", ".join(sorted(missing_excel_keys))
            )

        existing_keys = sync_service.get_existing_keys(MYSQL_CONFIG, TABLE_CONFIG, UNIQUE_COLUMNS)
        valid_key_rows = sum(
            sync_service.build_row_key(row, UNIQUE_COLUMNS) is not None
            for row in mapped_rows
        )
        if TABLE_CONFIG.get("update_existing", False):
            inserted_count, updated_count, failed_count = sync_service.upsert_rows(
                MYSQL_CONFIG, TABLE_CONFIG, mapped_rows, UNIQUE_COLUMNS, existing_keys
            )
            new_rows_count = inserted_count
        else:
            new_rows = sync_service.select_new_rows(
                mapped_rows, set(existing_keys), UNIQUE_COLUMNS
            )
            inserted_count, _ = sync_service.insert_new_rows(
                MYSQL_CONFIG, TABLE_CONFIG, new_rows
            )
            updated_count = 0
            failed_count = len(new_rows) - inserted_count
            new_rows_count = len(new_rows)
    except HTTPException:
        raise
    except Exception:
        logging.exception("Excel-to-MySQL sync failed")
        raise HTTPException(
            status_code=503,
            detail="Excel-to-MySQL sync failed; check the API server log",
        ) from None

    return {
        "status": "completed" if failed_count == 0 else "partial",
        "excel_rows": len(excel_rows),
        "valid_key_rows": valid_key_rows,
        "skipped_rows": len(excel_rows) - valid_key_rows,
        "new_rows": new_rows_count,
        "inserted_rows": inserted_count,
        "updated_rows": updated_count,
        "failed_rows": failed_count,
    }


# Wire vegetative_api with database query executor and table name getter
vegetative_api.init_vegetative_api(
    run_query_fn=lambda *args, **kwargs: run_query(*args, **kwargs),
    get_table_name_fn=lambda: TABLE_NAME,
)

# Include Vegetative Phase router with authentication dependency
app.include_router(vegetative_api.router, dependencies=[Depends(require_api_key)])

# Wire generative_api with database query executor and table name getter
generative_api.init_generative_api(
    run_query_fn=lambda *args, **kwargs: run_query(*args, **kwargs),
    get_table_name_fn=lambda: TABLE_NAME,
)

# Include Generative Phase router with authentication dependency
app.include_router(generative_api.router, dependencies=[Depends(require_api_key)])

# Wire preharvest_api with database query executor and table name getter
pre_harvest_api.init_preharvest_api(
    run_query_fn=lambda *args, **kwargs: run_query(*args, **kwargs),
    get_table_name_fn=lambda: TABLE_NAME,
)

# Include Preharvest Phase router with authentication dependency
app.include_router(pre_harvest_api.router, dependencies=[Depends(require_api_key)])

# Wire harvest_api with database query executor and table name getter
harvest_api.init_harvest_api(
    run_query_fn=lambda *args, **kwargs: run_query(*args, **kwargs),
    get_table_name_fn=lambda: TABLE_NAME,
)

# Include Harvest Phase router with authentication dependency
app.include_router(harvest_api.router, dependencies=[Depends(require_api_key)])


@app.post("/api/field-audit", dependencies=[Depends(require_api_key)])
def sync_field_audit_from_excel():
    if not SYNC_LOCK.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="An Excel sync is already running")
    try:
        return sync_excel_to_database()
    finally:
        SYNC_LOCK.release()


@app.get("/health", dependencies=[Depends(require_api_key)])
def health_check():
    return {"status": "ok"}


@app.get("/api/field-audit", dependencies=[Depends(require_api_key)])
def list_field_audit(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    season: str | None = None,
    field_number: str | None = None,
    farmer_name: str | None = None,
    phase: str | None = Query(default=None, description="Filter output schema by phase, e.g. 'vegetative' or 'fase-vegetative'"),
    fase: str | None = Query(default=None, description="Alias untuk parameter phase"),
):
    selected_phase = (phase or fase or "").lower().replace("_", "-")
    if selected_phase in ("vegetative", "fase-vegetative"):
        return query_vegetative_items(
            limit=limit,
            offset=offset,
            filters_dict={
                "season": season,
                "field_number": field_number,
                "farmer_name": farmer_name,
            },
        )
    if selected_phase in ("generative", "fase-generative"):
        return query_generative_items(
            limit=limit,
            offset=offset,
            filters_dict={
                "season": season,
                "field_number": field_number,
                "farmer_name": farmer_name,
            },
        )

    if selected_phase in ("preharvest", "fase-preharvest"):
        return query_preharvest_items(
            limit=limit,
            offset=offset,
            filters_dict={
                "season": season,
                "field_number": field_number,
                "farmer_name": farmer_name,
            },
        )    

    if selected_phase in ("harvest", "fase-harvest"):
            return query_harvest_items(
                limit=limit,
                offset=offset,
                filters_dict={
                    "season": season,
                    "field_number": field_number,
                    "farmer_name": farmer_name,
                },
            )    

    filters = []
    values = []
    for column, value in (
        ("season", season),
        ("field_number", field_number),
        ("farmer_name", farmer_name),
    ):
        if value is not None:
            filters.append(f"`{column}` = %s")
            values.append(value)

    where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""
    limit_val, offset_val = normalize_pagination(limit, offset)
    table = f"`{TABLE_NAME}`"
    total_rows = run_query(
        f"SELECT COUNT(*) AS total FROM {table}{where_clause}", tuple(values), fetch_one=True
    )
    items = run_query(
        f"SELECT * FROM {table}{where_clause} ORDER BY `id` DESC LIMIT %s OFFSET %s",
        tuple(values + [limit_val, offset_val]),
    )
    return {"items": items, "total": total_rows["total"], "limit": limit_val, "offset": offset_val}


@app.get("/api/field-audit/{row_id:int}", dependencies=[Depends(require_api_key)])
def get_field_audit(
    row_id: int,
    phase: str | None = Query(default=None, description="Filter output schema by phase, e.g. 'vegetative' or 'fase-vegetative'"),
    fase: str | None = Query(default=None, description="Alias untuk parameter phase"),
):
    selected_phase = (phase or fase or "").lower().replace("_", "-")
    if selected_phase in ("vegetative", "fase-vegetative"):
        return fetch_field_audit_vegetative(str(row_id))
    if selected_phase in ("generative", "fase-generative"):
        return fetch_field_audit_generative(str(row_id))
    if selected_phase in ("preharvest", "fase-preharvest"):
        return fetch_field_audit_preharvest(str(row_id))
    if selected_phase in ("harvest", "fase-harvest"):
        return fetch_field_audit_harvest(str(row_id))

    row = run_query(
        f"SELECT * FROM `{TABLE_NAME}` WHERE `id` = %s LIMIT 1",
        (row_id,),
        fetch_one=True,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Field audit row not found")
    return row


def is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main():
    parser = argparse.ArgumentParser(description="Field audit API and Excel sync service")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--host", default=os.getenv("FIELD_AUDIT_API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("FIELD_AUDIT_API_PORT", "8000")))
    args = parser.parse_args()

    if not args.config.exists():
        parser.error(f"Configuration file not found: {args.config}")
    with args.config.open("r", encoding="utf-8") as config_file:
        config = json.load(config_file)

    global MYSQL_CONFIG, TABLE_NAME, UNIQUE_COLUMNS, EXCEL_CONFIG, TABLE_CONFIG
    EXCEL_CONFIG = config["excel"]
    MYSQL_CONFIG = config["mysql"]
    TABLE_CONFIG = config["table"]
    TABLE_NAME = config["table"]["name"]
    UNIQUE_COLUMNS = config.get("table", {}).get("unique_columns", []) or []
    if not re.fullmatch(r"[A-Za-z0-9_]+", TABLE_NAME):
        parser.error("table.name must contain only letters, numbers, and underscores")
    if any(not re.fullmatch(r"[A-Za-z0-9_]+", column) for column in UNIQUE_COLUMNS):
        parser.error("table.unique_columns may contain only letters, numbers, and underscores")

    api_key = os.getenv("FIELD_AUDIT_API_KEY")
    if not is_loopback(args.host) and not api_key:
        parser.error("Set FIELD_AUDIT_API_KEY before binding the API to a network interface")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
