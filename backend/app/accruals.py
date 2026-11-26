"""Accrual payloads — каждое изменение StockItem пишет Accrual."""
from typing import Optional

from app.tariffs import ASSEMBLY_FEE, INTAKE_FEE, LOCAL_BONUS


def make_accrual(
    *,
    pvz_id: int,
    accrual_type: str,
    amount: float,
    order_id: Optional[int] = None,
    stock_item_id: Optional[int] = None,
) -> dict:
    return {
        "pvz_id": pvz_id,
        "order_id": order_id,
        "stock_item_id": stock_item_id,
        "type": accrual_type,
        "amount": round(amount, 2),
    }


def make_status_accrual(
    *,
    pvz_id: int,
    new_status: str,
    amount: float = 0.0,
    order_id: Optional[int] = None,
    stock_item_id: Optional[int] = None,
) -> dict:
    """Accrual на смену статуса StockItem: type=status:<STATUS>."""
    return make_accrual(
        pvz_id=pvz_id,
        accrual_type=f"status:{new_status}",
        amount=amount,
        order_id=order_id,
        stock_item_id=stock_item_id,
    )


def make_intake_accrual(*, pvz_id: int, qty: int, stock_item_id: Optional[int] = None) -> dict:
    return make_accrual(
        pvz_id=pvz_id,
        accrual_type="intake",
        amount=INTAKE_FEE * qty,
        stock_item_id=stock_item_id,
    )


def make_assembly_accrual(
    *,
    pvz_id: int,
    order_id: Optional[int] = None,
    stock_item_id: Optional[int] = None,
) -> dict:
    return make_accrual(
        pvz_id=pvz_id,
        accrual_type="assembly",
        amount=ASSEMBLY_FEE,
        order_id=order_id,
        stock_item_id=stock_item_id,
    )


def make_local_bonus_accrual(
    *,
    pvz_id: int,
    order_id: Optional[int] = None,
) -> dict:
    return make_accrual(
        pvz_id=pvz_id,
        accrual_type="local_bonus",
        amount=LOCAL_BONUS,
        order_id=order_id,
    )


def make_pvz_income_accrual(
    *,
    pvz_id: int,
    amount: float,
    order_id: Optional[int] = None,
) -> dict:
    return make_accrual(
        pvz_id=pvz_id,
        accrual_type="pvz_income",
        amount=amount,
        order_id=order_id,
    )
