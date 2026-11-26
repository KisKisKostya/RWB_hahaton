"""Tariffs and formulas from .cursorrules."""
import math

STORAGE_PER_UNIT_DAY = 5.0
INTAKE_FEE = 15.0
ASSEMBLY_FEE = 20.0
LOCAL_BASE = 80.0
LOCAL_PER_KM = 6.0
HUB_BASE = 120.0
HUB_PER_KM = 3.5
HUB_PROCESSING = 40.0
COMMISSION_RATE = 0.15
LOCAL_BONUS = 10.0
TTL_COEF = 1.5
TTL_MIN = 2
TTL_MAX = 14
TOP_RECHECK_DAYS = 5
RESERVE_PCT = 0.20


def storage_fee(days_stored: float, qty: int, rate: float = STORAGE_PER_UNIT_DAY) -> float:
    """ceil(days_stored) * STORAGE_PER_UNIT_DAY * qty"""
    return math.ceil(days_stored) * rate * qty


def local_cost(dist: float) -> float:
    """LOCAL_BASE + LOCAL_PER_KM*dist + ASSEMBLY_FEE"""
    return LOCAL_BASE + LOCAL_PER_KM * dist + ASSEMBLY_FEE


def hub_cost(dist: float) -> float:
    """HUB_BASE + HUB_PER_KM*dist + HUB_PROCESSING"""
    return HUB_BASE + HUB_PER_KM * dist + HUB_PROCESSING


def pvz_income_local(qty: int, stor: float) -> float:
    """INTAKE_FEE*qty + storage_fee + ASSEMBLY_FEE + LOCAL_BONUS"""
    return INTAKE_FEE * qty + stor + ASSEMBLY_FEE + LOCAL_BONUS


def pvz_income_hub(qty: int, stor: float) -> float:
    """INTAKE_FEE*qty + storage_fee + ASSEMBLY_FEE"""
    return INTAKE_FEE * qty + stor + ASSEMBLY_FEE


def marketplace_margin(price: float, route_cost: float, pvz_income: float) -> float:
    """COMMISSION_RATE*price - route_cost - pvz_income"""
    return COMMISSION_RATE * price - route_cost - pvz_income


def seller_payout(price: float, stor: float) -> float:
    """price - COMMISSION_RATE*price - storage_fee"""
    return price - COMMISSION_RATE * price - stor


def ttl_days(avg_interval: float) -> int:
    """clamp(round(avg_interval*TTL_COEF), TTL_MIN, TTL_MAX)"""
    return max(TTL_MIN, min(TTL_MAX, round(avg_interval * TTL_COEF)))
