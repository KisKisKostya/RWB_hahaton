"""Add an idempotent demo network of pickup points and warehouses.

Unlike app.seed, this script never deletes or rewrites existing business data.
Run from backend/: python -m app.seed_network_demo
"""
from app.models import PVZ, RoadEdge, SessionLocal, TruckRoute, TruckRouteStop, init_db

# Approximate demo coordinates, not official Wildberries facility addresses.
# The script can run on an empty database or after app.seed.
POINTS = [
    # city, address, latitude, longitude, capacity, area_m2, height_m, is_hub
    ("Казань", "ул. Баумана, 12", 55.7903, 49.1115, 80, 24, 2.2, False),
    ("Казань", "пр. Победы, 45", 55.7655, 49.2202, 60, 20, 2.2, False),
    ("Казань", "ул. Петербургская, 28", 55.7815, 49.1260, 50, 18, 2.0, False),
    ("Казань", "ул. Чистопольская, 26", 55.8208, 49.1280, 95, 28, 2.4, False),
    ("Казань", "ул. Декабристов, 156", 55.8190, 49.0900, 80, 24, 2.3, False),
    ("Москва", "ул. Тверская, 7", 55.7658, 37.6052, 100, 35, 2.3, False),
    ("Москва", "ул. Арбат, 19", 55.7495, 37.5914, 70, 28, 2.2, False),
    ("Москва", "Складской пр., 1 (HUB)", 55.7050, 37.6200, 2000, 1200, 8.0, True),
    ("Йошкар-Ола", "ул. Первомайская, 114", 56.6320, 47.8950, 65, 20, 2.2, False),
    ("Йошкар-Ола", "ул. Кирова, 6", 56.6370, 47.9070, 55, 18, 2.1, False),
    ("Чебоксары", "пр-т Ленина, 7", 56.1430, 47.2480, 75, 22, 2.2, False),
    ("Чебоксары", "ул. Университетская, 34", 56.1260, 47.2510, 60, 19, 2.1, False),
    ("Нижний Новгород", "ул. Белинского, 36", 56.3100, 44.0050, 100, 30, 2.4, False),
    ("Нижний Новгород", "пр-т Гагарина, 50", 56.2670, 43.9480, 80, 25, 2.2, False),
    ("Самара", "ул. Ленинградская, 29", 53.1950, 50.1000, 90, 27, 2.3, False),
    ("Самара", "Московское шоссе, 185", 53.2410, 50.2030, 75, 22, 2.2, False),
    ("Санкт-Петербург", "Невский пр-т, 88", 59.9340, 30.3550, 110, 34, 2.5, False),
    ("Санкт-Петербург", "Лиговский пр-т, 50", 59.9200, 30.3560, 85, 26, 2.3, False),
    ("Екатеринбург", "ул. Малышева, 51", 56.8370, 60.6050, 100, 30, 2.4, False),
    ("Екатеринбург", "ул. 8 Марта, 149", 56.8110, 60.6100, 75, 22, 2.2, False),
    ("Казань", "Региональный склад Mesh · Казань", 55.7350, 49.1700, 1800, 950, 8.0, True),
    ("Самара", "Региональный склад Mesh · Самара", 53.2050, 50.2450, 1600, 820, 7.5, True),
    ("Санкт-Петербург", "Региональный склад Mesh · Санкт-Петербург", 59.8700, 30.3000, 2200, 1100, 8.0, True),
    ("Екатеринбург", "Региональный склад Mesh · Екатеринбург", 56.7900, 60.6500, 1700, 900, 8.0, True),
]


def add_if_missing(db, city, address, **kwargs):
    point = db.query(PVZ).filter(
        PVZ.city == city,
        PVZ.address == address,
    ).first()
    if point:
        return point, False

    point = PVZ(city=city, address=address, **kwargs)
    db.add(point)
    db.flush()
    return point, True


def add_edge(db, point_a, point_b, distance_km):
    exists = db.query(RoadEdge).filter(
        (
            (RoadEdge.from_pvz_id == point_a.id)
            & (RoadEdge.to_pvz_id == point_b.id)
        )
        | (
            (RoadEdge.from_pvz_id == point_b.id)
            & (RoadEdge.to_pvz_id == point_a.id)
        )
    ).first()
    if exists:
        return

    db.add(RoadEdge(
        from_pvz_id=point_a.id,
        to_pvz_id=point_b.id,
        distance_km=distance_km,
        bidirectional=True,
        is_active=True,
    ))


def add_route(db, name, stops):
    if db.query(TruckRoute).filter(TruckRoute.name == name).first():
        return False

    route = TruckRoute(name=name, is_active=True)
    db.add(route)
    db.flush()

    for sequence_no, point in enumerate(stops, start=1):
        db.add(TruckRouteStop(
            route_id=route.id,
            pvz_id=point.id,
            sequence_no=sequence_no,
        ))
    return True


def seed_network():
    init_db()
    db = SessionLocal()
    created_points = 0
    created_routes = 0

    try:
        for (
            city, address, latitude, longitude, capacity,
            area_m2, height_m, is_hub,
        ) in POINTS:
            _, created = add_if_missing(
                db,
                city,
                address,
                latitude=latitude,
                longitude=longitude,
                capacity_units=capacity,
                reserve_pct=0.15 if is_hub else 0.20,
                peak_factor=1.15 if city in ("Москва", "Санкт-Петербург") else 1.0,
                intake_fee=15.0,
                storage_rate_day=5.0,
                assembly_fee=20.0,
                local_bonus=10.0,
                is_hub=is_hub,
                is_mesh_enabled=True,
                storage_area_m2=area_m2,
                storage_height_m=height_m,
            )
            created_points += int(created)

        all_points = db.query(PVZ).all()
        hubs = {point.city: point for point in all_points if point.is_hub}
        pvz_by_city = {}
        for point in all_points:
            if not point.is_hub:
                pvz_by_city.setdefault(point.city, []).append(point)

        hub_for_city = {
            "Казань": hubs["Казань"],
            "Йошкар-Ола": hubs["Казань"],
            "Чебоксары": hubs["Казань"],
            "Нижний Новгород": hubs["Казань"],
            "Москва": hubs["Москва"],
            "Самара": hubs["Самара"],
            "Санкт-Петербург": hubs["Санкт-Петербург"],
            "Екатеринбург": hubs["Екатеринбург"],
        }
        local_distances = {
            "Казань": 8,
            "Йошкар-Ола": 150,
            "Чебоксары": 160,
            "Нижний Новгород": 390,
            "Москва": 18,
            "Самара": 12,
            "Санкт-Петербург": 16,
            "Екатеринбург": 14,
        }

        for city, city_points in pvz_by_city.items():
            hub = hub_for_city.get(city)
            if not hub:
                continue
            for index, point in enumerate(city_points):
                add_edge(db, hub, point, local_distances[city] + index * 2.5)

        # Long-distance connections are warehouse-to-warehouse. No direct
        # intercity PVZ-to-PVZ edges are created.
        trunk = [
            ("Казань", "Самара", 360),
            ("Казань", "Москва", 820),
            ("Москва", "Санкт-Петербург", 710),
            ("Самара", "Екатеринбург", 800),
        ]
        for city_a, city_b, distance_km in trunk:
            add_edge(db, hubs[city_a], hubs[city_b], distance_km)

        for city in ("Казань", "Москва", "Самара", "Санкт-Петербург", "Екатеринбург"):
            hub = hubs[city]
            city_points = sorted(pvz_by_city.get(city, []), key=lambda point: point.id)
            if city_points:
                created_routes += int(add_route(
                    db,
                    f"Демо · {city} · склад и ПВЗ",
                    [hub, *city_points[:4]],
                ))

        intercity_routes = (
            (
                "Демо · Казань — Самара — Екатеринбург",
                ["Казань", "Самара", "Екатеринбург"],
            ),
            (
                "Демо · Казань — Москва — Санкт-Петербург",
                ["Казань", "Москва", "Санкт-Петербург"],
            ),
        )
        for route_name, cities in intercity_routes:
            created_routes += int(add_route(
                db,
                route_name,
                [hubs[city] for city in cities],
            ))

        db.commit()

        print(
            "Demo network ready: "
            f"new_points={created_points}, "
            f"total_points={db.query(PVZ).count()}, "
            f"warehouses={db.query(PVZ).filter(PVZ.is_hub.is_(True)).count()}, "
            f"active_road_edges={db.query(RoadEdge).filter(RoadEdge.is_active.is_(True)).count()}, "
            f"routes_added={created_routes}, "
            f"total_routes={db.query(TruckRoute).count()}"
        )
        print("Safe to run again: existing points, roads and routes are preserved.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_network()
