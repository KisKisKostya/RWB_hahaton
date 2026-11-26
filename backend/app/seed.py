"""Seed demo data: PVZ, hub, sellers, products, stock, orders."""
import random
import sys
from datetime import timedelta
from pathlib import Path

# allow `python -m app.seed` from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import (  # noqa: E402
    Customer,
    InventoryTransfer,
    Order,
    Product,
    PVZ,
    Seller,
    SessionLocal,
    StockItem,
    RoadEdge,
    TruckRoute,
    TruckRouteStop,
    WeeklyDemand,
    init_db,
    utcnow,
)
from app.main import build_route_options  # noqa: E402

random.seed(42)

CATEGORIES = ["одежда", "электроника", "дом", "красота", "спорт"]
PRODUCT_NAMES = [
    "Футболка Basic",
    "Худи Oversize",
    "Наушники Pro",
    "Чехол MagSafe",
    "Кружка Ceramic",
    "Подушка Soft",
    "Крем SPF50",
    "Шампунь Volume",
    "Коврик Yoga",
    "Гантели 5кг",
    "Рюкзак City",
    "Кеды Runner",
    "Лампа LED",
    "Органайзер Desk",
    "Маска тканевая",
    "Термос 0.5",
    "Мышь Wireless",
    "Клавиатура Compact",
    "Шарф Wool",
    "Носки Pack3",
]


def clear(db) -> None:
    for table in (
        "inventory_transfers",
        "truck_route_stops",
        "truck_routes",
        "road_edges",
        "weekly_demand",
        "accruals",
        "returns",
        "capacity_reservations",
        "route_options",
        "orders",
        "customers",
        "stock_items",
        "products",
        "pvz",
        "sellers",
    ):
        db.execute(__import__("sqlalchemy").text(f"DELETE FROM {table}"))
    db.commit()


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        clear(db)

        # --- Sellers (3) ---
        sellers = [
            Seller(name="Seller Alpha", commission_rate=0.15),
            Seller(name="Seller Beta", commission_rate=0.12),
            Seller(name="Seller Gamma", commission_rate=0.18),
        ]
        db.add_all(sellers)
        db.flush()

        # --- PVZ: 3 Казань, 2 Москва, 1 хаб Москва ---
        pvz_list = [
            PVZ(
                city="Казань",
                address="ул. Баумана, 12",
                capacity_units=80,
                reserve_pct=0.20,
                peak_factor=1.1,
                latitude=55.7903, longitude=49.1115, storage_area_m2=24, storage_height_m=2.2,
            ),
            PVZ(
                city="Казань",
                address="пр. Победы, 45",
                capacity_units=60,
                reserve_pct=0.20,
                peak_factor=1.0,
                latitude=55.7655, longitude=49.2202, storage_area_m2=20, storage_height_m=2.2,
            ),
            PVZ(
                city="Казань",
                address="ул. Петербургская, 28",
                capacity_units=50,
                reserve_pct=0.25,
                peak_factor=1.2,
                latitude=55.7815, longitude=49.1260, storage_area_m2=18, storage_height_m=2.0,
            ),
            PVZ(
                city="Москва",
                address="ул. Тверская, 7",
                capacity_units=100,
                reserve_pct=0.20,
                peak_factor=1.3,
                latitude=55.7658, longitude=37.6052, storage_area_m2=35, storage_height_m=2.3,
            ),
            PVZ(
                city="Москва",
                address="ул. Арбат, 19",
                capacity_units=70,
                reserve_pct=0.20,
                peak_factor=1.1,
                latitude=55.7495, longitude=37.5914, storage_area_m2=28, storage_height_m=2.2,
            ),
            PVZ(
                city="Москва",
                address="Складской пр., 1 (HUB)",
                capacity_units=2000,
                reserve_pct=0.10,
                peak_factor=1.0,
                is_hub=True,
                latitude=55.705, longitude=37.62, is_mesh_enabled=True,
                storage_area_m2=1200, storage_height_m=8.0,
            ),
        ]
        db.add_all(pvz_list)
        db.flush()

        kazan = [p for p in pvz_list if p.city == "Казань"]
        moscow = [p for p in pvz_list if p.city == "Москва" and not p.is_hub]
        hub = next(p for p in pvz_list if p.is_hub)

        # --- Products (20) ---
        products = []
        for i, name in enumerate(PRODUCT_NAMES):
            seller = sellers[i % 3]
            products.append(
                Product(
                    seller_id=seller.id,
                    sku=f"SKU-{1000 + i}",
                    name=name,
                    price=round(random.uniform(299, 7990), 2),
                    category=CATEGORIES[i % len(CATEGORIES)],
                    length_cm=(65 if "Гантели" in name else 30 if CATEGORIES[i % len(CATEGORIES)] == "одежда" else 25 if CATEGORIES[i % len(CATEGORIES)] == "электроника" else 22 if CATEGORIES[i % len(CATEGORIES)] == "красота" else 35),
                    width_cm=(45 if "Гантели" in name else 25 if CATEGORIES[i % len(CATEGORIES)] == "одежда" else 18 if CATEGORIES[i % len(CATEGORIES)] == "электроника" else 12 if CATEGORIES[i % len(CATEGORIES)] == "красота" else 25),
                    height_cm=(35 if "Гантели" in name else 5 if CATEGORIES[i % len(CATEGORIES)] == "одежда" else 10 if CATEGORIES[i % len(CATEGORIES)] == "электроника" else 8 if CATEGORIES[i % len(CATEGORIES)] == "красота" else 20),
                )
            )
        db.add_all(products)
        db.flush()

        # --- Stock: local TOP + hub + edge cases ---
        now = utcnow()
        stock_rows = []

        # city_local: TOP stock in Kazan for first 8 products
        for i, prod in enumerate(products[:8]):
            pvz = kazan[i % len(kazan)]
            stock_rows.append(
                StockItem(
                    product_id=prod.id,
                    pvz_id=pvz.id,
                    qty=random.randint(2, 8),
                    status="STORED",
                    accepted_at=now - timedelta(days=random.randint(1, 5)),
                    ttl_days=7,
                    storage_deadline=now + timedelta(days=7),
                    top_flag=True,
                    last_top_check=now - timedelta(days=1),
                )
            )

        # Moscow local TOP for next 4
        for i, prod in enumerate(products[8:12]):
            pvz = moscow[i % len(moscow)]
            stock_rows.append(
                StockItem(
                    product_id=prod.id,
                    pvz_id=pvz.id,
                    qty=random.randint(2, 6),
                    status="STORED",
                    accepted_at=now - timedelta(days=random.randint(1, 4)),
                    ttl_days=7,
                    storage_deadline=now + timedelta(days=7),
                    top_flag=True,
                    last_top_check=now,
                )
            )

        # hub_magistral: stock only at hub for products 12-15
        for prod in products[12:16]:
            stock_rows.append(
                StockItem(
                    product_id=prod.id,
                    pvz_id=hub.id,
                    qty=random.randint(5, 20),
                    status="STORED",
                    accepted_at=now - timedelta(days=2),
                    ttl_days=14,
                    storage_deadline=now + timedelta(days=14),
                    top_flag=False,
                    last_top_check=None,
                )
            )

        # long_storage / expired TOP for product 16
        stock_rows.append(
            StockItem(
                product_id=products[16].id,
                pvz_id=kazan[0].id,
                qty=3,
                status="STORED",
                accepted_at=now - timedelta(days=20),
                ttl_days=7,
                storage_deadline=now - timedelta(days=5),
                top_flag=True,
                last_top_check=now - timedelta(days=10),
            )
        )

        # no_capacity: fill one small Kazan PVZ almost full (non-TOP filler)
        filler_pvz = kazan[2]  # capacity 50
        stock_rows.append(
            StockItem(
                product_id=products[17].id,
                pvz_id=filler_pvz.id,
                qty=38,
                status="STORED",
                accepted_at=now - timedelta(days=3),
                ttl_days=10,
                storage_deadline=now + timedelta(days=10),
                top_flag=False,
                last_top_check=None,
            )
        )

        # remaining products at hub
        for prod in products[18:]:
            stock_rows.append(
                StockItem(
                    product_id=prod.id,
                    pvz_id=hub.id,
                    qty=10,
                    status="STORED",
                    accepted_at=now - timedelta(days=1),
                    ttl_days=14,
                    storage_deadline=now + timedelta(days=14),
                    top_flag=False,
                )
            )

        db.add_all(stock_rows)
        db.flush()

        # --- Weekly purchase history: batch demand by PVZ and product ---
        week_start = now - timedelta(days=now.weekday() + 7)
        for location in kazan:
            for index, product in enumerate(products):
                qty = max(0, 28 - index * 3) if product.id <= 8 else (8 if index % 3 == 0 else 2)
                db.add(WeeklyDemand(pvz_id=location.id, product_id=product.id, week_start=week_start, quantity=qty))
        for location in moscow:
            for index, product in enumerate(products):
                qty = max(0, 24 - (index - 8) * 4) if 8 <= product.id <= 12 else (6 if index % 4 == 0 else 1)
                db.add(WeeklyDemand(pvz_id=location.id, product_id=product.id, week_start=week_start, quantity=qty))

        # TOP flags are generated by the same demand/volume algorithm used in production.
        from app.network import calculate_assortment
        for location in pvz_list:
            if not location.is_hub:
                calculate_assortment(db, location, sync_flags=True)
        db.flush()

        # --- Road graph and active line-haul truck routes ---
        roads = [
            RoadEdge(from_pvz_id=1, to_pvz_id=2, distance_km=4.5),
            RoadEdge(from_pvz_id=2, to_pvz_id=3, distance_km=6.2),
            RoadEdge(from_pvz_id=1, to_pvz_id=3, distance_km=3.8),
            RoadEdge(from_pvz_id=4, to_pvz_id=5, distance_km=4.2),
            RoadEdge(from_pvz_id=4, to_pvz_id=6, distance_km=18.0),
            RoadEdge(from_pvz_id=5, to_pvz_id=6, distance_km=20.0),
            RoadEdge(from_pvz_id=3, to_pvz_id=6, distance_km=790.0),
        ]
        db.add_all(roads)
        db.flush()
        kazan_route = TruckRoute(name="Казань · городской контур", is_active=True)
        moscow_route = TruckRoute(name="Москва · ПВЗ — склад", is_active=True)
        long_route = TruckRoute(name="Межрегиональный рейс", is_active=True)
        db.add_all([kazan_route, moscow_route, long_route])
        db.flush()
        for route, stops in (
            (kazan_route, [1, 2, 3]),
            (moscow_route, [4, 5, 6]),
            (long_route, [6, 3, 1, 2]),
        ):
            for order_no, location_id in enumerate(stops):
                db.add(TruckRouteStop(route_id=route.id, pvz_id=location_id, sequence_no=order_no))

        default_customer = Customer(
            name="Александр Покупатель",
            phone="+7 900 000-00-00",
            email="customer@example.com",
            city="Казань",
            preferred_pvz_id=kazan[0].id,
        )
        db.add(default_customer)
        db.flush()

        # --- Orders (30) ---
        buyer_cities = ["Казань"] * 18 + ["Москва"] * 12
        random.shuffle(buyer_cities)
        orders = []
        for i in range(30):
            city = buyer_cities[i]
            if city == "Казань":
                buyer_pvz = random.choice(kazan)
                # prefer products with local stock for first half
                prod = products[i % 8] if i < 15 else products[12 + (i % 4)]
            else:
                buyer_pvz = random.choice(moscow)
                prod = products[8 + (i % 4)] if i % 3 else products[12 + (i % 4)]

            order = Order(
                product_id=prod.id,
                qty=1,
                buyer_city=city,
                buyer_pvz_id=buyer_pvz.id,
                status="CREATED",
                created_at=now - timedelta(hours=random.randint(1, 72)),
            )
            db.add(order)
            db.flush()
            build_route_options(db, order)
            orders.append(order)

        db.commit()
        print(
            f"Seeded: sellers={len(sellers)}, pvz={len(pvz_list)} "
            f"(hub=1), products={len(products)}, stock={len(stock_rows)}, "
            f"orders={len(orders)}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
