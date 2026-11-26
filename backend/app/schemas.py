"""Pydantic request/response schemas."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# --- Seller ---
class SellerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    commission_rate: float


# --- PVZ ---
class PVZOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    city: str
    address: str
    capacity_units: int
    reserve_pct: float
    peak_factor: float
    intake_fee: float
    storage_rate_day: float
    assembly_fee: float
    local_bonus: float
    is_hub: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_mesh_enabled: bool = True
    storage_area_m2: float = 20.0
    storage_height_m: float = 2.0


class CapacityOut(BaseModel):
    pvz_id: int
    capacity_units: int
    occupied: int
    reserved: int
    incoming: int
    free: int
    usable_limit: int
    capacity_ok: bool


# --- Product ---
class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seller_id: int
    sku: str
    name: str
    price: float
    category: str
    length_cm: float = 10.0
    width_cm: float = 10.0
    height_cm: float = 10.0


# --- Stock ---
class IntakeIn(BaseModel):
    product_id: int
    qty: int = Field(ge=1)
    top_flag: bool = False
    ttl_days: Optional[int] = None


class StockItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    pvz_id: int
    qty: int
    status: str
    accepted_at: datetime
    ttl_days: int
    storage_deadline: Optional[datetime]
    top_flag: bool
    last_top_check: Optional[datetime]


class RelocateIn(BaseModel):
    target_pvz_id: int
    reason: str = "manual"


# --- Order ---
class OrderCreate(BaseModel):
    product_id: int
    qty: int = Field(ge=1, default=1)
    buyer_city: str
    buyer_pvz_id: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    qty: int
    buyer_city: str
    buyer_pvz_id: int
    status: str
    chosen_route_id: Optional[int]
    created_at: datetime


class RouteSelectIn(BaseModel):
    route_id: int


class RouteOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    type: str
    cost: float
    eta_days: float
    distance_km: float
    pvz_income: float
    marketplace_margin: float
    seller_payout: float
    feasible: bool
    reject_reason: Optional[str]
    source_pvz_id: Optional[int]


# --- Return ---
class ReturnIn(BaseModel):
    reason: str
    condition: str = Field(pattern="^(intact|damaged)$")


class ReturnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_id: int
    reason: str
    condition: str
    decision: str
    created_at: datetime


# --- Accrual / Payout ---
class AccrualOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pvz_id: int
    order_id: Optional[int]
    stock_item_id: Optional[int]
    type: str
    amount: float
    created_at: datetime


class SellerPayoutOut(BaseModel):
    seller_id: int
    order_id: int
    product_id: int
    price: float
    commission: float
    storage_fee: float
    payout: float
    status: str


# --- Analytics ---
class CompareOut(BaseModel):
    order_id: int
    local: Optional[RouteOptionOut]
    hub: Optional[RouteOptionOut]
    recommended: Optional[str]
    delta_cost: Optional[float]
    delta_eta: Optional[float]
    delta_margin: Optional[float]


class SensitivityOut(BaseModel):
    param: str
    base_value: float
    sweeps: list[dict]
