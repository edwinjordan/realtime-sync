"""Pre Harvest Phase GET API for Field Audit."""

import datetime
import decimal
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query

PREHARVEST_COLUMNS = [
    "season",
    "type_corn",
    "field_number",
    "farmer_name",
    "grower",
    "hybrid",
    "actual_area_planted",
    "discard_area_ha",
    "effective_area_ha",
    "previous_crop_corn",
    "planting_ratio",
    "planting_space",
    "split_planting",
    "female_planting_date_actual",
    "hamlet",
    "village",
    "sub_district",
    "district",
    "province",
    "flagging_final",
    "field_assistant",
    "supervisor",
    "manager",
    "region",
    "corr_tagging",
    "qa_spv",
    "qa_fi",
    "pre_harvest_audit_date",
    "pre_harvest_audit_week",
    "pre_harvest_male_chopping_rows",
    "pre_harvest_crop_health",
    "pre_harvest_crop_uniformity",
    "pre_harvest_crop_condition",
    "pre_harvest_discard_area_ha",
    "pre_harvest_discard_reason",
    "pre_harvest_final_flagging",
    "pre_harvest_final_decision",
    "pre_harvest_remarks",
]

_RUN_QUERY_FN: Callable[..., Any] | None = None
_GET_TABLE_NAME_FN: Callable[[], str] | None = None

def init_preharvest_api(
    run_query_fn: Callable[..., Any],
    get_table_name_fn: Callable[[], str],
) -> None:
    """Initialize database query executor and table name getter."""
    global _RUN_QUERY_FN, _GET_TABLE_NAME_FN
    _RUN_QUERY_FN = run_query_fn
    _GET_TABLE_NAME_FN = get_table_name_fn

def _get_executor() -> tuple[Callable[..., Any], str]:
    if _RUN_QUERY_FN is None or _GET_TABLE_NAME_FN is None:
        raise HTTPException(status_code=503, detail="Pre Harvest API database is not configured")
    return _RUN_QUERY_FN, _GET_TABLE_NAME_FN()   

def format_preharvest_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Format and serialize a database row into the 50-field preharvest schema."""
    if not row:
        return row
    result: dict[str, Any] = {}
    for col in PREHARVEST_COLUMNS:
        val = row.get(col)
        if isinstance(val, decimal.Decimal):
            float_val = float(val)
            val = int(float_val) if float_val.is_integer() else float_val
        elif isinstance(val, (datetime.date, datetime.datetime)):
            val = val.strftime("%Y-%m-%d")
        elif isinstance(val, datetime.time):
            val = val.strftime("%H:%M:%S")
        elif isinstance(val, datetime.timedelta):
            total_seconds = int(val.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            val = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        result[col] = val
    return result    

def normalize_pagination(limit: Any, offset: Any) -> tuple[int, int]:
    """Normalize limit and offset values to integer."""
    limit_val = getattr(limit, "default", limit)
    offset_val = getattr(offset, "default", offset)
    try:
        limit_val = int(limit_val)
    except (TypeError, ValueError):
        limit_val = 100
    try:
        offset_val = int(offset_val)
    except (TypeError, ValueError):
        offset_val = 0
    return limit_val, offset_val  

def query_preharvest_items(
    limit: Any = 100,
    offset: Any = 0,
    filters_dict: dict[str, Any] | None = None,
    run_query_fn: Callable[..., Any] | None = None,
    table_name: str | None = None,
) -> dict[str, Any]:
    """Query MySQL database for preharvest phase items with filtering and pagination."""
    if run_query_fn is None or table_name is None:
        default_run_query, default_table = _get_executor()
        run_query_fn = run_query_fn or default_run_query
        table_name = table_name or default_table

    filters = []
    values = []
    if filters_dict:
        for column, value in filters_dict.items():
            if value is not None:
                filters.append(f"`{column}` = %s")
                values.append(value)

    where_clause = f" WHERE {' AND '.join(filters)}" if filters else ""
    limit_val, offset_val = normalize_pagination(limit, offset)
    table = f"`{table_name}`"
    columns_sql = ", ".join(f"`{col}`" for col in PREHARVEST_COLUMNS)

    total_rows = run_query_fn(
        f"SELECT COUNT(*) AS total FROM {table}{where_clause}", tuple(values), fetch_one=True
    )
    raw_items = run_query_fn(
        f"SELECT {columns_sql} FROM {table}{where_clause} ORDER BY `id` DESC LIMIT %s OFFSET %s",
        tuple(values + [limit_val, offset_val]),
    )
    items = [format_preharvest_row(item) for item in (raw_items or [])]
    total_count = total_rows["total"] if total_rows and "total" in total_rows else 0
    return {"items": items, "total": total_count, "limit": limit_val, "offset": offset_val} 

def fetch_field_audit_preharvest(
    identifier: str,
    run_query_fn: Callable[..., Any] | None = None,
    table_name: str | None = None,
) -> dict[str, Any]:
    """Fetch a single preharvest phase record by database row ID or field_number."""
    if run_query_fn is None or table_name is None:
        default_run_query, default_table = _get_executor()
        run_query_fn = run_query_fn or default_run_query
        table_name = table_name or default_table

    columns_sql = ", ".join(f"`{col}`" for col in PREHARVEST_COLUMNS)
    table = f"`{table_name}`"
    row = None
    if identifier.isdigit():
        row = run_query_fn(
            f"SELECT {columns_sql} FROM {table} WHERE `id` = %s LIMIT 1",
            (int(identifier),),
            fetch_one=True,
        )
    if row is None:
        row = run_query_fn(
            f"SELECT {columns_sql} FROM {table} WHERE `field_number` = %s LIMIT 1",
            (identifier,),
            fetch_one=True,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Field audit preharvest row not found")
    return format_preharvest_row(row)   

router = APIRouter(tags=["Pre Harvest Phase"])

@router.get("/api/field-audit/preharvest")
@router.get("/api/field-audit/fase-preharvest")
def list_field_audit_preharvest(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    season: str | None = None,
    field_number: str | None = None,
    farmer_name: str | None = None,
):
    return query_preharvest_items(
        limit=limit,
        offset=offset,
        filters_dict={
            "season": season,
            "field_number": field_number,
            "farmer_name": farmer_name,
        },
    )    

@router.get("/api/field-audit/preharvest/{identifier}")
@router.get("/api/field-audit/fase-preharvest/{identifier}")
def get_field_audit_preharvest(identifier: str):
    return fetch_field_audit_preharvest(identifier=identifier)
       