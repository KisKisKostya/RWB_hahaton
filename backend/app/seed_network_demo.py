"""Add an idempotent demo network of pickup points and warehouses.

Unlike app.seed, this script never deletes or rewrites existing business data.
Run from backend/: python -m app.seed_network_demo
"""
from app.models import PVZ, RoadEdge, SessionLocal, TruckRoute, TruckRouteStop, init_db

# Coordinates are approximate demo pins, not official WB facility addresses.
# Existing demo seed already creates 3 Kazan PVZ, 2 Moscow PVZ and a Moscow hub.
POINTS = [
  # city, address, lat, lon, capacity, area, height, is_hub
  ("Казань", "ул. Чистопольская, ્પ 26", 55.8208, 49.1280, 95, 28, 2.4, False),
  ("Казань", "ул. Декабристов, 156", 55.8190, 49.0900, 80, 24, 2.3, False),
  ("Йошкар-Ола", "ул. Первомайская, 114", 56.6320, 47.8950, 65, 20, 2.2, False),
  ("Йошкар-Ола", "ул. Кирова, 6", 56.6370, 47.9070, 55, 18, 2.1, False),
  ("Чебоксары", "пр-т Ленина, 7", 56.1430, 47.2480, 75, 22, 2.2, False),
  ("Чебоксары", "ул. Университетская, д 34", 56.1260, 47.2510, 60, 19, 2.1, False),
  ("Нижний Новгород", "ул. Белинского, 36", 56.3100, 44.0050, 100, 30, 2.4, False),
  ("Нижний Новгород", "пр-т Гагарина, д ра 50", 56.2670, 43.9480, 80, 25, 2.2, False),
  ("Самара", "ул. Ленинградская, 29", 53.1950, 50.1000, 90, 27, 2.3, False),
  ("Самара", "Московское шоссе, д 185", 53.2410, 50.2030, 75, 22, 2.2, False),
  ("Санкт-Петербург", "Невский пр-т, 88", 59.9340, 30.3550, 110, 34, 2.5, False),
  ("Санкт-Петербург", "Лиговский пр-т, д 50", 59.9200, 30.3560, 85, 26, 2.3, False),
  ("Екатеринбург", "ул. Малышева, д 51", 56.8370, 60.6050, 100, 30, 2.4, False),
  ("Екатеринбург", "ул. 8 Марта, д 149", 56.8110, 60.6100, 75, 22, 2.2, False),
  ("Казань", "Региональный склад Mesh · Казань", 55.7350, 49.1700, 1800, 950, 8.0, True),
  ("Самара", "Региональный склад Mesh · Самара", 53.2050, 50.2450, 1600, 820, 7.5, True),
  ("Санкт-Петербург", "Региональный склад Mesh · Санкт-Петербург", 59.8700, 30.3000, 2200, 1100, 8.0, True),
  ("Екатеринбург", "Региональный склад Mesh · Екатеринбург", 56.7900, 60.6500, 1700, 900, 8.0, True),
]

def add_if_missing(db, city, address, **kwargs):
  point = db.query(PVZ).filter(PVZ.city == city, PVZ.address == address).first()
  if point:
    return point, False
  point = PVZ(city=city, address=address, **kwargs)
  db.add(point)
  db.flush()
  return point, True


def add_edge(db, a, b, distance):
  exists = db.query(RoadEdge).filter(
    ((RoadEdge.from_pvz_id == a.id) & (RoadEdge.to_pvz_id == b.id))
    | ((RoadEdge.from_pvz_id == b.id) & (RoadEdge.to_pvz_id == a.id))
  ).first()
  if not exists:
    db.add(RoadEdge(
      from_pvz_id=a.id,
      to_pvz_id=b.id,
      distance_km=distance,
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
    locations = {}
    for city, address, lat, lon, capacity, area, height, is_hub in POINTS:
      point, created = add_if_missing(
        db,
        city,
        address,
        latitude=lat,
        longitude=lon,
        capacity_units=capacity,
        reserve_pct=0.15 if is_hub else 0.20,
        peak_factor=1.15 if city in ("Москва", "Санкт-Петербург") else 1.0,
        intake_fee=15.0,
        storage_rate_day=5.0,
        assembly_fee=20.0,
        local_bonus=10.0,
        is_hub=is_hub,
        is_mesh_enabled=True,
        storage_area_m2=area,
        storage_height_m=height,
      )
      locations[(city, address)] = point
      created_points += int(created)

    # Reuse pre-existing seed points by city and hub flag.
    all_points = db.query(PVZ).all()
    hubs = {p.city: p for p in all_points if p.is_hub}
    pvz_by_city = {}
    for point in all_points:
      if not point.is_hub:
        pvz_by_city.setdefault(point.city, []).append(point)

    # Add a regional hub-to-PVZ connection. Smaller neighbouring cities
    # are linked to the Kazan/Nizhny regional trunk in the demo graph.
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
      "Казань": 8, "Йошкар-Ола": 150, "Чебоксары": 160,
      "Нижний Новгород": 390, "Москва": 18, "Самара": 12,
      "Санкт-Петербург": 16, "Екатеринбург": 14,
    }
    for city, points in pvz_by_city.items():
      hub = hub_for_city.get(city)
      if not hub:
        continue
      for index, point in enumerate(points):
        # Existing and newly added points in the same city get
        # plausible local road distances to their regional hub.
        add_edge(db, hub, point, local_distances[city] + index * 2.5)

    # Regional trunk links: all long-distance links are warehouse-to-
    # warehouse; pickup points remain city-local.
    trunk = [
      ("Казань", "Самара", 360),
      ("Казань", "Москва", 820),
      ("Москва", "Санкт-Петербург", 710),
      ("Самара", "Екатеринбург", 800),
    ]
    for city_a, city_b, distance in trunk:
      add_edge(db, hubs[city_a], hubs[city_b], distance)

    # Routes are explicit sequences; duplicate names are skipped.
    for city in ("Казань", "Москва", "Самара", "Санкт-Петербург", "Екатеринбург"):
      hub = hubs[city]
      city_points = sorted(pvz_by_city.get(city, []), key=lambda p: p.id)
      if city_points:
        created_routes += int(add_route(
          db,
          f"Демо · {city} · склад и ПВЗ",
          [hub, *city_points[:4]],
        ))

    for route_name, cities in (
      ("Демо · Казань — Самара — Екатеринбург", ["Казань", "Самара", "Екатеринбург"]),
      ("Демо · Казань — Москва — Санкт-Петербург", ["Казань", "Москва", "Санкт-Петербург"]),
    ):
      created_routes += int(add_route(
        db, route_name, [hubs[city] for city in cities]
      ))

    db.commit()
    total_points = db.query(PVZ).count()
    total_hubs = db.query(PVZ).filter(PVZ.is_hub.is_(True)).count()
    total_edges = db.query(RoadEdge).filter(RoadEdge.is_active.is_(True)).count()
    total_routes = db.query(TruckRoute).count()
    print(
      "Demo network ready: "
      f"new_points={created_points}, total_points={total_points}, "
      f"warehouses={total_hubs}, active_road_edges={total_edges}, "
      f"routes_added={created_routes}, total_routes={total_routes}"
    )
    print("Safe to run again: existing points, roads and routes are preserved.")
  except Exception:
    db.rollback()
    raise
  finally:
    db.close()


if __name__ == "__main__":
  seed_network()
