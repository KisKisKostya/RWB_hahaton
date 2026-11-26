"""Formula + capacity checks from .cursorrules."""
from app.capacity import capacity_ok
from app.tariffs import (
    ASSEMBLY_FEE,
    COMMISSION_RATE,
    HUB_BASE,
    HUB_PER_KM,
    HUB_PROCESSING,
    LOCAL_BASE,
    LOCAL_BONUS,
    LOCAL_PER_KM,
    INTAKE_FEE,
    STORAGE_PER_UNIT_DAY,
    hub_cost,
    local_cost,
    marketplace_margin,
    pvz_income_local,
    seller_payout,
    storage_fee,
)


def test_storage_fee():
    # ceil(2.1) * 5.0 * 3 = 3 * 5 * 3 = 45
    assert storage_fee(2.1, 3) == 45.0
    assert storage_fee(0.1, 1) == STORAGE_PER_UNIT_DAY


def test_local_cost():
    dist = 10.0
    assert local_cost(dist) == LOCAL_BASE + LOCAL_PER_KM * dist + ASSEMBLY_FEE


def test_hub_cost():
    dist = 800.0
    assert hub_cost(dist) == HUB_BASE + HUB_PER_KM * dist + HUB_PROCESSING


def test_margin_and_payout():
    price, stor, dist, qty = 1000.0, 15.0, 10.0, 1
    cost = local_cost(dist)
    income = pvz_income_local(qty, stor)
    assert income == INTAKE_FEE * qty + stor + ASSEMBLY_FEE + LOCAL_BONUS
    assert marketplace_margin(price, cost, income) == (
        COMMISSION_RATE * price - cost - income
    )
    assert seller_payout(price, stor) == price - COMMISSION_RATE * price - stor


def test_capacity_ok():
    # usable = 100 * 0.8 = 80; occupied+incoming = 70 <= 80
    assert capacity_ok(occupied=50, incoming=20, capacity_units=100) is True


def test_capacity_no_capacity():
    # usable = 100 * 0.8 = 80; occupied+incoming = 81 > 80
    assert capacity_ok(occupied=70, incoming=11, capacity_units=100) is False
