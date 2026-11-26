"""Seed demo data: PVZ, hub, sellers, products, stock, orders."""
import argparse
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
    "Бутылка Steel",
    "Плед Nordic",
    "Колонка Mini",
    "Пауэрбанк 20K",
    "Кастрюля Stone",
    "Набор контейнеров",
    "Сыворотка Vitamin C",
    "Фен Compact",
    "Эспандер Pro",
    "Сумка Shopper",
]


def clear(db) -> None:
    for table in (
        "inventory_incidents",
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


def seed(reset: bool = False) -> None:
    init_db()
    db = SessionLocal()
    try:
        # Без --reset скрипт никогда не удаляет уже существующие данные.
        existing_pvz = db.query(PVZ).count()
        existing_sellers = db.query(Seller).count()
        if existing_pvz or existing_sellers:
            if not reset:
                print(
                    "База уже содержит данные. Ничего не изменено. "
                    "Для полной перегенерации демо-данных запусти: python -m app.seed --reset"
                )
                return
            clear(db)

        # --- Sellers (6) ---
        sellers = [
            Seller(name="Nord Wear", commission_rate=0.15),
            Seller(name="Gadget House", commission_rate=0.12),
            Seller(name="Home&Co", commission_rate=0.14),
            Seller(name="Beauty Lab", commission_rate=0.18),
            Seller(name="Sport Point", commission_rate=0.13),
            Seller(name="Urban Goods", commission_rate=0.16),
        ]
        db.add_all(sellers)
        db.flush()

        # --- Сеть: 6 ПВЗ в Казани, 5 ПВЗ в Москве и 2 городских склада ---
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
                city="Казань",
                address="ул. Чистопольская, 25",
                capacity_units=75,
                reserve_pct=0.20,
                peak_factor=1.1,
                latitude=55.8210, longitude=49.1280, storage_area_m2=25, storage_height_m=2.2,
            ),
            PVZ(
                city="Казань",
                address="ул. Декабристов, 100",
                capacity_units=65,
                reserve_pct=0.20,
                peak_factor=1.0,
                latitude=55.8200, longitude=49.0950, storage_area_m2=22, storage_height_m=2.1,
            ),
            PVZ(
                city="Казань",
                address="ул. Академика Глушко, 30",
                capacity_units=55,
                reserve_pct=0.22,
                peak_factor=1.0,
                latitude=55.7530, longitude=49.2100, storage_area_m2=19, storage_height_m=2.0,
            ),
            PVZ(
                city="Москва",
                address="Ленинградский просп., 32",
                capacity_units=90,
                reserve_pct=0.20,
                peak_factor=1.2,
                latitude=55.7900, longitude=37.5600, storage_area_m2=32, storage_height_m=2.3,
            ),
            PVZ(
                city="Москва",
                address="Варшавское ш., 26",
                capacity_units=85,
                reserve_pct=0.20,
                peak_factor=1.1,
                latitude=55.6900, longitude=37.6200, storage_area_m2=30, storage_height_m=2.2,
            ),
            PVZ(
                city="Москва",
                address="ул. Профсоюзная, 45",
                capacity_units=75,
                reserve_pct=0.20,
                peak_factor=1.0,
                latitude=55.6700, longitude=37.5600, storage_area_m2=27, storage_height_m=2.1,
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
            PVZ(
                city="Казань",
                address="Промышленная ул., 5 (HUB)",
                capacity_units=1500,
                reserve_pct=0.10,
                peak_factor=1.0,
                is_hub=True,
                latitude=55.7350, longitude=49.1900, is_mesh_enabled=True,
                storage_area_m2=900, storage_height_m=7.0,
            ),
        ]
        db.add_all(pvz_list)
        db.flush()

        kazan = [p for p in pvz_list if p.city == "Казань" and not p.is_hub]
        moscow = [p for p in pvz_list if p.city == "Москва" and not p.is_hub]
        moscow_hub = next(p for p in pvz_list if p.city == "Москва" and p.is_hub)
        kazan_hub = next(p for p in pvz_list if p.city == "Казань" and p.is_hub)
        hub = moscow_hub

        # --- Products (30) ---
        products = []
        for i, name in enumerate(PRODUCT_NAMES):
            seller = sellers[i % len(sellers)]
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

        # --- Городские дорожные графы и рейсы до локальных складов ---
        roads = []
        for locations, local_hub in ((kazan, kazan_hub), (moscow, moscow_hub)):
            # Цепочка городских ПВЗ + отдельное плечо до склада своего города.
            for left, right in zip(locations, locations[1:]):
                roads.append(
                    RoadEdge(
                        from_pvz_id=left.id,
                        to_pvz_id=right.id,
                        distance_km=round(random.uniform(2.5, 9.5), 1),
                    )
                )
            roads.append(
                RoadEdge(
                    from_pvz_id=locations[-1].id,
                    to_pvz_id=local_hub.id,
                    distance_km=round(random.uniform(8.0, 18.0), 1),
                )
            )
        db.add_all(roads)
        db.flush()

        route_specs = [
            ("Казань · городской контур", kazan),
            ("Казань · ПВЗ → склад", [*kazan, kazan_hub]),
            ("Казань · склад → ПВЗ", [kazan_hub, *reversed(kazan)]),
            ("Москва · городской контур", moscow),
            ("Москва · ПВЗ → склад", [*moscow, moscow_hub]),
            ("Москва · склад → ПВЗ", [moscow_hub, *reversed(moscow)]),
        ]
        routes = []
        for route_name, stops in route_specs:
            route = TruckRoute(name=route_name, is_active=True)
            db.add(route)
            db.flush()
            routes.append(route)
            for sequence_no, location in enumerate(stops):
                db.add(
                    TruckRouteStop(
                        route_id=route.id,
                        pvz_id=location.id,
                        sequence_no=sequence_no,
                    )
                )

        customers = []
        customer_names = [
            "Александр Покупатель", "Мария Смирнова", "Иван Петров",
            "Екатерина Волкова", "Дмитрий Соколов", "Анна Кузнецова",
            "Максим Орлов", "Полина Морозова", "Артём Васильев", "Ольга Новикова",
        ]
        for index, name in enumerate(customer_names):
            city = "Казань" if index % 2 == 0 else "Москва"
            locations = kazan if city == "Казань" else moscow
            customer = Customer(
                name=name,
                phone=f"+7 900 100-{index:02d}-{index + 10:02d}",
                email=f"buyer{index + 1}@example.com",
                city=city,
                preferred_pvz_id=locations[index % len(locations)].id,
            )
            db.add(customer)
            customers.append(customer)
        db.flush()

        # --- Заказы (60) с разными покупателями и пунктами выдачи ---
        buyer_cities = ["Казань"] * 36 + ["Москва"] * 24
        random.shuffle(buyer_cities)
        orders = []
        for i in range(60):
            city = buyer_cities[i]
            if city == "Казань":
                buyer_pvz = random.choice(kazan)
                prod = products[i % 8] if i < 20 else products[12 + (i % 8)]
            else:
                buyer_pvz = random.choice(moscow)
                prod = products[8 + (i % 4)] if i % 3 else products[12 + (i % 8)]

            order = Order(
                product_id=prod.id,
                qty=1,
                buyer_city=city,
                buyer_pvz_id=buyer_pvz.id,
                status="CREATED",
                customer_id=random.choice([c for c in customers if c.city == city]).id,
                created_at=now - timedelta(hours=random.randint(1, 120)),
            )
            db.add(order)
            db.flush()
            build_route_options(db, order)
            orders.append(order)

        db.commit()
        print(
            f"Seeded: sellers={len(sellers)}, pvz={len(pvz_list)} "
            f"(hubs=2), products={len(products)}, stock={len(stock_rows)}, "
            f"orders={len(orders)}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Заполнение базы демонстрационными данными Mesh")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="очистить существующие данные перед созданием нового демо-набора",
    )
    seed(reset=parser.parse_args().reset)
