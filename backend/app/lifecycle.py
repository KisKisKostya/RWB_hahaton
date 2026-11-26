"""Order / StockItem status transitions. Illegal → KeyError."""
from typing import Optional

from app.accruals import make_status_accrual

# Order: CREATED → … → ISSUED | CANCELLED | RETURNED | FAILED_ROUTE
ORDER_TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"ROUTE_SELECTED", "CANCELLED", "FAILED_ROUTE"},
    "ROUTE_SELECTED": {"RESERVED", "CANCELLED", "FAILED_ROUTE"},
    "RESERVED": {"ASSEMBLED", "CANCELLED", "FAILED_ROUTE"},
    "ASSEMBLED": {"IN_TRANSIT", "CANCELLED", "FAILED_ROUTE"},
    "IN_TRANSIT": {"READY", "ISSUED", "CANCELLED", "FAILED_ROUTE"},
    "READY": {"ISSUED", "RETURNED", "CANCELLED"},
    "ISSUED": {"RETURNED"},
    "CANCELLED": set(),
    "RETURNED": set(),
    "FAILED_ROUTE": set(),
}

# StockItem statuses from .cursorrules
STOCK_TRANSITIONS: dict[str, set[str]] = {
    "ACCEPTED": {"STORED"},
    "STORED": {"RESERVED", "RELOCATED", "EXPIRED", "TO_HUB", "TO_SELLER"},
    "RESERVED": {"ASSEMBLED", "STORED"},
    "ASSEMBLED": {"ISSUED", "RESERVED"},
    "ISSUED": {"RETURNED", "STORED", "DAMAGED", "RELOCATED"},
    "RETURNED": {"STORED", "RELOCATED", "TO_SELLER", "DAMAGED"},
    "RELOCATED": {"STORED", "TO_HUB", "ACCEPTED"},
    "TO_HUB": {"STORED", "ACCEPTED"},
    "TO_SELLER": set(),
    "EXPIRED": {"TO_SELLER"},
    "DAMAGED": {"TO_SELLER"},
}


def transition_order(current: str, new: str) -> str:
    """Разрешённый переход Order. Нелегальный → KeyError."""
    allowed = ORDER_TRANSITIONS[current]  # KeyError if unknown status
    if new not in allowed:
        raise KeyError(f"illegal order transition: {current} -> {new}")
    return new


def transition_stock(
    current: str,
    new: str,
    *,
    pvz_id: Optional[int] = None,
    stock_item_id: Optional[int] = None,
    order_id: Optional[int] = None,
    amount: float = 0.0,
) -> tuple[str, Optional[dict]]:
    """
    Разрешённый переход StockItem. Нелегальный → KeyError.
    Каждое изменение статуса пишет Accrual (dict payload).
    """
    allowed = STOCK_TRANSITIONS[current]  # KeyError if unknown status
    if new not in allowed:
        raise KeyError(f"illegal stock transition: {current} -> {new}")
    accrual = None
    if pvz_id is not None:
        accrual = make_status_accrual(
            pvz_id=pvz_id,
            new_status=new,
            amount=amount,
            stock_item_id=stock_item_id,
            order_id=order_id,
        )
    return new, accrual


def can_transition_order(current: str, new: str) -> bool:
    return new in ORDER_TRANSITIONS.get(current, set())


def can_transition_stock(current: str, new: str) -> bool:
    return new in STOCK_TRANSITIONS.get(current, set())
