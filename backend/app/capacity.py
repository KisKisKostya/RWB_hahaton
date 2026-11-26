"""Capacity checks from .cursorrules."""
from app.tariffs import RESERVE_PCT


def usable_capacity(capacity_units: int, reserve_pct: float = RESERVE_PCT) -> float:
    """capacity_units * (1 - RESERVE_PCT)"""
    return capacity_units * (1 - reserve_pct)


def capacity_ok(
    occupied: int,
    incoming: int,
    capacity_units: int,
    reserve_pct: float = RESERVE_PCT,
) -> bool:
    """occupied + incoming <= capacity_units*(1-RESERVE_PCT)"""
    return occupied + incoming <= usable_capacity(capacity_units, reserve_pct)
