"""5 routing cases: feasible + reject_reasons from .cursorrules."""
from app.routing import build_hub, build_local, select_route


def _hub(**kw):
    defaults = dict(
        dist=800.0,
        eta_days=2.0,
        price=1000.0,
        qty=1,
        storage_fee=0.0,
        source_pvz_id=99,
        hub_available=True,
    )
    defaults.update(kw)
    return build_hub(**defaults)


def _local(hub, **kw):
    defaults = dict(
        dist=8.0,
        eta_days=0.4,
        price=1000.0,
        qty=1,
        storage_fee=10.0,
        top_flag=True,
        occupied=10,
        incoming=1,
        capacity_units=100,
        reserve_pct=0.20,
        hub_eta=hub["eta_days"],
        hub_marketplace_cost=hub["marketplace_cost"],
        source_pvz_id=1,
        has_stock=True,
    )
    defaults.update(kw)
    return build_local(**defaults)


def test_local_feasible_ok():
    hub = _hub()
    local = _local(hub)
    assert local["feasible"] is True
    assert local["reject_reason"] is None
    assert select_route(local, hub)["type"] == "local"


def test_reject_top_flag_false():
    hub = _hub()
    local = _local(hub, top_flag=False)
    assert local["feasible"] is False
    assert local["reject_reason"] == "top_flag_false"
    assert select_route(local, hub)["type"] == "hub"


def test_reject_no_capacity():
    hub = _hub()
    # usable = 100*0.8=80; occupied+incoming=81
    local = _local(hub, occupied=70, incoming=11)
    assert local["feasible"] is False
    assert local["reject_reason"] == "no_capacity"


def test_reject_eta_local_worse_than_hub():
    hub = _hub(eta_days=2.0)
    # eta_local > hub_eta - 0.5  =>  > 1.5
    local = _local(hub, eta_days=1.6, hub_eta=2.0)
    assert local["feasible"] is False
    assert local["reject_reason"] == "eta_local_worse_than_hub"


def test_reject_marketplace_cost_and_select_hub():
    hub = _hub(dist=10.0, eta_days=2.0)  # cheap hub
    # expensive local: large dist → high cost → marketplace_cost_local > hub
    local = _local(hub, dist=500.0, eta_days=0.4, hub_marketplace_cost=hub["marketplace_cost"])
    assert local["marketplace_cost"] > hub["marketplace_cost"]
    assert local["feasible"] is False
    assert local["reject_reason"] == "marketplace_cost_local_worse"
    chosen = select_route(local, hub)
    assert chosen["type"] == "hub"
    assert chosen["feasible"] is True
