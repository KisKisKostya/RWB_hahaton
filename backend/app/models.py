"""SQLAlchemy models + SQLite engine."""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = "sqlite:///./mesh.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Seller(Base):
    __tablename__ = "sellers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    commission_rate = Column(Float, nullable=False, default=0.15)

    products = relationship("Product", back_populates="seller")


class PVZ(Base):
    __tablename__ = "pvz"

    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, nullable=False)
    address = Column(String, nullable=False)
    capacity_units = Column(Integer, nullable=False, default=100)
    reserve_pct = Column(Float, nullable=False, default=0.20)
    peak_factor = Column(Float, nullable=False, default=1.0)
    intake_fee = Column(Float, nullable=False, default=15.0)
    storage_rate_day = Column(Float, nullable=False, default=5.0)
    assembly_fee = Column(Float, nullable=False, default=20.0)
    local_bonus = Column(Float, nullable=False, default=10.0)
    is_hub = Column(Boolean, nullable=False, default=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_mesh_enabled = Column(Boolean, nullable=False, default=True)
    storage_area_m2 = Column(Float, nullable=False, default=20.0)
    storage_height_m = Column(Float, nullable=False, default=2.0)

    stock_items = relationship("StockItem", back_populates="pvz")
    accruals = relationship("Accrual", back_populates="pvz")
    reservations = relationship("CapacityReservation", back_populates="pvz")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("sellers.id"), nullable=False)
    sku = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    length_cm = Column(Float, nullable=False, default=10.0)
    width_cm = Column(Float, nullable=False, default=10.0)
    height_cm = Column(Float, nullable=False, default=10.0)

    seller = relationship("Seller", back_populates="products")
    stock_items = relationship("StockItem", back_populates="product")
    orders = relationship("Order", back_populates="product")


class StockItem(Base):
    __tablename__ = "stock_items"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False)
    qty = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="ACCEPTED")
    accepted_at = Column(DateTime, nullable=False, default=utcnow)
    ttl_days = Column(Integer, nullable=False, default=7)
    storage_deadline = Column(DateTime, nullable=True)
    top_flag = Column(Boolean, nullable=False, default=False)
    last_top_check = Column(DateTime, nullable=True)
    transfer_id = Column(Integer, ForeignKey("inventory_transfers.id"), nullable=True)

    product = relationship("Product", back_populates="stock_items")
    pvz = relationship("PVZ", back_populates="stock_items")
    accruals = relationship("Accrual", back_populates="stock_item")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    qty = Column(Integer, nullable=False, default=1)
    buyer_city = Column(String, nullable=False)
    buyer_pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False)
    status = Column(String, nullable=False, default="CREATED")
    chosen_route_id = Column(Integer, nullable=True)  # RouteOption.id, no FK (cycle)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    reserved_stock_item_id = Column(Integer, ForeignKey("stock_items.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    product = relationship("Product", back_populates="orders")
    buyer_pvz = relationship("PVZ", foreign_keys=[buyer_pvz_id])
    routes = relationship(
        "RouteOption",
        back_populates="order",
        foreign_keys="RouteOption.order_id",
    )
    returns = relationship("Return", back_populates="order")
    accruals = relationship("Accrual", back_populates="order")


class RouteOption(Base):
    __tablename__ = "route_options"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    type = Column(String, nullable=False)  # local | hub
    cost = Column(Float, nullable=False)
    eta_days = Column(Float, nullable=False)
    distance_km = Column(Float, nullable=False)
    pvz_income = Column(Float, nullable=False)
    marketplace_margin = Column(Float, nullable=False)
    seller_payout = Column(Float, nullable=False)
    feasible = Column(Boolean, nullable=False, default=True)
    reject_reason = Column(String, nullable=True)
    source_pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=True)

    order = relationship("Order", back_populates="routes", foreign_keys=[order_id])
    source_pvz = relationship("PVZ", foreign_keys=[source_pvz_id])


class Accrual(Base):
    __tablename__ = "accruals"

    id = Column(Integer, primary_key=True, index=True)
    pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    stock_item_id = Column(Integer, ForeignKey("stock_items.id"), nullable=True)
    type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)

    pvz = relationship("PVZ", back_populates="accruals")
    order = relationship("Order", back_populates="accruals")
    stock_item = relationship("StockItem", back_populates="accruals")


class Return(Base):
    __tablename__ = "returns"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    reason = Column(String, nullable=False)
    condition = Column(String, nullable=False)  # intact | damaged
    decision = Column(String, nullable=False)  # keep | relocate | to_seller
    created_at = Column(DateTime, nullable=False, default=utcnow)

    order = relationship("Order", back_populates="returns")


class CapacityReservation(Base):
    __tablename__ = "capacity_reservations"

    id = Column(Integer, primary_key=True, index=True)
    pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False)
    units = Column(Integer, nullable=False)
    source = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    pvz = relationship("PVZ", back_populates="reservations")



class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, default="Покупатель")
    phone = Column(String, nullable=False, default="")
    email = Column(String, nullable=False, default="")
    city = Column(String, nullable=False, default="Казань")
    preferred_pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class WeeklyDemand(Base):
    __tablename__ = "weekly_demand"

    id = Column(Integer, primary_key=True, index=True)
    pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    week_start = Column(DateTime, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class RoadEdge(Base):
    __tablename__ = "road_edges"

    id = Column(Integer, primary_key=True, index=True)
    from_pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False, index=True)
    to_pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False, index=True)
    distance_km = Column(Float, nullable=False)
    bidirectional = Column(Boolean, nullable=False, default=True)
    is_active = Column(Boolean, nullable=False, default=True)


class TruckRoute(Base):
    __tablename__ = "truck_routes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=utcnow)


class TruckRouteStop(Base):
    __tablename__ = "truck_route_stops"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("truck_routes.id"), nullable=False, index=True)
    pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False)
    sequence_no = Column(Integer, nullable=False)


class InventoryTransfer(Base):
    __tablename__ = "inventory_transfers"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    qty = Column(Integer, nullable=False)
    from_pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False)
    to_pvz_id = Column(Integer, ForeignKey("pvz.id"), nullable=False)
    route_id = Column(Integer, ForeignKey("truck_routes.id"), nullable=True)
    status = Column(String, nullable=False, default="WAITING_ROUTE")
    distance_km = Column(Float, nullable=True)
    reason = Column(String, nullable=False, default="demand_rebalance")
    created_at = Column(DateTime, nullable=False, default=utcnow)
    completed_at = Column(DateTime, nullable=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    # Lightweight SQLite migrations keep existing hackathon demo databases usable.
    migrations = {
        "pvz": {
            "latitude": "FLOAT",
            "longitude": "FLOAT",
            "is_mesh_enabled": "BOOLEAN NOT NULL DEFAULT 1",
            "storage_area_m2": "FLOAT NOT NULL DEFAULT 20.0",
            "storage_height_m": "FLOAT NOT NULL DEFAULT 2.0",
        },
        "products": {
            "length_cm": "FLOAT NOT NULL DEFAULT 10.0",
            "width_cm": "FLOAT NOT NULL DEFAULT 10.0",
            "height_cm": "FLOAT NOT NULL DEFAULT 10.0",
        },
        "stock_items": {
            "transfer_id": "INTEGER REFERENCES inventory_transfers(id)",
        },
        "orders": {
            "customer_id": "INTEGER REFERENCES customers(id)",
            "reserved_stock_item_id": "INTEGER REFERENCES stock_items(id)",
        },
    }
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in migrations.items():
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, sql_type in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
