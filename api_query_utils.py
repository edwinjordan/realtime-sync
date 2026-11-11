import re
from typing import Any

from fastapi import HTTPException


_COLUMN_NAME_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")

NON_PLD_FLAGGING_FILTER = "`flagging_final` <> %s"
PLD_FLAGGING_VALUE = "PLD"


def build_order_clause(order_by: Any = "id", order: Any = "desc") -> str:
    """Build a safe ORDER BY clause from a column name and sort direction."""
    order_by = getattr(order_by, "default", order_by)
    order = getattr(order, "default", order)

    if not isinstance(order_by, str) or not _COLUMN_NAME_PATTERN.fullmatch(order_by):
        raise HTTPException(
            status_code=422,
            detail="order_by must be a valid column name",
        )
    if not isinstance(order, str) or order.upper() not in ("ASC", "DESC"):
        raise HTTPException(
            status_code=422,
            detail="order must be either 'asc' or 'desc'",
        )

    return f"ORDER BY `{order_by}` {order.upper()}"
