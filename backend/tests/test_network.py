"""Tests for the new network graph and automatic assortment rules."""

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, PVZ, Product, RoadEdge, Seller, StockItem, TruckRoute, TruckRouteStop, WeeklyDemand, utcnow
from app.network import _create_transfer, calculate_assortment, category_volume_limit, shortest_path


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_dijkstra_uses_shortest_road_path(db):
    locations = [
        PVZ(city="Казань", address=f"Пункт {number}", latitude=55.7, longitude=49.1)
        for number in range(1, 4)
    ]
    db.add_all(locations)
    db.flush()
    db.add_all([
        RoadEdge(from_pvz_id=locations[0].id, to_pvz_id=locations[1].id, distance_km=4.5),
        RoadEdge(from_pvz_id=locations[1].id, to_pvz_id=locations[2].id, distance_km=3.0),
        RoadEdge(from_pvz_id=locations[0].id, to_pvz_id=locations[2].id, distance_km=12.0),
    ])
    db.flush()

    path, distance = shortest_path(db, locations[0].id, locations[2].id)

    assert path == [locations[0].id, locations[1].id, locations[2].id]
    assert distance == pytest.approx(7.5)


def test_category_specific_package_volume_limits(db):
    seller = Seller(name="Seller", commission_rate=0.15)
    db.add(seller)
    db.flush()
    clothing = Product(
        seller_id=seller.id, sku="CLOTH-1", name="Футболка",
        price=1000, category="одежда", length_cm=20, width_cm=15, height_cm=5,
    )
    sport = Product(
        seller_id=seller.id, sku="SPORT-1", name="Гантели",
        price=2000, category="спорт", length_cm=100, width_cm=50, height_cm=40,
    )
    db.add_all([clothing, sport])
    db.flush()

    assert category_volume_limit(clothing) == pytest.approx(0.025)
    assert category_volume_limit(sport) == pytest.approx(0.06)


def test_assortment_is_automatic_top_five_and_respects_dimensions(db):
    seller = Seller(name="Seller", commission_rate=0.15)
    pvz = PVZ(
        city="Казань", address="ул. Тестовая, 1",
        storage_area_m2=1, storage_height_m=1,
        capacity_units=100, reserve_pct=0.2,
    )
    db.add_all([seller, pvz])
    db.flush()

    products = []
    for index in range(6):
        oversized = index == 5
        products.append(Product(
            seller_id=seller.id,
            sku=f"SKU-{index}",
            name=f"Товар {index}",
            price=1000,
            category="спорт" if oversized else "одежда",
            length_cm=100 if oversized else 10,
            width_cm=100 if oversized else 10,
            height_cm=100 if oversized else 10,
        ))
    db.add_all(products)
    db.flush()

    week = utcnow() - timedelta(days=7)
    for index, product in enumerate(products):
        db.add(WeeklyDemand(
            pvz_id=pvz.id,
            product_id=product.id,
            week_start=week,
            quantity=60 - index * 5,
        ))
    db.flush()

    result = calculate_assortment(db, pvz, sync_flags=True)

    assert len(result["top_products"]) == 5
    assert result["top_products"][0]["product_id"] == products[0].id
    oversized_candidate = next(row for row in result["candidates"] if row["product_id"] == products[5].id)
    assert oversized_candidate["allocatable_qty"] == 0
    assert "Крупногабаритный" in oversized_candidate["excluded_reason"]


def test_transfer_reserves_exact_stock_amount_and_links_to_route(db):
    seller = Seller(name="Seller", commission_rate=0.15)
    source = PVZ(city="Казань", address="ПВЗ отправления", storage_area_m2=10, storage_height_m=2)
    target = PVZ(city="Казань", address="ПВЗ назначения", storage_area_m2=10, storage_height_m=2)
    db.add_all([seller, source, target])
    db.flush()
    product = Product(
        seller_id=seller.id, sku="TRANSFER-1", name="Товар для рейса",
        price=1000, category="одежда", length_cm=10, width_cm=10, height_cm=10,
    )
    db.add(product)
    db.flush()

    db.add_all([
        StockItem(
            product_id=product.id, pvz_id=source.id, qty=5, status="STORED",
            accepted_at=utcnow() - timedelta(days=2), ttl_days=7,
        ),
        StockItem(
            product_id=product.id, pvz_id=source.id, qty=4, status="STORED",
            accepted_at=utcnow() - timedelta(days=1), ttl_days=7,
        ),
    ])
    db.flush()

    transfer = _create_transfer(
        db, product_id=product.id, qty=7,
        from_id=source.id, to_id=target.id, reason="test",
    )
    db.flush()

    reserved = db.query(StockItem).filter(
        StockItem.pvz_id == source.id,
        StockItem.product_id == product.id,
        StockItem.status == "IN_TRANSFER",
    ).all()
    sellable = db.query(StockItem).filter(
        StockItem.pvz_id == source.id,
        StockItem.product_id == product.id,
        StockItem.status == "STORED",
    ).all()

    assert transfer is not None
    assert transfer.status == "WAITING_ROUTE"
    assert transfer.qty == 7
    assert sum(row.qty for row in reserved) == 7
    assert all(row.transfer_id == transfer.id for row in reserved)
    assert sum(row.qty for row in sellable) == 2
