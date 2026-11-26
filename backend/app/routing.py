"""Routing: build_local, build_hub, select_route (.cursorrules)."""
from typing import Any, Optional

from app.capacity import capacity_ok
from app.tariffs import (
    hub_cost as calc_hub_cost,
    local_cost as calc_local_cost,
    marketplace_margin,
    pvz_income_hub,
    pvz_income_local,
    seller_payout,
)


def marketplace_cost(route_cost: float, pvz_income: float) -> float:
    """Затраты маркетплейса на маршрут = route_cost + pvz_income."""
    return route_cost + pvz_income


def build_hub(
    *,
    dist: float,
    eta_days: float,
    price: float,
    qty: int = 1,
    storage_fee: float = 0.0,
    source_pvz_id: Optional[int] = None,
    hub_available: bool = True,
) -> dict[str, Any]:
    """Собрать hub RouteOption. reject_reason заполняется всегда при infeasible."""
    cost = calc_hub_cost(dist)
    income = pvz_income_hub(qty, storage_fee)
    total_price = price * qty
    margin = marketplace_margin(total_price, cost, income)
    payout = seller_payout(total_price, storage_fee)

    feasible = True
    reject_reason: Optional[str] = None
    if not hub_available:
        feasible = False
        reject_reason = "no_hub"

    return {
        "type": "hub",
        "cost": round(cost, 2),
        "eta_days": round(eta_days, 2),
        "distance_km": round(dist, 2),
        "pvz_income": round(income, 2),
        "marketplace_margin": round(margin, 2),
        "marketplace_cost": round(marketplace_cost(cost, income), 2),
        "seller_payout": round(payout, 2),
        "feasible": feasible,
        "reject_reason": reject_reason,
        "source_pvz_id": source_pvz_id,
    }


def build_local(
    *,
    dist: float,
    eta_days: float,
    price: float,
    qty: int = 1,
    storage_fee: float = 0.0,
    top_flag: bool,
    occupied: int,
    incoming: int,
    capacity_units: int,
    reserve_pct: float = 0.20,
    hub_eta: float,
    hub_marketplace_cost: float,
    source_pvz_id: Optional[int] = None,
    has_stock: bool = True,
) -> dict[str, Any]:
    """
    Собрать local RouteOption.
    routing_local_feasible:
      - top_flag == true
      - capacity_ok
      - eta_local <= eta_hub - 0.5
      - marketplace_cost_local <= marketplace_cost_hub
      - иначе reject_reason
    """
    cost = calc_local_cost(dist)
    income = pvz_income_local(qty, storage_fee)
    total_price = price * qty
    margin = marketplace_margin(total_price, cost, income)
    payout = seller_payout(total_price, storage_fee)
    mkt_cost = marketplace_cost(cost, income)

    feasible = True
    reject_reason: Optional[str] = None

    if not has_stock:
        feasible = False
        reject_reason = "no_local_top_stock"
    elif not top_flag:
        feasible = False
        reject_reason = "top_flag_false"
    elif not capacity_ok(occupied, incoming, capacity_units, reserve_pct):
        feasible = False
        reject_reason = "no_capacity"
    elif eta_days > hub_eta - 0.5:
        feasible = False
        reject_reason = "eta_local_worse_than_hub"
    elif mkt_cost > hub_marketplace_cost:
        feasible = False
        reject_reason = "marketplace_cost_local_worse"

    return {
        "type": "local",
        "cost": round(cost, 2),
        "eta_days": round(eta_days, 2),
        "distance_km": round(dist, 2),
        "pvz_income": round(income, 2),
        "marketplace_margin": round(margin, 2),
        "marketplace_cost": round(mkt_cost, 2),
        "seller_payout": round(payout, 2),
        "feasible": feasible,
        "reject_reason": reject_reason,
        "source_pvz_id": source_pvz_id,
    }


def select_route(local: dict[str, Any], hub: dict[str, Any]) -> dict[str, Any]:
    """Выбрать feasible local, иначе hub. Если оба нет — ValueError + причины."""
    if local.get("feasible"):
        return local
    if hub.get("feasible"):
        return hub
    raise ValueError(
        f"no_feasible_route local={local.get('reject_reason')} hub={hub.get('reject_reason')}"
    )
