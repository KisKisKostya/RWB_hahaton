"""Mesh MVP FastAPI — все расчёты и эндпоинты."""
import math
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app import schemas
from app.capacity import capacity_ok as check_capacity_ok
from app.capacity import usable_capacity
from app.models import (
    Accrual,
    CapacityReservation,
    Order,
    Product,
    PVZ,
    Return,
    RouteOption,
    Seller,
    StockItem,
    get_db,
    init_db,
    utcnow,
)
from app.routing import build_hub, build_local
from app.tariffs import (
    ASSEMBLY_FEE,
    COMMISSION_RATE,
    HUB_BASE,
    HUB_PER_KM,
    INTAKE_FEE,
    LOCAL_BASE,
    LOCAL_PER_KM,
    RESERVE_PCT,
    STORAGE_PER_UNIT_DAY,
    TOP_RECHECK_DAYS,
    TTL_MAX,
    TTL_MIN,
    storage_fee as calc_storage_fee,
)

CITY_COORDS = {
    "Казань": (55.796, 49.106),
    "Москва": (55.755, 37.617),
}

OCCUPIED_STATUSES = {"ACCEPTED", "STORED", "RESERVED", "ASSEMBLED"}

app = FastAPI(title="Mesh MVP", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


# ---------- helpers ----------

def haversine_km(city_a: str, city_b: str) -> float:
    if city_a == city_b:
        return 8.0
    a = CITY_COORDS.get(city_a)
    b = CITY_COORDS.get(city_b)
    if not a or not b:
        return 500.0
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def days_stored(accepted_at: datetime, now: Optional[datetime] = None) -> float:
    now = now or utcnow()
    delta = now - accepted_at
    return max(delta.total_seconds() / 86400.0, 0.0)


def storage_fee(accepted_at: datetime, qty: int, rate: float = STORAGE_PER_UNIT_DAY) -> float:
    return calc_storage_fee(days_stored(accepted_at), qty, rate)


def occupied_units(db: Session, pvz_id: int) -> int:
    items = (
        db.query(StockItem)
        .filter(StockItem.pvz_id == pvz_id, StockItem.status.in_(OCCUPIED_STATUSES))
        .all()
    )
    return sum(i.qty for i in items)


def reserved_units(db: Session, pvz_id: int) -> int:
    now = utcnow()
    rows = (
        db.query(CapacityReservation)
        .filter(CapacityReservation.pvz_id == pvz_id, CapacityReservation.expires_at > now)
        .all()
    )
    return sum(r.units for r in rows)


def capacity_snapshot(db: Session, pvz: PVZ, incoming: int = 0) -> dict:
    occ = occupied_units(db, pvz.id)
    res = reserved_units(db, pvz.id)
    reserve = pvz.reserve_pct if pvz.reserve_pct is not None else RESERVE_PCT
    usable = int(usable_capacity(pvz.capacity_units, reserve))
    free = max(usable - occ - res, 0)
    # occupied + reserved counts as already taken; incoming is new load
    ok = check_capacity_ok(occ + res, incoming, pvz.capacity_units, reserve)
    return {
        "pvz_id": pvz.id,
        "capacity_units": pvz.capacity_units,
        "occupied": occ,
        "reserved": res,
        "incoming": incoming,
        "free": free,
        "usable_limit": usable,
        "capacity_ok": ok,
    }


def write_accrual(
    db: Session,
    *,
    pvz_id: int,
    accrual_type: str,
    amount: float,
    order_id: Optional[int] = None,
    stock_item_id: Optional[int] = None,
) -> Accrual:
    row = Accrual(
        pvz_id=pvz_id,
        order_id=order_id,
        stock_item_id=stock_item_id,
        type=accrual_type,
        amount=amount,
    )
    db.add(row)
    return row


def set_stock_status(
    db: Session,
    item: StockItem,
    new_status: str,
    *,
    order_id: Optional[int] = None,
    amount: float = 0.0,
) -> None:
    item.status = new_status
    write_accrual(
        db,
        pvz_id=item.pvz_id,
        accrual_type=f"status:{new_status}",
        amount=amount,
        order_id=order_id,
        stock_item_id=item.id,
    )


def find_local_stock(db: Session, product_id: int, buyer_city: str) -> Optional[StockItem]:
    """Сток на ПВЗ того же города с top_flag, не хаб."""
    q = (
        db.query(StockItem)
        .join(PVZ, StockItem.pvz_id == PVZ.id)
        .filter(
            StockItem.product_id == product_id,
            StockItem.status.in_(["ACCEPTED", "STORED"]),
            StockItem.top_flag.is_(True),
            PVZ.city == buyer_city,
            PVZ.is_hub.is_(False),
        )
        .order_by(StockItem.accepted_at.asc())
    )
    return q.first()


def find_hub(db: Session) -> Optional[PVZ]:
    return db.query(PVZ).filter(PVZ.is_hub.is_(True)).first()


def build_route_options(db: Session, order: Order) -> list[RouteOption]:
    product = db.query(Product).filter(Product.id == order.product_id).first()
    buyer_pvz = db.query(PVZ).filter(PVZ.id == order.buyer_pvz_id).first()
    if not product or not buyer_pvz:
        raise HTTPException(404, "product or buyer_pvz not found")

    db.query(RouteOption).filter(RouteOption.order_id == order.id).delete()
    db.flush()

    local_item = find_local_stock(db, order.product_id, order.buyer_city)
    hub = find_hub(db)

    # --- hub first (local needs hub eta / marketplace_cost) ---
    hub_dist = 800.0
    hub_eta = 2.0
    hub_stor = 0.0
    hub_source_id = None
    if hub:
        hub_source_id = hub.id
        hub_dist = haversine_km(hub.city, buyer_pvz.city)
        hub_eta = 1.5 + hub_dist / 400.0
        hub_item = (
            db.query(StockItem)
            .filter(
                StockItem.product_id == order.product_id,
                StockItem.pvz_id == hub.id,
                StockItem.status.in_(["ACCEPTED", "STORED"]),
            )
            .first()
        )
        if hub_item:
            hub_stor = storage_fee(hub_item.accepted_at, order.qty, hub.storage_rate_day)

    hub_data = build_hub(
        dist=hub_dist,
        eta_days=hub_eta,
        price=product.price,
        qty=order.qty,
        storage_fee=hub_stor,
        source_pvz_id=hub_source_id,
        hub_available=hub is not None,
    )

    # --- local ---
    local_dist = 8.0
    local_eta = 0.5
    stor = 0.0
    source_pvz_id = None
    top_flag = False
    has_stock = local_item is not None
    cap = capacity_snapshot(db, buyer_pvz, incoming=order.qty)

    if local_item:
        source_pvz = db.query(PVZ).filter(PVZ.id == local_item.pvz_id).first()
        source_pvz_id = source_pvz.id
        top_flag = bool(local_item.top_flag)
        stor = storage_fee(local_item.accepted_at, order.qty, source_pvz.storage_rate_day)
        local_dist = haversine_km(source_pvz.city, buyer_pvz.city)
        if source_pvz.city == buyer_pvz.city:
            local_dist = max(3.0, abs(source_pvz.id - buyer_pvz.id) * 2.5)
        local_eta = 0.3 + local_dist / 80.0

    local_data = build_local(
        dist=local_dist,
        eta_days=local_eta,
        price=product.price,
        qty=order.qty,
        storage_fee=stor,
        top_flag=top_flag,
        occupied=cap["occupied"] + cap["reserved"],
        incoming=order.qty,
        capacity_units=buyer_pvz.capacity_units,
        reserve_pct=buyer_pvz.reserve_pct or RESERVE_PCT,
        hub_eta=hub_data["eta_days"],
        hub_marketplace_cost=hub_data["marketplace_cost"],
        source_pvz_id=source_pvz_id,
        has_stock=has_stock,
    )

    local_opt = RouteOption(
        order_id=order.id,
        type=local_data["type"],
        cost=local_data["cost"],
        eta_days=local_data["eta_days"],
        distance_km=local_data["distance_km"],
        pvz_income=local_data["pvz_income"],
        marketplace_margin=local_data["marketplace_margin"],
        seller_payout=local_data["seller_payout"],
        feasible=local_data["feasible"],
        reject_reason=local_data["reject_reason"],
        source_pvz_id=local_data["source_pvz_id"],
    )
    hub_opt = RouteOption(
        order_id=order.id,
        type=hub_data["type"],
        cost=hub_data["cost"],
        eta_days=hub_data["eta_days"],
        distance_km=hub_data["distance_km"],
        pvz_income=hub_data["pvz_income"],
        marketplace_margin=hub_data["marketplace_margin"],
        seller_payout=hub_data["seller_payout"],
        feasible=hub_data["feasible"],
        reject_reason=hub_data["reject_reason"],
        source_pvz_id=hub_data["source_pvz_id"],
    )
    db.add(local_opt)
    db.add(hub_opt)
    db.flush()
    return [local_opt, hub_opt]


# ---------- endpoints ----------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/pvz", response_model=list[schemas.PVZOut])
def list_pvz(db: Session = Depends(get_db)):
    return db.query(PVZ).all()


@app.get("/sellers", response_model=list[schemas.SellerOut])
def list_sellers(db: Session = Depends(get_db)):
    return db.query(Seller).all()


@app.get("/products", response_model=list[schemas.ProductOut])
def list_products(db: Session = Depends(get_db)):
    return db.query(Product).all()


@app.post("/pvz/{pvz_id}/intake", response_model=schemas.StockItemOut)
def intake(pvz_id: int, body: schemas.IntakeIn, db: Session = Depends(get_db)):
    pvz = db.query(PVZ).filter(PVZ.id == pvz_id).first()
    if not pvz:
        raise HTTPException(404, "pvz not found")
    product = db.query(Product).filter(Product.id == body.product_id).first()
    if not product:
        raise HTTPException(404, "product not found")

    cap = capacity_snapshot(db, pvz, incoming=body.qty)
    if not cap["capacity_ok"]:
        raise HTTPException(409, detail={"error": "no_capacity", "capacity": cap})

    now = utcnow()
    ttl = body.ttl_days or 7
    ttl = max(TTL_MIN, min(TTL_MAX, ttl))
    item = StockItem(
        product_id=body.product_id,
        pvz_id=pvz_id,
        qty=body.qty,
        status="ACCEPTED",
        accepted_at=now,
        ttl_days=ttl,
        storage_deadline=now + timedelta(days=ttl),
        top_flag=body.top_flag,
        last_top_check=now if body.top_flag else None,
    )
    db.add(item)
    db.flush()
    fee = (pvz.intake_fee or INTAKE_FEE) * body.qty
    write_accrual(
        db,
        pvz_id=pvz_id,
        accrual_type="intake",
        amount=fee,
        stock_item_id=item.id,
    )
    item.status = "STORED"
    write_accrual(
        db,
        pvz_id=pvz_id,
        accrual_type="status:STORED",
        amount=0.0,
        stock_item_id=item.id,
    )
    db.commit()
    db.refresh(item)
    return item


@app.get("/pvz/{pvz_id}/stock", response_model=list[schemas.StockItemOut])
def get_stock(pvz_id: int, db: Session = Depends(get_db)):
    if not db.query(PVZ).filter(PVZ.id == pvz_id).first():
        raise HTTPException(404, "pvz not found")
    return db.query(StockItem).filter(StockItem.pvz_id == pvz_id).all()


@app.get("/pvz/{pvz_id}/capacity", response_model=schemas.CapacityOut)
def get_capacity(pvz_id: int, db: Session = Depends(get_db)):
    pvz = db.query(PVZ).filter(PVZ.id == pvz_id).first()
    if not pvz:
        raise HTTPException(404, "pvz not found")
    return capacity_snapshot(db, pvz)


@app.post("/orders", response_model=schemas.OrderOut)
def create_order(body: schemas.OrderCreate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == body.product_id).first()
    if not product:
        raise HTTPException(404, "product not found")
    buyer_pvz = db.query(PVZ).filter(PVZ.id == body.buyer_pvz_id).first()
    if not buyer_pvz:
        raise HTTPException(404, "buyer_pvz not found")

    order = Order(
        product_id=body.product_id,
        qty=body.qty,
        buyer_city=body.buyer_city,
        buyer_pvz_id=body.buyer_pvz_id,
        status="CREATED",
    )
    db.add(order)
    db.flush()
    build_route_options(db, order)
    db.commit()
    db.refresh(order)
    return order


@app.get("/orders/{order_id}/routes", response_model=list[schemas.RouteOptionOut])
def get_routes(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "order not found")
    routes = db.query(RouteOption).filter(RouteOption.order_id == order_id).all()
    if not routes:
        routes = build_route_options(db, order)
        db.commit()
    return routes


@app.post("/orders/{order_id}/route", response_model=schemas.OrderOut)
def select_route(order_id: int, body: schemas.RouteSelectIn, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "order not found")
    route = (
        db.query(RouteOption)
        .filter(RouteOption.id == body.route_id, RouteOption.order_id == order_id)
        .first()
    )
    if not route:
        raise HTTPException(404, "route not found")
    if not route.feasible:
        raise HTTPException(
            409,
            detail={"error": "route_not_feasible", "reject_reason": route.reject_reason},
        )

    order.chosen_route_id = route.id
    order.status = "ROUTE_SELECTED"

    # reserve stock / capacity
    if route.type == "local" and route.source_pvz_id:
        item = find_local_stock(db, order.product_id, order.buyer_city)
        if item:
            set_stock_status(db, item, "RESERVED", order_id=order.id)
        buyer = db.query(PVZ).filter(PVZ.id == order.buyer_pvz_id).first()
        db.add(
            CapacityReservation(
                pvz_id=buyer.id,
                units=order.qty,
                source=f"order:{order.id}",
                expires_at=utcnow() + timedelta(days=2),
            )
        )
        order.status = "RESERVED"
    elif route.type == "hub":
        hub = find_hub(db)
        if hub:
            item = (
                db.query(StockItem)
                .filter(
                    StockItem.product_id == order.product_id,
                    StockItem.pvz_id == hub.id,
                    StockItem.status.in_(["ACCEPTED", "STORED"]),
                )
                .first()
            )
            if item:
                set_stock_status(db, item, "RESERVED", order_id=order.id)
            else:
                # create transit reservation at buyer
                pass
            db.add(
                CapacityReservation(
                    pvz_id=order.buyer_pvz_id,
                    units=order.qty,
                    source=f"order:{order.id}:hub",
                    expires_at=utcnow() + timedelta(days=3),
                )
            )
            order.status = "RESERVED"

    db.commit()
    db.refresh(order)
    return order


@app.post("/orders/{order_id}/assemble", response_model=schemas.OrderOut)
def assemble(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "order not found")
    if order.status not in ("RESERVED", "ROUTE_SELECTED"):
        raise HTTPException(409, f"bad status: {order.status}")

    route = db.query(RouteOption).filter(RouteOption.id == order.chosen_route_id).first()
    if route and route.source_pvz_id:
        item = (
            db.query(StockItem)
            .filter(
                StockItem.product_id == order.product_id,
                StockItem.pvz_id == route.source_pvz_id,
                StockItem.status == "RESERVED",
            )
            .first()
        )
        if item:
            set_stock_status(
                db, item, "ASSEMBLED", order_id=order.id, amount=ASSEMBLY_FEE
            )

    order.status = "ASSEMBLED"
    db.commit()
    db.refresh(order)
    return order


@app.post("/orders/{order_id}/issue", response_model=schemas.OrderOut)
def issue(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "order not found")
    if order.status not in ("ASSEMBLED", "IN_TRANSIT", "READY", "RESERVED"):
        # allow READY path
        if order.status == "ASSEMBLED":
            order.status = "IN_TRANSIT"
        else:
            raise HTTPException(409, f"bad status: {order.status}")

    if order.status == "ASSEMBLED":
        order.status = "IN_TRANSIT"
        db.flush()

    route = db.query(RouteOption).filter(RouteOption.id == order.chosen_route_id).first()
    if route and route.source_pvz_id:
        item = (
            db.query(StockItem)
            .filter(
                StockItem.product_id == order.product_id,
                StockItem.pvz_id == route.source_pvz_id,
                StockItem.status.in_(["ASSEMBLED", "RESERVED"]),
            )
            .first()
        )
        if item:
            set_stock_status(db, item, "ISSUED", order_id=order.id)

    # buyer intake accrual
    write_accrual(
        db,
        pvz_id=order.buyer_pvz_id,
        accrual_type="issue_intake",
        amount=INTAKE_FEE * order.qty,
        order_id=order.id,
    )
    if route:
        write_accrual(
            db,
            pvz_id=order.buyer_pvz_id,
            accrual_type="pvz_income",
            amount=route.pvz_income,
            order_id=order.id,
        )

    order.status = "ISSUED"
    db.commit()
    db.refresh(order)
    return order


@app.post("/orders/{order_id}/return", response_model=schemas.ReturnOut)
def return_order(order_id: int, body: schemas.ReturnIn, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "order not found")
    if order.status not in ("ISSUED", "READY"):
        raise HTTPException(409, f"bad status: {order.status}")

    if body.condition == "damaged":
        decision = "to_seller"
        stock_status = "DAMAGED"
    else:
        # intact → keep at buyer PVZ or relocate if no capacity
        cap = capacity_snapshot(
            db, db.query(PVZ).filter(PVZ.id == order.buyer_pvz_id).first(), incoming=order.qty
        )
        if cap["capacity_ok"]:
            decision = "keep"
            stock_status = "STORED"
        else:
            decision = "relocate"
            stock_status = "RELOCATED"

    ret = Return(
        order_id=order.id,
        reason=body.reason,
        condition=body.condition,
        decision=decision,
    )
    db.add(ret)

    route = db.query(RouteOption).filter(RouteOption.id == order.chosen_route_id).first()
    source_id = route.source_pvz_id if route else order.buyer_pvz_id
    item = (
        db.query(StockItem)
        .filter(StockItem.product_id == order.product_id, StockItem.pvz_id == source_id)
        .order_by(StockItem.id.desc())
        .first()
    )
    if item:
        if decision == "keep":
            item.pvz_id = order.buyer_pvz_id
            item.top_flag = True
            item.last_top_check = utcnow()
        elif decision == "relocate":
            hub = find_hub(db)
            if hub:
                item.pvz_id = hub.id
        set_stock_status(db, item, stock_status, order_id=order.id)

    order.status = "RETURNED"
    db.commit()
    db.refresh(ret)
    return ret


@app.post("/stock/{stock_id}/relocate", response_model=schemas.StockItemOut)
def relocate(stock_id: int, body: schemas.RelocateIn, db: Session = Depends(get_db)):
    item = db.query(StockItem).filter(StockItem.id == stock_id).first()
    if not item:
        raise HTTPException(404, "stock not found")
    target = db.query(PVZ).filter(PVZ.id == body.target_pvz_id).first()
    if not target:
        raise HTTPException(404, "target pvz not found")

    cap = capacity_snapshot(db, target, incoming=item.qty)
    if not cap["capacity_ok"]:
        raise HTTPException(409, detail={"error": "no_capacity", "capacity": cap})

    # TTL / TOP recheck
    now = utcnow()
    if item.storage_deadline and item.storage_deadline < now:
        set_stock_status(db, item, "EXPIRED", amount=0.0)
        set_stock_status(db, item, "TO_SELLER", amount=0.0)
        db.commit()
        db.refresh(item)
        return item

    if item.last_top_check and (now - item.last_top_check).days >= TOP_RECHECK_DAYS:
        item.top_flag = False
        item.last_top_check = now

    item.pvz_id = target.id
    set_stock_status(db, item, "RELOCATED", amount=0.0)
    if target.is_hub:
        set_stock_status(db, item, "TO_HUB", amount=0.0)
    else:
        set_stock_status(db, item, "STORED", amount=0.0)

    db.commit()
    db.refresh(item)
    return item


@app.get("/pvz/{pvz_id}/accruals", response_model=list[schemas.AccrualOut])
def get_accruals(pvz_id: int, db: Session = Depends(get_db)):
    if not db.query(PVZ).filter(PVZ.id == pvz_id).first():
        raise HTTPException(404, "pvz not found")
    return db.query(Accrual).filter(Accrual.pvz_id == pvz_id).order_by(Accrual.id).all()


@app.get("/seller/{seller_id}/payouts", response_model=list[schemas.SellerPayoutOut])
def seller_payouts(seller_id: int, db: Session = Depends(get_db)):
    seller = db.query(Seller).filter(Seller.id == seller_id).first()
    if not seller:
        raise HTTPException(404, "seller not found")
    products = db.query(Product).filter(Product.seller_id == seller_id).all()
    pids = [p.id for p in products]
    orders = db.query(Order).filter(Order.product_id.in_(pids)).all() if pids else []
    out = []
    for o in orders:
        product = next(p for p in products if p.id == o.product_id)
        route = (
            db.query(RouteOption).filter(RouteOption.id == o.chosen_route_id).first()
            if o.chosen_route_id
            else None
        )
        price = product.price * o.qty
        commission = COMMISSION_RATE * price
        stor = 0.0
        payout = route.seller_payout if route else price - commission
        if route:
            # reverse-engineer storage from payout formula
            stor = price - commission - route.seller_payout
        out.append(
            schemas.SellerPayoutOut(
                seller_id=seller_id,
                order_id=o.id,
                product_id=product.id,
                price=round(price, 2),
                commission=round(commission, 2),
                storage_fee=round(stor, 2),
                payout=round(payout, 2),
                status=o.status,
            )
        )
    return out


@app.get("/analytics/compare", response_model=schemas.CompareOut)
def analytics_compare(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "order not found")
    routes = db.query(RouteOption).filter(RouteOption.order_id == order_id).all()
    if not routes:
        routes = build_route_options(db, order)
        db.commit()
    local = next((r for r in routes if r.type == "local"), None)
    hub = next((r for r in routes if r.type == "hub"), None)
    recommended = None
    if local and local.feasible:
        recommended = "local"
    elif hub and hub.feasible:
        recommended = "hub"
    delta_cost = delta_eta = delta_margin = None
    if local and hub:
        delta_cost = round(local.cost - hub.cost, 2)
        delta_eta = round(local.eta_days - hub.eta_days, 2)
        delta_margin = round(local.marketplace_margin - hub.marketplace_margin, 2)
    return schemas.CompareOut(
        order_id=order_id,
        local=local,
        hub=hub,
        recommended=recommended,
        delta_cost=delta_cost,
        delta_eta=delta_eta,
        delta_margin=delta_margin,
    )


@app.get("/analytics/sensitivity", response_model=schemas.SensitivityOut)
def analytics_sensitivity(param: str = "LOCAL_PER_KM", order_id: Optional[int] = None):
    """Простая чувствительность тарифа — без изменения БД."""
    base_map = {
        "LOCAL_PER_KM": LOCAL_PER_KM,
        "HUB_PER_KM": HUB_PER_KM,
        "COMMISSION_RATE": COMMISSION_RATE,
        "LOCAL_BASE": LOCAL_BASE,
        "HUB_BASE": HUB_BASE,
        "ASSEMBLY_FEE": ASSEMBLY_FEE,
    }
    if param not in base_map:
        raise HTTPException(400, f"unknown param, choose from {list(base_map)}")
    base = base_map[param]
    sweeps = []
    for mul in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
        val = round(base * mul, 4)
        # toy margin impact
        if "PER_KM" in param or "BASE" in param or param == "ASSEMBLY_FEE":
            impact = round(-(val - base) * 10, 2)
        else:
            impact = round((val - base) * 1000, 2)
        sweeps.append({"value": val, "multiplier": mul, "margin_delta": impact})
    return schemas.SensitivityOut(param=param, base_value=base, sweeps=sweeps)


@app.get("/orders", response_model=list[schemas.OrderOut])
def list_orders(db: Session = Depends(get_db)):
    return db.query(Order).order_by(Order.id).all()


@app.get("/orders/{order_id}", response_model=schemas.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "order not found")
    return order
