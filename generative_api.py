"""Generative Phase GET API for Field Audit."""

import datetime
import decimal
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Query

GENERATIVE_COLUMNS = [
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
    "co_detasseling",
    "gen1_audit_date",
    "gen1_audit_week",
    "gen1_readiness_status",
    "gen1_roguing_status",
    "gen1_lsv_status",
    "gen1_crop_uniformity",
    "gen1_crop_health",
    "gen1_action_needed",
    "gen1_remarks",
    "gen2_audit_date",
    "gen2_audit_week",
    "gen2_roguing_status",
    "gen2_female_shedding",
    "gen2_offtype_m",
    "gen2_offtype_f",
    "gen2_lsv_status",
    "gen2_crop_uniformity",
    "gen2_crop_health",
    "gen2_action_needed",
    "gen2_remarks",
    "gen3_audit_date",
    "gen3_audit_week",
    "gen3_female_shedding",
    "gen3_offtype_m",
    "gen3_offtype_f",
    "gen3_lsv_status",
    "gen3_crop_uniformity",
    "gen3_crop_health",
    "gen3_detasseling_assessment",
    "gen3_isolation_status",
    "gen3_affected_other_field",
    "gen3_closed_out_date",
    "gen3_flagging",
    "gen3_final_decision",
    "gen3_discard_area_ha",
    "gen3_discard_reason",
    "gen3_action_needed",
    "gen3_remarks",
    "gen4_audit_date",
    "gen4_audit_week",
    "gen4_female_shedding",
    "gen4_offtype_m",
    "gen4_offtype_f",
    "gen4_roguing_status",
    "gen4_lsv_status",
    "gen4_crop_uniformity",
    "gen4_crop_health",
    "gen4_action_needed",
    "gen4_remarks",
    "gen5_audit_date",
    "gen5_audit_week",
    "gen5_female_shedding",
    "gen5_offtype_m",
    "gen5_offtype_f",
    "gen5_lsv_status",
    "gen5_crop_uniformity",
    "gen5_crop_health",
    "gen5_detasseling_assessment",
    "gen5_isolation_problem",
    "gen5_affected_other_field",
    "gen5_closed_out_date",
    "gen5_final_flagging",
    "gen5_final_decision",
    "gen5_pld_area_ha",
    "gen5_pld_reason",
    "gen5_remarks",
]

_RUN_QUERY_FN: Callable[..., Any] | None = None
_GET_TABLE_NAME_FN: Callable[[], str] | None = None

def init_generative_api(
    run_query_fn: Callable[..., Any],
    get_table_name_fn: Callable[[], str],
) -> None:
    """Initialize database query executor and table name getter."""
    global _RUN_QUERY_FN, _GET_TABLE_NAME_FN
    _RUN_QUERY_FN = run_query_fn
    _GET_TABLE_NAME_FN = get_table_name_fn

def _get_executor() -> tuple[Callable[..., Any], str]:
    if _RUN_QUERY_FN is None or _GET_TABLE_NAME_FN is None:
        raise HTTPException(status_code=503, detail="Generative API database is not configured")
    return _RUN_QUERY_FN, _GET_TABLE_NAME_FN() 

def format_generative_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Format and serialize a database row into the 50-field generative schema."""
    if not row:
        return row
    result: dict[str, Any] = {}
    for col in GENERATIVE_COLUMNS:
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

def query_generative_items(
    limit: Any = 100,
    offset: Any = 0,
    filters_dict: dict[str, Any] | None = None,
    run_query_fn: Callable[..., Any] | None = None,
    table_name: str | None = None,
) -> dict[str, Any]:
    """Query MySQL database for generative phase items with filtering and pagination."""
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
    columns_sql = ", ".join(f"`{col}`" for col in GENERATIVE_COLUMNS)

    total_rows = run_query_fn(
        f"SELECT COUNT(*) AS total FROM {table}{where_clause}", tuple(values), fetch_one=True
    )
    raw_items = run_query_fn(
        f"SELECT {columns_sql} FROM {table}{where_clause} ORDER BY `id` DESC LIMIT %s OFFSET %s",
        tuple(values + [limit_val, offset_val]),
    )
    items = [format_generative_row(item) for item in (raw_items or [])]
    total_count = total_rows["total"] if total_rows and "total" in total_rows else 0
    return {"items": items, "total": total_count, "limit": limit_val, "offset": offset_val}

def fetch_field_audit_generative(
    identifier: str,
    run_query_fn: Callable[..., Any] | None = None,
    table_name: str | None = None,
) -> dict[str, Any]:
    """Fetch a single generative phase record by database row ID or field_number."""
    if run_query_fn is None or table_name is None:
        default_run_query, default_table = _get_executor()
        run_query_fn = run_query_fn or default_run_query
        table_name = table_name or default_table

    columns_sql = ", ".join(f"`{col}`" for col in GENERATIVE_COLUMNS)
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
        raise HTTPException(status_code=404, detail="Field audit generative row not found")
    return format_generative_row(row)


router = APIRouter(tags=["Generative Phase"])

@router.get("/api/field-audit/generative")
@router.get("/api/field-audit/fase-generative")
def list_field_audit_generative(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    season: str | None = None,
    field_number: str | None = None,
    farmer_name: str | None = None,
):
    return query_generative_items(
        limit=limit,
        offset=offset,
        filters_dict={
            "season": season,
            "field_number": field_number,
            "farmer_name": farmer_name,
        },
    )    

@router.get("/api/field-audit/generative/{identifier}")
@router.get("/api/field-audit/fase-generative/{identifier}")
def get_field_audit_generative(identifier: str):
    return fetch_field_audit_generative(identifier=identifier)
