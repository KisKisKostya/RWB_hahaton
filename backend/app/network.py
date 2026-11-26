"""Network, demand forecasting, vehicle routes and customer-facing endpoints."""

import heapq
import math
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models import (
    Accrual,
    CapacityReservation,
    Customer,
    InventoryTransfer,
    Order,
    Product,
    PVZ,
    RoadEdge,
    SessionLocal,
    StockItem,
    TruckRoute,
    TruckRouteStop,
    WeeklyDemand,
    get_db,
    utcnow,
)

router = APIRouter(tags=["network", "demand", "customer"])

AVAILABLE_STOCK = ("ACCEPTED", "STORED")
ACTIVE_STOCK = ("ACCEPTED", "STORED", "RESERVED", "ASSEMBLED")
OCCUPIED_STOCK = (*ACTIVE_STOCK, "IN_TRANSFER", "RETURNED", "DAMAGED")
TRANSFER_PENDING = ("WAITING_ROUTE", "READY_ON_ROUTE")
MAX_PVZ_ITEM_VOLUME_M3 = 0.08
CATEGORY_MAX_VOLUME_M3 = {
    "одежда": 0.025,
    "электроника": 0.06,
    "дом": 0.08,
    "красота": 0.02,
    "спорт": 0.06,
}
DEFAULT_LEAD_TIME_DAYS = 2
DEFAULT_SAFETY_DAYS = 1


class PVZCreate(BaseModel):
    city: str = Field(min_length=2, max_length=100)
    address: str = Field(min_length=3, max_length=250)
    is_hub: bool = False
    is_mesh_enabled: bool = True
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    storage_area_m2: float = Field(default=20, gt=0, le=100000)
    storage_height_m: float = Field(default=2, gt=0, le=20)
    capacity_units: int = Field(default=100, ge=1, le=1000000)
    reserve_pct: float = Field(default=0.2, ge=0, le=0.9)


class PVZUpdate(BaseModel):
    city: Optional[str] = None
    address: Optional[str] = None
    is_hub: Optional[bool] = None
    is_mesh_enabled: Optional[bool] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    storage_area_m2: Optional[float] = Field(default=None, gt=0, le=100000)
    storage_height_m: Optional[float] = Field(default=None, gt=0, le=20)
    capacity_units: Optional[int] = Field(default=None, ge=1, le=1000000)
    reserve_pct: Optional[float] = Field(default=None, ge=0, le=0.9)


class DemandLine(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=0)


class DemandBatch(BaseModel):
    week_start: Optional[datetime] = None
    rows: list[DemandLine] = Field(min_length=1, max_length=1000)


class RoadEdgeCreate(BaseModel):
    from_pvz_id: int
    to_pvz_id: int
    distance_km: float = Field(gt=0, le=10000)
    bidirectional: bool = True


class TruckRouteCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    stop_pvz_ids: list[int] = Field(min_length=2, max_length=100)
    is_active: bool = True


class ProductDimensionsUpdate(BaseModel):
    length_cm: float = Field(gt=0, le=2000)
    width_cm: float = Field(gt=0, le=2000)
    height_cm: float = Field(gt=0, le=2000)


class SellerIntake(BaseModel):
    product_id: int
    qty: int = Field(ge=1)
    origin_pvz_id: Optional[int] = None


class CustomerProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=40)
    email: Optional[str] = Field(default=None, max_length=160)
    city: Optional[str] = Field(default=None, max_length=100)
    preferred_pvz_id: Optional[int] = None


class CustomerOrderCreate(BaseModel):
    product_id: int
    qty: int = Field(default=1, ge=1)
    buyer_pvz_id: int


def _pvz_label(pvz: PVZ) -> str:
    return f"{pvz.city}, {pvz.address}"


def _coords(pvz: PVZ) -> tuple[float, float]:
    centers = {
        "Казань": (55.796, 49.106),
        "Москва": (55.7558, 37.6173),
        "Йошкар-Ола": (56.6388, 47.8908),
    }
    center = centers.get(pvz.city, (55.75, 37.61))
    # Older demo records did not store coordinates. Give them stable map positions
    # around their city center until an operator pins the exact location.
    offset = (pvz.id % 7) * 0.006
    return (
        float(pvz.latitude if pvz.latitude is not None else center[0] + offset),
        float(pvz.longitude if pvz.longitude is not None else center[1] + offset * 1.4),
    )


def category_volume_limit(product: Product) -> float:
    return CATEGORY_MAX_VOLUME_M3.get((product.category or "").strip().lower(), MAX_PVZ_ITEM_VOLUME_M3)


def _volume_m3(product: Product) -> float:
    return max(
        (float(product.length_cm or 10) * float(product.width_cm or 10) * float(product.height_cm or 10)) / 1_000_000,
        0.000001,
    )


def _occupied_volume(db: Session, pvz_id: int) -> float:
    rows = (
        db.query(StockItem, Product)
        .join(Product, Product.id == StockItem.product_id)
        .filter(StockItem.pvz_id == pvz_id, StockItem.status.in_(OCCUPIED_STOCK))
        .all()
    )
    return sum(_volume_m3(product) * item.qty for item, product in rows)


def _storage_capacity(pvz: PVZ) -> float:
    return max(float(pvz.storage_area_m2 or 0) * float(pvz.storage_height_m or 0), 0)


def _build_adjacency(db: Session) -> dict[int, list[tuple[int, float]]]:
    adjacency: dict[int, list[tuple[int, float]]] = {}
    edges = db.query(RoadEdge).filter(RoadEdge.is_active.is_(True)).all()
    for edge in edges:
        adjacency.setdefault(edge.from_pvz_id, []).append((edge.to_pvz_id, edge.distance_km))
        if edge.bidirectional:
            adjacency.setdefault(edge.to_pvz_id, []).append((edge.from_pvz_id, edge.distance_km))
    return adjacency


def shortest_path(db: Session, start_id: int, finish_id: int) -> tuple[list[int], Optional[float]]:
    if start_id == finish_id:
        return [start_id], 0.0
    adjacency = _build_adjacency(db)
    distances = {start_id: 0.0}
    previous: dict[int, int] = {}
    queue: list[tuple[float, int]] = [(0.0, start_id)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances.get(node):
            continue
        if node == finish_id:
            break
        for neighbor, weight in adjacency.get(node, []):
            candidate = distance + weight
            if candidate < distances.get(neighbor, float("inf")):
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))
    if finish_id not in distances:
        return [], None
    path = [finish_id]
    while path[-1] != start_id:
        path.append(previous[path[-1]])
    path.reverse()
    return path, distances[finish_id]


def _route_distance(db: Session, stop_ids: list[int]) -> Optional[float]:
    distance = 0.0
    for start, end in zip(stop_ids, stop_ids[1:]):
        _, leg = shortest_path(db, start, end)
        if leg is None:
            return None
        distance += leg
    return distance


def _route_for_transfer(db: Session, from_id: int, to_id: int) -> tuple[Optional[int], Optional[float]]:
    endpoints = db.query(PVZ).filter(PVZ.id.in_([from_id, to_id])).all()
    if len(endpoints) != 2 or any(not location.is_mesh_enabled for location in endpoints):
        return None, None
    routes = db.query(TruckRoute).filter(TruckRoute.is_active.is_(True)).all()
    choices: list[tuple[float, int]] = []
    for route in routes:
        stops = (
            db.query(TruckRouteStop)
            .filter(TruckRouteStop.route_id == route.id)
            .order_by(TruckRouteStop.sequence_no)
            .all()
        )
        ids = [stop.pvz_id for stop in stops]
        if from_id not in ids or to_id not in ids:
            continue
        if ids.index(from_id) >= ids.index(to_id):
            continue
        segment = ids[ids.index(from_id): ids.index(to_id) + 1]
        distance = _route_distance(db, segment)
        if distance is not None:
            choices.append((distance, route.id))
    if not choices:
        return None, None
    distance, route_id = min(choices)
    return route_id, distance

def _demand_totals(db: Session, pvz_id: int, days: int = 28) -> tuple[dict[int, int], int]:
    cutoff = utcnow() - timedelta(days=days)
    records = db.query(WeeklyDemand).filter(
        WeeklyDemand.pvz_id == pvz_id,
        WeeklyDemand.week_start >= cutoff,
    ).all()
    totals: dict[int, int] = {}
    weeks = set()
    for record in records:
        totals[record.product_id] = totals.get(record.product_id, 0) + record.quantity
        weeks.add(record.week_start.date())
    return totals, max(len(weeks), 1)


def calculate_assortment(db: Session, pvz: PVZ, sync_flags: bool = False) -> dict:
    demand, weeks = _demand_totals(db, pvz.id)
    capacity = _storage_capacity(pvz)
    occupied = _occupied_volume(db, pvz.id)
    free = max(capacity - occupied, 0.0)
    candidates = []
    for product_id, total in demand.items():
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product or total <= 0:
            continue
        volume = _volume_m3(product)
        weekly_average = total / weeks
        target = max(1, math.ceil((weekly_average / 7) * (DEFAULT_LEAD_TIME_DAYS + DEFAULT_SAFETY_DAYS)))
        current_rows = db.query(StockItem).filter(
            StockItem.pvz_id == pvz.id,
            StockItem.product_id == product.id,
            StockItem.status.in_(AVAILABLE_STOCK),
        ).all()
        current_qty = sum(item.qty for item in current_rows)
        remaining_need = max(target - current_qty, 0)
        possible = math.floor(free / volume) if volume > 0 else 0
        max_category_volume = category_volume_limit(product)
        size_ok = volume <= max_category_volume
        if not size_ok:
            possible = 0
        replenishment_qty = max(0, min(remaining_need, possible))
        candidates.append({
            "product_id": product.id,
            "name": product.name,
            "sku": product.sku,
            "category": product.category,
            "weekly_demand": round(weekly_average, 2),
            "total_sold": total,
            "volume_m3": round(volume, 4),
            "dimensions_cm": {
                "length": product.length_cm,
                "width": product.width_cm,
                "height": product.height_cm,
            },
            "current_qty": current_qty,
            "recommended_qty": target,
            "remaining_need_qty": remaining_need,
            "allocatable_qty": replenishment_qty,
            "eligible_size": size_ok,
            "excluded_reason": (
                "Крупногабаритный товар: превышен лимит объёма для категории"
                if not size_ok
                else "Недостаточно свободного объёма для пополнения"
                if replenishment_qty < remaining_need
                else None
            ),
        })
    candidates.sort(key=lambda row: (row["weekly_demand"], row["total_sold"]), reverse=True)

    # The TOP is recalculated from sales, dimensions and the remaining storage
    # volume. The system picks no more than five products for each PVZ.
    selected = []
    reserved_volume = 0.0
    selected_ids = set()
    for row in candidates:
        if len(selected) >= 5:
            break
        if not row["eligible_size"] or (row["current_qty"] <= 0 and row["allocatable_qty"] <= 0):
            continue
        row_volume = row["allocatable_qty"] * row["volume_m3"]
        if reserved_volume + row_volume > free:
            row["allocatable_qty"] = max(0, math.floor((free - reserved_volume) / row["volume_m3"]))
            row["excluded_reason"] = "Недостаточно свободного объёма для пополнения"
            if row["allocatable_qty"] <= 0:
                continue
            row_volume = row["allocatable_qty"] * row["volume_m3"]
        reserved_volume += row_volume
        row["rank"] = len(selected) + 1
        selected.append(row)
        selected_ids.add(row["product_id"])

    if sync_flags:
        stocks = db.query(StockItem).filter(
            StockItem.pvz_id == pvz.id,
            StockItem.status.in_(AVAILABLE_STOCK),
        ).all()
        for item in stocks:
            item.top_flag = item.product_id in selected_ids
            item.last_top_check = utcnow()
        db.flush()

    return {
        "pvz_id": pvz.id,
        "storage_capacity_m3": round(capacity, 3),
        "occupied_volume_m3": round(occupied, 3),
        "free_volume_m3": round(free, 3),
        "top_products": selected,
        "candidates": candidates,
        "calculated_at": utcnow().isoformat(),
        "policy": {
            "top_limit": 5,
            "lead_time_days": DEFAULT_LEAD_TIME_DAYS,
            "safety_days": DEFAULT_SAFETY_DAYS,
            "max_item_volume_m3": MAX_PVZ_ITEM_VOLUME_M3,
            "category_volume_limits_m3": CATEGORY_MAX_VOLUME_M3,
        },
    }


def _create_transfer(
    db: Session,
    product_id: int,
    qty: int,
    from_id: int,
    to_id: int,
    reason: str,
) -> Optional[InventoryTransfer]:
    if qty <= 0 or from_id == to_id:
        return None

    available_rows = db.query(StockItem).filter(
        StockItem.product_id == product_id,
        StockItem.pvz_id == from_id,
        StockItem.status.in_(("STORED", "RETURNED")),
        StockItem.qty > 0,
    ).order_by(StockItem.accepted_at).all()
    if sum(row.qty for row in available_rows) < qty:
        return None

    route_id, distance = _route_for_transfer(db, from_id, to_id)
    transfer = InventoryTransfer(
        product_id=product_id,
        qty=qty,
        from_pvz_id=from_id,
        to_pvz_id=to_id,
        route_id=route_id,
        status="READY_ON_ROUTE" if route_id else "WAITING_ROUTE",
        distance_km=distance,
        reason=reason,
    )
    db.add(transfer)
    db.flush()

    remaining = qty
    for row in available_rows:
        taken = min(row.qty, remaining)
        if taken == row.qty:
            row.status = "IN_TRANSFER"
            row.transfer_id = transfer.id
        else:
            row.qty -= taken
            db.add(StockItem(
                product_id=row.product_id,
                pvz_id=row.pvz_id,
                qty=taken,
                status="IN_TRANSFER",
                accepted_at=row.accepted_at,
                ttl_days=row.ttl_days,
                storage_deadline=row.storage_deadline,
                top_flag=False,
                last_top_check=utcnow(),
                transfer_id=transfer.id,
            ))
        remaining -= taken
        if remaining <= 0:
            break

    db.flush()
    return transfer

def plan_rebalancing(db: Session) -> list[InventoryTransfer]:
    locations = db.query(PVZ).filter(PVZ.is_mesh_enabled.is_(True)).all()
    assortments = {
        location.id: calculate_assortment(db, location, sync_flags=True)
        for location in locations
    }
    plans = []
    for source in locations:
        items = db.query(StockItem).filter(
            StockItem.pvz_id == source.id,
            StockItem.status == "STORED",
            StockItem.qty > 0,
        ).all()
        processed_products: set[int] = set()
        for item in items:
            if item.product_id in processed_products:
                continue
            processed_products.add(item.product_id)

            pending_outbound = db.query(InventoryTransfer).filter(
                InventoryTransfer.product_id == item.product_id,
                InventoryTransfer.from_pvz_id == source.id,
                InventoryTransfer.status.in_(TRANSFER_PENDING),
            ).first()
            if pending_outbound:
                continue

            source_top_ids = {
                row["product_id"] for row in assortments[source.id]["top_products"]
            }
            if item.product_id in source_top_ids:
                continue

            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product:
                continue
            source_qty = sum(
                row.qty for row in db.query(StockItem).filter(
                    StockItem.pvz_id == source.id,
                    StockItem.product_id == product.id,
                    StockItem.status == "STORED",
                ).all()
            )
            if source_qty <= 0:
                continue

            receiving = []
            for target in locations:
                if target.id == source.id:
                    continue
                desired = next(
                    (
                        row for row in assortments[target.id]["top_products"]
                        if row["product_id"] == product.id
                    ),
                    None,
                )
                if not desired:
                    continue

                current = sum(
                    row.qty for row in db.query(StockItem).filter(
                        StockItem.pvz_id == target.id,
                        StockItem.product_id == product.id,
                        StockItem.status.in_(AVAILABLE_STOCK),
                    ).all()
                )
                planned_incoming = sum(
                    row.qty for row in db.query(InventoryTransfer).filter(
                        InventoryTransfer.product_id == product.id,
                        InventoryTransfer.to_pvz_id == target.id,
                        InventoryTransfer.status.in_(TRANSFER_PENDING),
                    ).all()
                )
                deficit = max(desired["recommended_qty"] - current - planned_incoming, 0)
                if deficit:
                    receiving.append((desired["weekly_demand"], target.id, deficit))

            if receiving:
                _, target_id, deficit = max(receiving)
                transfer = _create_transfer(
                    db,
                    product.id,
                    min(source_qty, deficit),
                    source.id,
                    target_id,
                    "demand_rebalance",
                )
            else:
                if source.is_hub:
                    continue
                hubs = db.query(PVZ).filter(
                    PVZ.is_hub.is_(True),
                    PVZ.is_mesh_enabled.is_(True),
                    PVZ.id != source.id,
                ).all()
                hub_choices = []
                for hub in hubs:
                    hub_free = _storage_capacity(hub) - _occupied_volume(db, hub.id)
                    fit_qty = min(source_qty, max(0, math.floor(hub_free / _volume_m3(product))))
                    if fit_qty > 0:
                        hub_choices.append((hub_free, hub, fit_qty))
                if hub_choices:
                    _, hub, fit_qty = max(hub_choices, key=lambda row: row[0])
                    transfer = _create_transfer(
                        db, product.id, fit_qty, source.id, hub.id, "no_local_demand"
                    )
                else:
                    transfer = None
            if transfer:
                plans.append(transfer)
    db.flush()
    return plans

def _refresh_waiting_transfers(db: Session) -> None:
    pending = db.query(InventoryTransfer).filter(
        InventoryTransfer.status.in_(TRANSFER_PENDING)
    ).all()
    for transfer in pending:
        route_id, distance = _route_for_transfer(
            db, transfer.from_pvz_id, transfer.to_pvz_id
        )
        transfer.route_id = route_id
        transfer.distance_km = distance
        transfer.status = "READY_ON_ROUTE" if route_id else "WAITING_ROUTE"


@router.get("/network/map")
def network_map(db: Session = Depends(get_db)):
    locations = db.query(PVZ).order_by(PVZ.id).all()
    edges = db.query(RoadEdge).filter(RoadEdge.is_active.is_(True)).all()
    routes = db.query(TruckRoute).filter(TruckRoute.is_active.is_(True)).all()
    nodes = []
    for location in locations:
        lat, lon = _coords(location)
        nodes.append({
            "id": location.id,
            "city": location.city,
            "address": location.address,
            "label": f"{location.city} · {location.address}",
            "is_hub": location.is_hub,
            "is_mesh_enabled": location.is_mesh_enabled,
            "latitude": lat,
            "longitude": lon,
            "storage_area_m2": location.storage_area_m2,
            "storage_height_m": location.storage_height_m,
            "storage_capacity_m3": round(_storage_capacity(location), 3),
            "occupied_volume_m3": round(_occupied_volume(db, location.id), 3),
        })
    return {
        "locations": nodes,
        "edges": [{
            "id": edge.id,
            "from_pvz_id": edge.from_pvz_id,
            "to_pvz_id": edge.to_pvz_id,
            "distance_km": edge.distance_km,
            "bidirectional": edge.bidirectional,
        } for edge in edges],
        "routes": [{
            "id": route.id,
            "name": route.name,
            "stop_pvz_ids": [
                stop.pvz_id for stop in db.query(TruckRouteStop)
                .filter(TruckRouteStop.route_id == route.id)
                .order_by(TruckRouteStop.sequence_no).all()
            ],
        } for route in routes],
    }


@router.post("/network/pvz")
def create_pvz(body: PVZCreate, db: Session = Depends(get_db)):
    pvz = PVZ(**body.model_dump())
    db.add(pvz)
    db.commit()
    db.refresh(pvz)
    return {"id": pvz.id, "label": _pvz_label(pvz), "is_hub": pvz.is_hub}


@router.patch("/network/pvz/{pvz_id}")
def update_pvz(pvz_id: int, body: PVZUpdate, db: Session = Depends(get_db)):
    pvz = db.query(PVZ).filter(PVZ.id == pvz_id).first()
    if not pvz:
        raise HTTPException(404, "ПВЗ или склад не найден")
    changes = body.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(pvz, key, value)

    _refresh_waiting_transfers(db)
    for location in db.query(PVZ).filter(PVZ.is_mesh_enabled.is_(True)).all():
        calculate_assortment(db, location, sync_flags=True)
    plans = plan_rebalancing(db)
    db.commit()
    return {
        "id": pvz.id,
        "updated": list(changes.keys()),
        "rebalanced_transfers": [transfer.id for transfer in plans],
    }


@router.get("/network/edges")
def list_edges(db: Session = Depends(get_db)):
    return db.query(RoadEdge).filter(RoadEdge.is_active.is_(True)).all()


@router.post("/network/edges")
def create_edge(body: RoadEdgeCreate, db: Session = Depends(get_db)):
    if body.from_pvz_id == body.to_pvz_id:
        raise HTTPException(400, "Нельзя создать дорогу из пункта в него же")
    for location_id in (body.from_pvz_id, body.to_pvz_id):
        if not db.query(PVZ).filter(PVZ.id == location_id).first():
            raise HTTPException(404, f"Пункт {location_id} не найден")
    edge = RoadEdge(**body.model_dump())
    db.add(edge)
    db.commit()
    db.refresh(edge)
    _refresh_waiting_transfers(db)
    db.commit()
    return {"id": edge.id, "distance_km": edge.distance_km}


@router.delete("/network/edges/{edge_id}")
def delete_edge(edge_id: int, db: Session = Depends(get_db)):
    edge = db.query(RoadEdge).filter(RoadEdge.id == edge_id).first()
    if not edge:
        raise HTTPException(404, "Дорожное ребро не найдено")
    edge.is_active = False
    _refresh_waiting_transfers(db)
    db.commit()
    return {"deleted": edge_id}


@router.get("/network/shortest-path")
def get_shortest_path(
    from_pvz_id: int = Query(gt=0),
    to_pvz_id: int = Query(gt=0),
    db: Session = Depends(get_db),
):
    path, distance = shortest_path(db, from_pvz_id, to_pvz_id)
    if distance is None:
        raise HTTPException(404, "Между пунктами пока нет связанного дорожного маршрута")
    return {"path": path, "distance_km": round(distance, 2), "algorithm": "Dijkstra"}


@router.get("/network/routes")
def list_truck_routes(db: Session = Depends(get_db)):
    result = []
    for route in db.query(TruckRoute).order_by(TruckRoute.id.desc()).all():
        stops = db.query(TruckRouteStop).filter(
            TruckRouteStop.route_id == route.id
        ).order_by(TruckRouteStop.sequence_no).all()
        stop_ids = [stop.pvz_id for stop in stops]
        result.append({
            "id": route.id,
            "name": route.name,
            "is_active": route.is_active,
            "stop_pvz_ids": stop_ids,
            "distance_km": _route_distance(db, stop_ids) if len(stop_ids) > 1 else 0,
        })
    return result


@router.post("/network/routes")
def create_truck_route(body: TruckRouteCreate, db: Session = Depends(get_db)):
    if len(set(body.stop_pvz_ids)) != len(body.stop_pvz_ids):
        raise HTTPException(400, "Один и тот же пункт не должен повторяться в рейсе")
    locations = db.query(PVZ).filter(PVZ.id.in_(body.stop_pvz_ids)).all()
    if len(locations) != len(body.stop_pvz_ids):
        raise HTTPException(404, "Один из пунктов маршрута не найден")
    distance = _route_distance(db, body.stop_pvz_ids)
    if distance is None:
        raise HTTPException(409, "Маршрут нельзя построить: добавьте длину дорог между соседними пунктами")
    route = TruckRoute(name=body.name, is_active=body.is_active)
    db.add(route)
    db.flush()
    for order, pvz_id in enumerate(body.stop_pvz_ids):
        db.add(TruckRouteStop(route_id=route.id, pvz_id=pvz_id, sequence_no=order))
    db.flush()
    _refresh_waiting_transfers(db)
    db.commit()
    return {"id": route.id, "name": route.name, "distance_km": round(distance, 2)}


@router.patch("/network/routes/{route_id}/active")
def set_route_active(route_id: int, active: bool = Query(...), db: Session = Depends(get_db)):
    route = db.query(TruckRoute).filter(TruckRoute.id == route_id).first()
    if not route:
        raise HTTPException(404, "Рейс не найден")
    route.is_active = active
    _refresh_waiting_transfers(db)
    db.commit()
    return {"id": route.id, "is_active": route.is_active}


@router.post("/network/demand/{pvz_id}")
def upload_weekly_demand(pvz_id: int, body: DemandBatch, db: Session = Depends(get_db)):
    pvz = db.query(PVZ).filter(PVZ.id == pvz_id).first()
    if not pvz:
        raise HTTPException(404, "ПВЗ не найден")
    week_start = body.week_start or utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = week_start - timedelta(days=week_start.weekday())
    submitted_ids = {row.product_id for row in body.rows}
    for row in body.rows:
        if not db.query(Product).filter(Product.id == row.product_id).first():
            raise HTTPException(404, f"Товар {row.product_id} не найден")
        existing = db.query(WeeklyDemand).filter(
            WeeklyDemand.pvz_id == pvz_id,
            WeeklyDemand.product_id == row.product_id,
            WeeklyDemand.week_start == week_start,
        ).first()
        if existing:
            existing.quantity = row.quantity
        else:
            db.add(WeeklyDemand(
                pvz_id=pvz_id,
                product_id=row.product_id,
                week_start=week_start,
                quantity=row.quantity,
            ))
    # Treat a submitted weekly report as a full snapshot: omitted products
    # have zero demand in the edited report.
    previous_rows = db.query(WeeklyDemand).filter(
        WeeklyDemand.pvz_id == pvz_id,
        WeeklyDemand.week_start == week_start,
    ).all()
    for previous in previous_rows:
        if previous.product_id not in submitted_ids:
            previous.quantity = 0
    db.flush()
    assortment = calculate_assortment(db, pvz, sync_flags=True)
    transfers = plan_rebalancing(db)
    db.commit()
    return {
        "pvz_id": pvz_id,
        "week_start": week_start.date().isoformat(),
        "saved_rows": len(body.rows),
        "assortment": assortment,
        "planned_transfers": [transfer.id for transfer in transfers],
    }


@router.get("/network/demand/{pvz_id}")
def get_weekly_demand_history(pvz_id: int, db: Session = Depends(get_db)):
    if not db.query(PVZ).filter(PVZ.id == pvz_id).first():
        raise HTTPException(404, "ПВЗ не найден")
    rows = db.query(WeeklyDemand).filter(
        WeeklyDemand.pvz_id == pvz_id
    ).order_by(WeeklyDemand.week_start.desc(), WeeklyDemand.product_id.asc()).all()
    result = []
    for row in rows:
        product = db.query(Product).filter(Product.id == row.product_id).first()
        result.append({
            "week_start": row.week_start.date().isoformat(),
            "product_id": row.product_id,
            "product_name": product.name if product else f"Товар #{row.product_id}",
            "sku": product.sku if product else None,
            "quantity": row.quantity,
        })
    return result


@router.get("/network/assortment/{pvz_id}")
def get_assortment(pvz_id: int, db: Session = Depends(get_db)):
    pvz = db.query(PVZ).filter(PVZ.id == pvz_id).first()
    if not pvz:
        raise HTTPException(404, "ПВЗ не найден")
    result = calculate_assortment(db, pvz, sync_flags=True)
    db.commit()
    return result


@router.patch("/products/{product_id}/dimensions")
def update_product_dimensions(
    product_id: int,
    body: ProductDimensionsUpdate,
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(404, "Товар не найден")
    product.length_cm = body.length_cm
    product.width_cm = body.width_cm
    product.height_cm = body.height_cm
    db.flush()
    for location in db.query(PVZ).filter(PVZ.is_mesh_enabled.is_(True)).all():
        calculate_assortment(db, location, sync_flags=True)
    plans = plan_rebalancing(db)
    db.commit()
    return {
        "product_id": product.id,
        "dimensions_cm": {
            "length": product.length_cm,
            "width": product.width_cm,
            "height": product.height_cm,
        },
        "volume_m3": round(_volume_m3(product), 4),
        "planned_transfers": [transfer.id for transfer in plans],
    }


@router.get("/network/transfers")
def list_transfers(db: Session = Depends(get_db)):
    rows = db.query(InventoryTransfer).order_by(InventoryTransfer.created_at.desc()).all()
    result = []
    for item in rows:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        source = db.query(PVZ).filter(PVZ.id == item.from_pvz_id).first()
        target = db.query(PVZ).filter(PVZ.id == item.to_pvz_id).first()
        route = db.query(TruckRoute).filter(TruckRoute.id == item.route_id).first() if item.route_id else None
        result.append({
            "id": item.id,
            "product_id": item.product_id,
            "product_name": product.name if product else f"Товар #{item.product_id}",
            "qty": item.qty,
            "from_pvz_id": item.from_pvz_id,
            "from_label": _pvz_label(source) if source else "—",
            "to_pvz_id": item.to_pvz_id,
            "to_label": _pvz_label(target) if target else "—",
            "route_id": item.route_id,
            "route_name": route.name if route else None,
            "status": item.status,
            "distance_km": item.distance_km,
            "reason": item.reason,
            "created_at": item.created_at.isoformat(),
        })
    return result


@router.post("/network/transfers/{transfer_id}/complete")
def complete_transfer(transfer_id: int, db: Session = Depends(get_db)):
    transfer = db.query(InventoryTransfer).filter(InventoryTransfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(404, "Перемещение не найдено")
    if transfer.status != "READY_ON_ROUTE":
        raise HTTPException(409, "Перемещение ожидает подходящего действующего рейса")
    source = db.query(PVZ).filter(PVZ.id == transfer.from_pvz_id).first()
    target = db.query(PVZ).filter(PVZ.id == transfer.to_pvz_id).first()
    product = db.query(Product).filter(Product.id == transfer.product_id).first()
    if not source or not target or not product:
        raise HTTPException(404, "Не найден пункт или товар")
    available_rows = db.query(StockItem).filter(
        StockItem.pvz_id == source.id,
        StockItem.product_id == product.id,
        StockItem.status == "IN_TRANSFER",
        StockItem.transfer_id == transfer.id,
        StockItem.qty > 0,
    ).order_by(StockItem.accepted_at).all()
    total_available = sum(row.qty for row in available_rows)
    if total_available < transfer.qty:
        raise HTTPException(409, "На исходном ПВЗ больше нет нужного количества товара")
    added_volume = _volume_m3(product) * transfer.qty
    if _occupied_volume(db, target.id) + added_volume > _storage_capacity(target):
        raise HTTPException(409, "На целевом пункте недостаточно свободного объёма")
    remaining = transfer.qty
    for row in available_rows:
        taken = min(row.qty, remaining)
        row.qty -= taken
        remaining -= taken
        if row.qty == 0:
            row.status = "RELOCATED"
        if remaining <= 0:
            break
    db.add(StockItem(
        product_id=product.id,
        pvz_id=target.id,
        qty=transfer.qty,
        status="STORED",
        accepted_at=utcnow(),
        ttl_days=7,
        storage_deadline=utcnow() + timedelta(days=7),
        top_flag=False,
    ))
    transfer.status = "COMPLETED"
    transfer.completed_at = utcnow()
    db.flush()
    calculate_assortment(db, target, sync_flags=True)
    plan_rebalancing(db)
    db.commit()
    return {"id": transfer.id, "status": transfer.status, "from_pvz_id": source.id, "to_pvz_id": target.id}


@router.get("/seller/{seller_id}/products")
def seller_products(seller_id: int, db: Session = Depends(get_db)):
    # Seller IDs are stored in the existing sellers table.
    from app.models import Seller
    seller = db.query(Seller).filter(Seller.id == seller_id).first()
    if not seller:
        raise HTTPException(404, "Продавец не найден")
    return db.query(Product).filter(Product.seller_id == seller_id).order_by(Product.id).all()


@router.post("/seller/intake")
def seller_auto_intake(body: SellerIntake, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == body.product_id).first()
    if not product:
        raise HTTPException(404, "Товар не найден")

    volume = _volume_m3(product)
    candidates = []
    for location in db.query(PVZ).filter(
        PVZ.is_mesh_enabled.is_(True),
        PVZ.is_hub.is_(False),
    ).all():
        demand, _ = _demand_totals(db, location.id)
        weekly = demand.get(product.id, 0)
        if weekly <= 0 or volume > category_volume_limit(product):
            continue
        free = _storage_capacity(location) - _occupied_volume(db, location.id)
        if volume * body.qty <= free:
            candidates.append((weekly, free, location))

    if candidates:
        _, _, destination = max(candidates, key=lambda row: (row[0], row[1]))
        decision = "PVZ"
    else:
        hubs = db.query(PVZ).filter(
            PVZ.is_hub.is_(True),
            PVZ.is_mesh_enabled.is_(True),
        ).all()
        suitable_hubs = [
            ( _storage_capacity(hub) - _occupied_volume(db, hub.id), hub)
            for hub in hubs
            if volume * body.qty <= _storage_capacity(hub) - _occupied_volume(db, hub.id)
        ]
        if not suitable_hubs:
            raise HTTPException(409, "Нет подключённого к Mesh склада с достаточным свободным объёмом")
        _, destination = max(suitable_hubs, key=lambda row: row[0])
        decision = "HUB"

    origin = db.query(PVZ).filter(PVZ.id == body.origin_pvz_id).first() if body.origin_pvz_id else destination
    if not origin:
        raise HTTPException(404, "Пункт приёма продавца не найден")
    if not origin.is_mesh_enabled:
        raise HTTPException(409, "Пункт приёма исключён из Mesh-доставки. Выберите подключённый ПВЗ или склад.")

    source_item = StockItem(
        product_id=product.id,
        pvz_id=origin.id,
        qty=body.qty,
        status="STORED",
        accepted_at=utcnow(),
        ttl_days=7,
        storage_deadline=utcnow() + timedelta(days=7),
        top_flag=False,
    )
    db.add(source_item)
    db.flush()
    transfer = None
    if origin.id != destination.id:
        transfer = _create_transfer(
            db, product.id, body.qty, origin.id, destination.id, "seller_auto_intake"
        )
    calculate_assortment(db, destination, sync_flags=True)
    db.commit()
    return {
        "product_id": product.id,
        "qty": body.qty,
        "origin_pvz_id": origin.id,
        "destination_pvz_id": destination.id,
        "destination": _pvz_label(destination),
        "storage_type": decision,
        "transfer_id": transfer.id if transfer else None,
        "transfer_status": transfer.status if transfer else "STORED_AT_DESTINATION",
        "explanation": (
            "Выбрано по фактическому спросу на товар, категории, габаритам и свободному объёму хранения."
            if decision == "PVZ"
            else "На ПВЗ нет подходящего спроса, габариты не подходят категории или недостаточно места. Товар направлен на подключённый склад."
        ),
    }

@router.get("/customer/profile/{customer_id}")
def get_customer_profile(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        first_pvz = db.query(PVZ).filter(PVZ.is_hub.is_(False)).first()
        customer = Customer(
            id=customer_id,
            name="Новый покупатель",
            city=first_pvz.city if first_pvz else "Казань",
            preferred_pvz_id=first_pvz.id if first_pvz else None,
        )
        db.add(customer)
        db.commit()
        db.refresh(customer)
    preferred = db.query(PVZ).filter(PVZ.id == customer.preferred_pvz_id).first() if customer.preferred_pvz_id else None
    return {
        "id": customer.id,
        "name": customer.name,
        "phone": customer.phone,
        "email": customer.email,
        "city": customer.city,
        "preferred_pvz_id": customer.preferred_pvz_id,
        "preferred_pvz": _pvz_label(preferred) if preferred else None,
    }


@router.patch("/customer/profile/{customer_id}")
def update_customer_profile(customer_id: int, body: CustomerProfileUpdate, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(404, "Профиль покупателя не найден")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("preferred_pvz_id") is not None and not db.query(PVZ).filter(PVZ.id == changes["preferred_pvz_id"]).first():
        raise HTTPException(404, "Выбранный ПВЗ не найден")
    for key, value in changes.items():
        setattr(customer, key, value)
    db.commit()
    return {"id": customer.id, "updated": list(changes.keys())}


def _distance_km(a: PVZ, b: PVZ) -> float:
    lat1, lon1 = _coords(a)
    lat2, lon2 = _coords(b)
    rad = math.pi / 180
    dlat = (lat2 - lat1) * rad
    dlon = (lon2 - lon1) * rad
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


@router.get("/customer/availability")
def customer_availability(
    product_id: int = Query(gt=0),
    pvz_id: int = Query(gt=0),
    radius_km: float = Query(default=25, gt=0, le=300),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    selected = db.query(PVZ).filter(PVZ.id == pvz_id).first()
    if not product or not selected:
        raise HTTPException(404, "Товар или ПВЗ не найден")
    stocks = db.query(StockItem).filter(
        StockItem.product_id == product_id,
        StockItem.status == "STORED",
        StockItem.qty > 0,
    ).all()
    quantities: dict[int, int] = {}
    for stock in stocks:
        quantities[stock.pvz_id] = quantities.get(stock.pvz_id, 0) + stock.qty

    available = []
    for location_id, quantity in quantities.items():
        location = db.query(PVZ).filter(PVZ.id == location_id).first()
        if not location or location.is_hub:
            continue
        _, road_distance = shortest_path(db, selected.id, location.id)
        distance = 0.0 if location.id == selected.id else (
            road_distance if road_distance is not None else _distance_km(selected, location)
        )
        if distance <= radius_km:
            available.append({
                "pvz_id": location.id,
                "city": location.city,
                "address": location.address,
                "qty": quantity,
                "distance_km": round(distance, 1),
                "distance_type": "road" if road_distance is not None else "approximate",
                "is_selected": location.id == selected.id,
                "can_pick_up_now": True,
            })
    available.sort(key=lambda row: (not row["is_selected"], row["distance_km"]))
    local = next((row for row in available if row["is_selected"]), None)
    return {
        "product_id": product.id,
        "product_name": product.name,
        "selected_pvz_id": selected.id,
        "available_at_selected": local is not None,
        "alternatives": [row for row in available if not row["is_selected"]],
        "pickup_options": available,
        "radius_km": radius_km,
    }


@router.post("/customer/orders")
def create_customer_order(body: CustomerOrderCreate, customer_id: int = Query(default=1), db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    product = db.query(Product).filter(Product.id == body.product_id).first()
    location = db.query(PVZ).filter(PVZ.id == body.buyer_pvz_id).first()
    if not customer or not product or not location:
        raise HTTPException(404, "Профиль, товар или ПВЗ не найден")
    stock_rows = db.query(StockItem).filter(
        StockItem.product_id == product.id,
        StockItem.pvz_id == location.id,
        StockItem.status == "STORED",
        StockItem.qty > 0,
    ).order_by(StockItem.accepted_at).all()
    if sum(row.qty for row in stock_rows) < body.qty:
        raise HTTPException(409, "В выбранном ПВЗ недостаточно товара для немедленной выдачи")

    remaining = body.qty
    first_stock = stock_rows[0]
    for row in stock_rows:
        taken = min(row.qty, remaining)
        row.qty -= taken
        remaining -= taken
        if row.qty == 0:
            row.status = "RELOCATED"
        if remaining <= 0:
            break

    reserved_stock = StockItem(
        product_id=product.id,
        pvz_id=location.id,
        qty=body.qty,
        status="RESERVED",
        accepted_at=first_stock.accepted_at,
        ttl_days=first_stock.ttl_days,
        storage_deadline=first_stock.storage_deadline,
        top_flag=False,
        last_top_check=utcnow(),
    )
    db.add(reserved_stock)
    db.flush()
    order = Order(
        product_id=product.id,
        qty=body.qty,
        buyer_city=location.city,
        buyer_pvz_id=location.id,
        customer_id=customer.id,
        reserved_stock_item_id=reserved_stock.id,
        status="READY",
    )
    db.add(order)
    db.flush()
    reserved_stock.order_id = order.id
    order.reserved_stock_item_id = reserved_stock.id
    plan_rebalancing(db)
    db.commit()
    db.refresh(order)
    return {
        "id": order.id,
        "status": order.status,
        "product_name": product.name,
        "qty": order.qty,
        "pickup_pvz_id": location.id,
        "pickup_address": _pvz_label(location),
        "message": "Заказ оформлен. Товар уже находится в выбранном пункте.",
    }


@router.post("/customer/orders/{order_id}/pickup")
def confirm_customer_pickup(
    order_id: int,
    customer_id: int = Query(default=1),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.customer_id == customer_id,
    ).first()
    if not order:
        raise HTTPException(404, "Заказ не найден")
    if order.status != "READY":
        raise HTTPException(409, "Заказ не готов к выдаче")
    reserved_stock = db.query(StockItem).filter(
        StockItem.id == order.reserved_stock_item_id,
        StockItem.status == "RESERVED",
    ).first()
    if not reserved_stock:
        raise HTTPException(409, "Резерв товара не найден")
    reserved_stock.status = "ISSUED"
    order.status = "ISSUED"
    location = db.query(PVZ).filter(PVZ.id == order.buyer_pvz_id).first()
    if location:
        from app.models import Accrual
        from app.tariffs import storage_fee as calc_storage_fee

        days = max((utcnow() - reserved_stock.accepted_at).total_seconds() / 86400, 0)
        storage_amount = calc_storage_fee(days, order.qty, location.storage_rate_day)
        for accrual_type, amount in (
            ("issue_intake", location.intake_fee * order.qty),
            ("assembly", location.assembly_fee),
            ("storage_fee", storage_amount),
            ("local_bonus", location.local_bonus),
        ):
            db.add(Accrual(
                pvz_id=location.id,
                order_id=order.id,
                stock_item_id=reserved_stock.id,
                type=accrual_type,
                amount=round(amount, 2),
            ))
        calculate_assortment(db, location, sync_flags=True)
    db.query(CapacityReservation).filter(
        CapacityReservation.source.like(f"order:{order.id}%")
    ).delete(synchronize_session=False)
    plan_rebalancing(db)
    db.commit()
    return {"order_id": order.id, "status": order.status, "message": "Получение заказа подтверждено"}


@router.get("/customer/orders/{customer_id}")
def list_customer_orders(customer_id: int, db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.customer_id == customer_id).order_by(Order.created_at.desc()).all()
    return [{
        "id": order.id,
        "product_id": order.product_id,
        "qty": order.qty,
        "status": order.status,
        "buyer_pvz_id": order.buyer_pvz_id,
        "created_at": order.created_at.isoformat(),
    } for order in orders]
