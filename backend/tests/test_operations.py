"""Regression tests for returns, operational incidents and integrated finance."""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import (
    Accrual,
    Base,
    CapacityReservation,
    InventoryIncident,
    InventoryTransfer,
    Order,
    Product,
    PVZ,
    Return,
    RoadEdge,
    Seller,
    StockItem,
    TruckRoute,
    TruckRouteStop,
    utcnow,
)
from app.operations import (
    IncidentResolution,
    ReturnRequest,
    _release_order_holds,
    finance_seller_payouts,
    finance_summary,
    process_return,
    report_transfer_failure,
    resolve_incident,
)
from app.routing import build_hub


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def make_order(db, *, qty=1, price=1000.0, pvz=None, commission=0.12, status="ISSUED"):
    seller = Seller(name="Seller Test", commission_rate=commission)
    db.add(seller)
    db.flush()
    pvz = pvz or PVZ(
        city="Казань",
        address="Тестовый ПВЗ",
        capacity_units=100,
        reserve_pct=0.0,
        storage_area_m2=10,
        storage_height_m=2,
        storage_rate_day=0,
        is_mesh_enabled=True,
    )
    db.add(pvz)
    db.flush()
    product = Product(
        seller_id=seller.id,
        sku=f"SKU-{seller.id}",
        name="Тестовый товар",
        price=price,
        category="дом",
        length_cm=10,
        width_cm=10,
        height_cm=10,
    )
    db.add(product)
    db.flush()
    order = Order(
        product_id=product.id,
        qty=qty,
        buyer_city=pvz.city,
        buyer_pvz_id=pvz.id,
        status=status,
    )
    db.add(order)
    db.flush()
    return seller, pvz, product, order


def test_return_splits_exact_quantity_across_lots_and_reverses_revenue(db):
    _, pvz, product, order = make_order(db, qty=2, price=999)
    first = StockItem(
        product_id=product.id, pvz_id=pvz.id, qty=1, status="ISSUED",
        accepted_at=utcnow() - timedelta(days=1), ttl_days=7, order_id=order.id,
    )
    second = StockItem(
        product_id=product.id, pvz_id=pvz.id, qty=3, status="ISSUED",
        accepted_at=utcnow() - timedelta(days=2), ttl_days=7, order_id=order.id,
    )
    db.add_all([first, second])
    db.flush()
    order.reserved_stock_item_id = first.id

    result = process_return(
        db,
        order,
        ReturnRequest(reason="Не подошёл размер", condition="intact"),
    )
    db.flush()

    returned = db.query(StockItem).filter(
        StockItem.order_id == order.id,
        StockItem.status == "STORED",
    ).all()
    leftover = db.query(StockItem).filter(
        StockItem.id == second.id,
    ).first()
    refund_entry = db.query(Accrual).filter(
        Accrual.order_id == order.id,
        Accrual.type == "return_refund",
    ).one()

    assert order.status == "RETURNED"
    assert result.refund_amount == pytest.approx(1998.0)
    assert result.status == "PROCESSED"
    assert sum(row.qty for row in returned) == 2
    assert leftover.qty == 2
    assert leftover.order_id is None
    assert leftover.status == "ISSUED"
    assert refund_entry.amount == pytest.approx(-1998.0)


def test_damaged_return_creates_incident_and_excludes_stock_from_sale(db):
    _, pvz, product, order = make_order(db)
    stock = StockItem(
        product_id=product.id, pvz_id=pvz.id, qty=1, status="ISSUED",
        accepted_at=utcnow(), ttl_days=7, order_id=order.id,
    )
    db.add(stock)
    db.flush()
    order.reserved_stock_item_id = stock.id

    result = process_return(
        db,
        order,
        ReturnRequest(reason="Повреждена упаковка", condition="damaged"),
    )
    db.flush()

    incident = db.query(InventoryIncident).filter(
        InventoryIncident.order_id == order.id,
        InventoryIncident.incident_type == "DAMAGED_RETURN",
    ).one()
    assert result.decision == "to_seller"
    assert result.status == "WAITING_SELLER"
    assert stock.status == "DAMAGED"
    assert incident.status == "OPEN"


def test_intact_return_goes_to_hub_on_existing_route_when_buyer_pvz_is_full(db):
    buyer = PVZ(
        city="Казань", address="ПВЗ отправления", capacity_units=1, reserve_pct=0,
        storage_area_m2=0.001, storage_height_m=1, is_mesh_enabled=True,
    )
    _, _, product, order = make_order(db, qty=1, pvz=buyer)
    filler = StockItem(
        product_id=product.id, pvz_id=buyer.id, qty=1, status="STORED",
        accepted_at=utcnow(), ttl_days=7,
    )
    issued = StockItem(
        product_id=product.id, pvz_id=buyer.id, qty=1, status="ISSUED",
        accepted_at=utcnow(), ttl_days=7, order_id=order.id,
    )
    hub = PVZ(
        city="Казань", address="Хаб", capacity_units=1000, reserve_pct=0.1,
        storage_area_m2=100, storage_height_m=5, is_hub=True, is_mesh_enabled=True,
    )
    db.add_all([filler, issued, hub])
    db.flush()
    order.reserved_stock_item_id = issued.id
    db.add(RoadEdge(
        from_pvz_id=buyer.id, to_pvz_id=hub.id, distance_km=5.0, bidirectional=True,
    ))
    route = TruckRoute(name="Казань — хаб", is_active=True)
    db.add(route)
    db.flush()
    db.add_all([
        TruckRouteStop(route_id=route.id, pvz_id=buyer.id, sequence_no=0),
        TruckRouteStop(route_id=route.id, pvz_id=hub.id, sequence_no=1),
    ])
    db.flush()

    result = process_return(
        db,
        order,
        ReturnRequest(reason="Покупатель передумал", condition="intact"),
    )
    db.flush()
    transfer = db.query(InventoryTransfer).filter(
        InventoryTransfer.reason == "returned_stock_rebalance",
    ).one()

    assert result.decision == "relocate"
    assert result.status == "WAITING_TRANSFER"
    assert transfer.status == "READY_ON_ROUTE"
    assert transfer.route_id == route.id
    assert issued.status == "IN_TRANSFER"
    assert issued.transfer_id == transfer.id


def test_resolving_damaged_return_marks_all_linked_lots_as_sent(db):
    _, pvz, product, order = make_order(db, qty=2)
    rows = [
        StockItem(product_id=product.id, pvz_id=pvz.id, qty=1, status="DAMAGED", accepted_at=utcnow(), ttl_days=7, order_id=order.id)
        for _ in range(2)
    ]
    db.add_all(rows)
    db.flush()
    incident = InventoryIncident(
        incident_type="DAMAGED_RETURN", severity="high", status="OPEN",
        message="Отправить продавцу", pvz_id=pvz.id, order_id=order.id,
        stock_item_id=rows[0].id,
    )
    db.add(incident)
    db.flush()

    resolve_incident(
        incident.id,
        IncidentResolution(resolution_note="Передано продавцу по акту", mark_sent_to_seller=True),
        db,
    )

    assert all(row.status == "TO_SELLER" for row in rows)
    assert incident.status == "RESOLVED"


def test_cancel_helper_releases_capacity_and_restores_reserved_lots(db):
    _, pvz, product, order = make_order(db, status="RESERVED")
    stock = StockItem(
        product_id=product.id, pvz_id=pvz.id, qty=2, status="RESERVED",
        accepted_at=utcnow(), ttl_days=7, order_id=order.id,
    )
    db.add(stock)
    db.flush()
    order.reserved_stock_item_id = stock.id
    db.add(CapacityReservation(
        pvz_id=pvz.id, units=2, source=f"order:{order.id}",
        expires_at=utcnow() + timedelta(days=1),
    ))
    db.flush()

    released = _release_order_holds(db, order)

    assert released == 1
    assert stock.status == "STORED"
    assert stock.order_id is None
    assert db.query(CapacityReservation).filter(
        CapacityReservation.source == f"order:{order.id}",
    ).count() == 0


def test_transfer_failure_creates_persistent_incident_and_requeues_goods(db):
    seller, source, product, order = make_order(db)
    target = PVZ(
        city="Казань", address="ПВЗ назначения", capacity_units=100,
        reserve_pct=0, storage_area_m2=10, storage_height_m=2, is_mesh_enabled=True,
    )
    route = TruckRoute(name="Рейс", is_active=True)
    db.add_all([target, route])
    db.flush()
    transfer = InventoryTransfer(
        product_id=product.id, qty=1, from_pvz_id=source.id, to_pvz_id=target.id,
        route_id=route.id, status="READY_ON_ROUTE", distance_km=10, reason="test",
    )
    db.add(transfer)
    db.flush()

    result = report_transfer_failure(transfer.id, "Машина сломалась", db)
    db.flush()
    incident = db.query(InventoryIncident).filter(
        InventoryIncident.id == result["incident_id"],
    ).one()

    assert transfer.status == "WAITING_ROUTE"
    assert transfer.route_id is None
    assert incident.status == "OPEN"
    assert incident.transfer_id == transfer.id


def test_finance_summary_and_seller_payout_use_sellers_own_commission(db):
    seller, pvz, product, order = make_order(db, qty=2, price=1000, commission=0.12, status="RETURNED")
    stock = StockItem(
        product_id=product.id, pvz_id=pvz.id, qty=2, status="ISSUED",
        accepted_at=utcnow(), ttl_days=7, order_id=order.id,
    )
    db.add(stock)
    db.flush()
    order.reserved_stock_item_id = stock.id
    db.add(Return(
        order_id=order.id, reason="Частичный возврат", condition="intact",
        decision="keep", stock_item_id=stock.id, refund_amount=500, status="PROCESSED",
    ))
    db.flush()

    summary = finance_summary(pvz_id=None, db=db)
    payouts = finance_seller_payouts(db=db)
    payout = next(row for row in payouts if row["seller_id"] == seller.id)

    assert summary["gross_sales"] == pytest.approx(2000)
    assert summary["returns_refunded"] == pytest.approx(500)
    assert summary["net_sales"] == pytest.approx(1500)
    assert summary["commission"] == pytest.approx(180)
    assert summary["seller_payout"] == pytest.approx(1320)
    assert payout["commission_rate"] == pytest.approx(0.12)
    assert payout["payout"] == pytest.approx(1320)


def test_route_financials_accept_a_per_seller_commission_rate():
    result = build_hub(
        dist=100,
        eta_days=1,
        price=1000,
        commission_rate=0.12,
        hub_available=True,
    )
    assert result["marketplace_margin"] == pytest.approx(120 - result["cost"] - result["pvz_income"])
    assert result["seller_payout"] == pytest.approx(880)
