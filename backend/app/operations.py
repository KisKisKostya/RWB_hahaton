"""Operational exception workflows, returns and finance reporting for Mesh MVP."""

import math
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.lifecycle import transition_order, transition_stock
from app.models import (
    Accrual,
    CapacityReservation,
    Customer,
    InventoryIncident,
    InventoryTransfer,
    Order,
    Product,
    PVZ,
    Return,
    RouteOption,
    Seller,
    StockItem,
    TruckRoute,
    get_db,
    utcnow,
)
from app.tariffs import HUB_PER_KM

router = APIRouter(tags=["operations", "returns", "finance"])
OCCUPIED_STATUSES = ("ACCEPTED", "STORED", "RESERVED", "ASSEMBLED", "IN_TRANSFER", "RETURNED", "DAMAGED")


class ReturnRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    condition: str = Field(pattern="^(intact|damaged)$")


class IncidentResolution(BaseModel):
    resolution_note: str = Field(min_length=3, max_length=500)
    mark_sent_to_seller: bool = False


def _stock_transition(db: Session, item: StockItem, next_status: str, order_id: Optional[int] = None) -> None:
    status, accrual = transition_stock(
        item.status,
        next_status,
        pvz_id=item.pvz_id,
        stock_item_id=item.id,
        order_id=order_id,
    )
    item.status = status
    if accrual:
        db.add(Accrual(**accrual))


def _create_incident(
    db: Session,
    *,
    incident_type: str,
    message: str,
    severity: str = "warning",
    pvz_id: Optional[int] = None,
    transfer_id: Optional[int] = None,
    order_id: Optional[int] = None,
    stock_item_id: Optional[int] = None,
) -> InventoryIncident:
    row = InventoryIncident(
        incident_type=incident_type,
        severity=severity,
        status="OPEN",
        message=message,
        pvz_id=pvz_id,
        transfer_id=transfer_id,
        order_id=order_id,
        stock_item_id=stock_item_id,
    )
    db.add(row)
    db.flush()
    return row


def _occupied_units(db: Session, pvz_id: int) -> int:
    rows = db.query(StockItem).filter(
        StockItem.pvz_id == pvz_id,
        StockItem.status.in_(OCCUPIED_STATUSES),
    ).all()
    active_reservations = db.query(CapacityReservation).filter(
        CapacityReservation.pvz_id == pvz_id,
        CapacityReservation.expires_at > utcnow(),
    ).all()
    return sum(row.qty for row in rows) + sum(row.units for row in active_reservations)


def _volume_m3(product: Product) -> float:
    return max(
        (float(product.length_cm or 10) * float(product.width_cm or 10) * float(product.height_cm or 10)) / 1_000_000,
        0.000001,
    )


def _occupied_volume(db: Session, pvz_id: int) -> float:
    rows = db.query(StockItem, Product).join(Product, Product.id == StockItem.product_id).filter(
        StockItem.pvz_id == pvz_id,
        StockItem.status.in_(OCCUPIED_STATUSES),
    ).all()
    return sum(_volume_m3(product) * item.qty for item, product in rows)


def _has_capacity(db: Session, pvz: PVZ, product: Product, qty: int) -> bool:
    usable_units = int(pvz.capacity_units * (1 - (pvz.reserve_pct or 0)))
    if _occupied_units(db, pvz.id) + qty > usable_units:
        return False
    storage_capacity = float(pvz.storage_area_m2 or 0) * float(pvz.storage_height_m or 0)
    return _occupied_volume(db, pvz.id) + _volume_m3(product) * qty <= storage_capacity


def process_return(db: Session, order: Order, body: ReturnRequest) -> Return:
    if order.status != "ISSUED":
        raise HTTPException(409, "Вернуть можно только выданный заказ")
    if db.query(Return).filter(Return.order_id == order.id).first():
        raise HTTPException(409, "Для этого заказа возврат уже зарегистрирован")

    product = db.query(Product).filter(Product.id == order.product_id).first()
    buyer_pvz = db.query(PVZ).filter(PVZ.id == order.buyer_pvz_id).first()
    if not product or not buyer_pvz:
        raise HTTPException(404, "Товар или ПВЗ заказа не найден")

    item = None
    if order.reserved_stock_item_id:
        item = db.query(StockItem).filter(StockItem.id == order.reserved_stock_item_id).first()
    if not item:
        item = db.query(StockItem).filter(
            StockItem.order_id == order.id,
            StockItem.product_id == order.product_id,
            StockItem.status == "ISSUED",
        ).order_by(StockItem.id.desc()).first()
    if not item:
        route = db.query(RouteOption).filter(RouteOption.id == order.chosen_route_id).first() if order.chosen_route_id else None
        source_id = route.source_pvz_id if route and route.source_pvz_id else buyer_pvz.id
        item = db.query(StockItem).filter(
            StockItem.product_id == order.product_id,
            StockItem.pvz_id == source_id,
            StockItem.status == "ISSUED",
            StockItem.qty >= order.qty,
        ).order_by(StockItem.id.desc()).first()
    if not item or item.status != "ISSUED" or item.qty < order.qty:
        raise HTTPException(409, "Не найдена точная партия выданного товара для возврата")

    if item.qty > order.qty:
        item.qty -= order.qty
        returned_item = StockItem(
            product_id=item.product_id,
            pvz_id=item.pvz_id,
            qty=order.qty,
            status="ISSUED",
            accepted_at=item.accepted_at,
            ttl_days=item.ttl_days,
            storage_deadline=item.storage_deadline,
            top_flag=False,
            last_top_check=utcnow(),
            order_id=order.id,
        )
        db.add(returned_item)
        db.flush()
        item = returned_item
    else:
        item.order_id = order.id
    order.reserved_stock_item_id = item.id

    refund_amount = round(product.price * order.qty, 2)
    if body.condition == "damaged":
        _stock_transition(db, item, "DAMAGED", order.id)
        decision = "to_seller"
        return_status = "WAITING_SELLER"
        _create_incident(
            db,
            incident_type="DAMAGED_RETURN",
            severity="high",
            message=f"Повреждённый возврат заказа #{order.id}: требуется осмотр и отправка продавцу.",
            pvz_id=buyer_pvz.id,
            order_id=order.id,
            stock_item_id=item.id,
        )
    else:
        # A returned parcel physically enters the buyer's PVZ first.
        item.pvz_id = buyer_pvz.id
        _stock_transition(db, item, "RETURNED", order.id)
        if _has_capacity(db, buyer_pvz, product, order.qty):
            _stock_transition(db, item, "STORED", order.id)
            item.accepted_at = utcnow()
            item.ttl_days = 7
            item.storage_deadline = utcnow() + timedelta(days=7)
            item.top_flag = False
            item.last_top_check = utcnow()
            decision = "keep"
            return_status = "PROCESSED"
        else:
            from app.network import _create_transfer

            hubs = db.query(PVZ).filter(
                PVZ.is_hub.is_(True),
                PVZ.is_mesh_enabled.is_(True),
            ).all()
            target_hub = next(
                (
                    hub for hub in hubs
                    if _has_capacity(db, hub, product, order.qty)
                    or (_occupied_units(db, hub.id) + order.qty <= int(hub.capacity_units * (1 - (hub.reserve_pct or 0))))
                ),
                None,
            )
            if target_hub:
                transfer = _create_transfer(
                    db,
                    product_id=product.id,
                    qty=order.qty,
                    from_id=buyer_pvz.id,
                    to_id=target_hub.id,
                    reason="returned_stock_rebalance",
                )
                if transfer:
                    decision = "relocate"
                    return_status = "WAITING_TRANSFER"
                    if transfer.status == "WAITING_ROUTE":
                        _create_incident(
                            db,
                            incident_type="RETURN_WAITING_ROUTE",
                            message=f"Возврат заказа #{order.id} ожидает подходящего рейса на хаб.",
                            pvz_id=buyer_pvz.id,
                            transfer_id=transfer.id,
                            order_id=order.id,
                            stock_item_id=item.id,
                        )
                else:
                    decision = "relocate"
                    return_status = "NEEDS_REVIEW"
            else:
                decision = "relocate"
                return_status = "NEEDS_REVIEW"
            if return_status == "NEEDS_REVIEW":
                _create_incident(
                    db,
                    incident_type="RETURN_CAPACITY",
                    severity="high",
                    message=f"На ПВЗ {buyer_pvz.id} не хватает места для возврата заказа #{order.id}; свободного хаба нет.",
                    pvz_id=buyer_pvz.id,
                    order_id=order.id,
                    stock_item_id=item.id,
                )

    row = Return(
        order_id=order.id,
        reason=body.reason,
        condition=body.condition,
        decision=decision,
        stock_item_id=item.id,
        refund_amount=refund_amount,
        status=return_status,
    )
    db.add(row)
    order.status = transition_order(order.status, "RETURNED")
    db.add(Accrual(
        pvz_id=buyer_pvz.id,
        order_id=order.id,
        stock_item_id=item.id,
        type="return_refund",
        amount=-refund_amount,
    ))
    db.flush()
    return row


@router.get("/returns")
def list_returns(db: Session = Depends(get_db)):
    rows = db.query(Return).order_by(Return.created_at.desc()).all()
    result = []
    for row in rows:
        order = db.query(Order).filter(Order.id == row.order_id).first()
        product = db.query(Product).filter(Product.id == order.product_id).first() if order else None
        result.append({
            "id": row.id,
            "order_id": row.order_id,
            "product_name": product.name if product else "—",
            "qty": order.qty if order else 0,
            "reason": row.reason,
            "condition": row.condition,
            "decision": row.decision,
            "refund_amount": row.refund_amount,
            "status": row.status,
            "stock_item_id": row.stock_item_id,
            "created_at": row.created_at.isoformat(),
        })
    return result


@router.get("/ops/incidents")
def list_incidents(status: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(InventoryIncident)
    if status:
        query = query.filter(InventoryIncident.status == status.upper())
    rows = query.order_by(InventoryIncident.created_at.desc()).all()
    return [{
        "id": row.id,
        "incident_type": row.incident_type,
        "severity": row.severity,
        "status": row.status,
        "message": row.message,
        "resolution_note": row.resolution_note,
        "pvz_id": row.pvz_id,
        "transfer_id": row.transfer_id,
        "order_id": row.order_id,
        "stock_item_id": row.stock_item_id,
        "created_at": row.created_at.isoformat(),
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
    } for row in rows]


@router.post("/network/transfers/{transfer_id}/report-failure")
def report_transfer_failure(transfer_id: int, message: str = Query(default="Рейс отменён или не состоялся"), db: Session = Depends(get_db)):
    transfer = db.query(InventoryTransfer).filter(InventoryTransfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(404, "Перемещение не найдено")
    if transfer.status != "READY_ON_ROUTE":
        raise HTTPException(409, "Сообщить о сбое можно только для назначенного рейса")
    transfer.status = "WAITING_ROUTE"
    transfer.route_id = None
    transfer.distance_km = None
    incident = _create_incident(
        db,
        incident_type="ROUTE_FAILURE",
        severity="high",
        message=f"Сбой рейса для перемещения #{transfer.id}: {message}",
        pvz_id=transfer.from_pvz_id,
        transfer_id=transfer.id,
    )
    db.commit()
    return {"transfer_id": transfer.id, "status": transfer.status, "incident_id": incident.id}


@router.post("/network/transfers/{transfer_id}/retry")
def retry_transfer(transfer_id: int, db: Session = Depends(get_db)):
    transfer = db.query(InventoryTransfer).filter(InventoryTransfer.id == transfer_id).first()
    if not transfer:
        raise HTTPException(404, "Перемещение не найдено")
    if transfer.status not in ("WAITING_ROUTE", "READY_ON_ROUTE"):
        raise HTTPException(409, "Повторно назначить можно только ожидающее перемещение")
    from app.network import _refresh_waiting_transfers

    _refresh_waiting_transfers(db)
    db.flush()
    if transfer.status != "READY_ON_ROUTE":
        db.commit()
        raise HTTPException(409, "Подходящий рейс пока не найден; перемещение осталось в очереди")
    incidents = db.query(InventoryIncident).filter(
        InventoryIncident.transfer_id == transfer.id,
        InventoryIncident.status == "OPEN",
        InventoryIncident.incident_type == "ROUTE_FAILURE",
    ).all()
    for incident in incidents:
        incident.status = "RESOLVED"
        incident.resolution_note = f"Повторно назначен рейс #{transfer.route_id}"
        incident.resolved_at = utcnow()
    db.commit()
    return {"transfer_id": transfer.id, "status": transfer.status, "route_id": transfer.route_id}


@router.post("/ops/incidents/{incident_id}/resolve")
def resolve_incident(incident_id: int, body: IncidentResolution, db: Session = Depends(get_db)):
    incident = db.query(InventoryIncident).filter(InventoryIncident.id == incident_id).first()
    if not incident:
        raise HTTPException(404, "Инцидент не найден")
    if incident.status == "RESOLVED":
        raise HTTPException(409, "Инцидент уже закрыт")
    if body.mark_sent_to_seller and incident.stock_item_id:
        item = db.query(StockItem).filter(StockItem.id == incident.stock_item_id).first()
        if item and item.status in ("DAMAGED", "RETURNED", "EXPIRED"):
            _stock_transition(db, item, "TO_SELLER", incident.order_id)
    incident.status = "RESOLVED"
    incident.resolution_note = body.resolution_note
    incident.resolved_at = utcnow()
    db.commit()
    return {"id": incident.id, "status": incident.status}


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Заказ не найден")
    try:
        order.status = transition_order(order.status, "CANCELLED")
    except KeyError as exc:
        raise HTTPException(409, f"Нельзя отменить заказ в статусе {order.status}") from exc

    reservations = db.query(CapacityReservation).filter(
        CapacityReservation.source.like(f"order:{order.id}%")
    ).all()
    for reservation in reservations:
        db.delete(reservation)

    rows = db.query(StockItem).filter(
        StockItem.order_id == order.id,
        StockItem.status.in_(("RESERVED", "ASSEMBLED")),
    ).all()
    if order.reserved_stock_item_id and not rows:
        item = db.query(StockItem).filter(StockItem.id == order.reserved_stock_item_id).first()
        if item and item.status in ("RESERVED", "ASSEMBLED"):
            rows = [item]
    for item in rows:
        if item.status == "ASSEMBLED":
            _stock_transition(db, item, "RESERVED", order.id)
        if item.status == "RESERVED":
            _stock_transition(db, item, "STORED", order.id)
        item.order_id = None
    db.commit()
    return {"order_id": order.id, "status": order.status, "released_stock_lots": len(rows)}


@router.post("/orders/{order_id}/fail")
def mark_order_failed(order_id: int, message: str = Query(default="Не удалось выполнить маршрут"), db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Заказ не найден")
    try:
        order.status = transition_order(order.status, "FAILED_ROUTE")
    except KeyError as exc:
        raise HTTPException(409, f"Нельзя отметить сбой заказа в статусе {order.status}") from exc
    incident = _create_incident(
        db,
        incident_type="ORDER_ROUTE_FAILURE",
        severity="high",
        message=f"Сбой доставки заказа #{order.id}: {message}",
        pvz_id=order.buyer_pvz_id,
        order_id=order.id,
    )
    db.commit()
    return {"order_id": order.id, "status": order.status, "incident_id": incident.id}


def _storage_fee(item: Optional[StockItem], pvz: Optional[PVZ], qty: int) -> float:
    if not item or not pvz:
        return 0.0
    days = max((utcnow() - item.accepted_at).total_seconds() / 86400, 0)
    return round(math.ceil(days) * float(pvz.storage_rate_day or 0) * qty, 2)


def _finance_orders(db: Session, pvz_id: Optional[int]):
    query = db.query(Order)
    if pvz_id is not None:
        query = query.filter(Order.buyer_pvz_id == pvz_id)
    return query.all()


@router.get("/finance/summary")
def finance_summary(pvz_id: Optional[int] = Query(default=None), db: Session = Depends(get_db)):
    if pvz_id is not None and not db.query(PVZ).filter(PVZ.id == pvz_id).first():
        raise HTTPException(404, "ПВЗ не найден")
    orders = _finance_orders(db, pvz_id)
    gross_sales = commission = storage_total = logistics_total = refunds = seller_payout = 0.0
    for order in orders:
        if order.status not in ("ISSUED", "RETURNED"):
            continue
        product = db.query(Product).filter(Product.id == order.product_id).first()
        if not product:
            continue
        seller = db.query(Seller).filter(Seller.id == product.seller_id).first()
        price = float(product.price) * order.qty
        order_refunds = sum(
            row.refund_amount for row in db.query(Return).filter(Return.order_id == order.id).all()
        )
        gross_sales += price
        refunds += order_refunds
        commission_rate = float(seller.commission_rate if seller else 0.15)
        order_commission = max(price - order_refunds, 0) * commission_rate
        commission += order_commission
        stock = db.query(StockItem).filter(StockItem.order_id == order.id).first()
        if not stock and order.reserved_stock_item_id:
            stock = db.query(StockItem).filter(StockItem.id == order.reserved_stock_item_id).first()
        source_pvz = db.query(PVZ).filter(PVZ.id == stock.pvz_id).first() if stock else db.query(PVZ).filter(PVZ.id == order.buyer_pvz_id).first()
        storage = _storage_fee(stock, source_pvz, order.qty)
        storage_total += storage
        payout = max(price - order_refunds, 0) - order_commission - storage
        seller_payout += payout
        if order.chosen_route_id:
            route = db.query(RouteOption).filter(RouteOption.id == order.chosen_route_id).first()
            if route:
                logistics_total += route.cost
    transfer_query = db.query(InventoryTransfer).filter(InventoryTransfer.status == "COMPLETED")
    if pvz_id is not None:
        transfer_query = transfer_query.filter(
            (InventoryTransfer.from_pvz_id == pvz_id) | (InventoryTransfer.to_pvz_id == pvz_id)
        )
    transfer_cost = sum((row.distance_km or 0) * HUB_PER_KM for row in transfer_query.all())
    accrual_query = db.query(Accrual)
    if pvz_id is not None:
        accrual_query = accrual_query.filter(Accrual.pvz_id == pvz_id)
    accrual_rows = accrual_query.all()
    return {
        "pvz_id": pvz_id,
        "orders_count": len([o for o in orders if o.status in ("ISSUED", "RETURNED")]),
        "gross_sales": round(gross_sales, 2),
        "returns_refunded": round(refunds, 2),
        "net_sales": round(gross_sales - refunds, 2),
        "commission": round(commission, 2),
        "storage_fees": round(storage_total, 2),
        "logistics_cost": round(logistics_total + transfer_cost, 2),
        "seller_payout": round(seller_payout, 2),
        "pvz_accruals": round(sum(row.amount for row in accrual_rows), 2),
        "completed_transfers": transfer_query.count(),
        "accruals": [{
            "id": row.id, "type": row.type, "amount": row.amount,
            "pvz_id": row.pvz_id, "order_id": row.order_id,
            "created_at": row.created_at.isoformat(),
        } for row in sorted(accrual_rows, key=lambda x: x.created_at, reverse=True)[:30]],
    }


@router.get("/finance/seller-payouts")
def finance_seller_payouts(db: Session = Depends(get_db)):
    sellers = db.query(Seller).order_by(Seller.name).all()
    result = []
    for seller in sellers:
        products = db.query(Product).filter(Product.seller_id == seller.id).all()
        product_map = {product.id: product for product in products}
        orders = db.query(Order).filter(Order.product_id.in_(product_map.keys())).all() if product_map else []
        gross = commission = storage = refunds = payout = 0.0
        for order in orders:
            if order.status not in ("ISSUED", "RETURNED"):
                continue
            product = product_map[order.product_id]
            amount = product.price * order.qty
            refund = sum(row.refund_amount for row in db.query(Return).filter(Return.order_id == order.id).all())
            gross += amount
            refunds += refund
            fee = max(amount - refund, 0) * seller.commission_rate
            commission += fee
            stock = db.query(StockItem).filter(StockItem.order_id == order.id).first()
            if not stock and order.reserved_stock_item_id:
                stock = db.query(StockItem).filter(StockItem.id == order.reserved_stock_item_id).first()
            pvz = db.query(PVZ).filter(PVZ.id == (stock.pvz_id if stock else order.buyer_pvz_id)).first()
            store_fee = _storage_fee(stock, pvz, order.qty)
            storage += store_fee
            payout += max(amount - refund, 0) - fee - store_fee
        result.append({
            "seller_id": seller.id,
            "seller_name": seller.name,
            "commission_rate": seller.commission_rate,
            "gross_sales": round(gross, 2),
            "refunds": round(refunds, 2),
            "commission": round(commission, 2),
            "storage_fee": round(storage, 2),
            "payout": round(payout, 2),
            "orders_count": len([o for o in orders if o.status in ("ISSUED", "RETURNED")]),
        })
    return result
