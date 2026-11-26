"""Lifecycle transitions + accruals; illegal → KeyError."""
import pytest

from app.accruals import make_intake_accrual, make_status_accrual
from app.lifecycle import (
    ORDER_TRANSITIONS,
    STOCK_TRANSITIONS,
    transition_order,
    transition_stock,
)
from app.tariffs import INTAKE_FEE


def test_order_happy_path():
    status = "CREATED"
    for nxt in (
        "ROUTE_SELECTED",
        "RESERVED",
        "ASSEMBLED",
        "IN_TRANSIT",
        "READY",
        "ISSUED",
        "RETURNED",
    ):
        status = transition_order(status, nxt)
    assert status == "RETURNED"


def test_order_illegal_raises_keyerror():
    with pytest.raises(KeyError, match="illegal order transition"):
        transition_order("CREATED", "ISSUED")
    with pytest.raises(KeyError, match="illegal order transition"):
        transition_order("ISSUED", "CREATED")
    with pytest.raises(KeyError):
        transition_order("UNKNOWN", "CREATED")


def test_stock_happy_path_writes_accrual():
    status = "ACCEPTED"
    accruals = []
    for nxt, amount in (
        ("STORED", 0.0),
        ("RESERVED", 0.0),
        ("ASSEMBLED", 20.0),
        ("ISSUED", 0.0),
    ):
        status, acc = transition_stock(
            status,
            nxt,
            pvz_id=1,
            stock_item_id=10,
            order_id=5,
            amount=amount,
        )
        assert acc is not None
        assert acc["type"] == f"status:{nxt}"
        assert acc["pvz_id"] == 1
        assert acc["amount"] == amount
        accruals.append(acc)
    assert status == "ISSUED"
    assert len(accruals) == 4


def test_stock_illegal_raises_keyerror():
    with pytest.raises(KeyError, match="illegal stock transition"):
        transition_stock("ACCEPTED", "ISSUED")
    with pytest.raises(KeyError, match="illegal stock transition"):
        transition_stock("TO_SELLER", "STORED")
    with pytest.raises(KeyError):
        transition_stock("NOPE", "STORED")


def test_stock_expired_to_seller_and_intake_accrual():
    status, acc = transition_stock(
        "STORED", "EXPIRED", pvz_id=2, stock_item_id=3
    )
    assert status == "EXPIRED"
    assert acc["type"] == "status:EXPIRED"

    status, acc = transition_stock(
        "EXPIRED", "TO_SELLER", pvz_id=2, stock_item_id=3
    )
    assert status == "TO_SELLER"
    assert acc["type"] == "status:TO_SELLER"

    intake = make_intake_accrual(pvz_id=2, qty=3, stock_item_id=3)
    assert intake["type"] == "intake"
    assert intake["amount"] == INTAKE_FEE * 3
    assert make_status_accrual(pvz_id=1, new_status="STORED")["type"] == "status:STORED"


def test_terminal_states_have_no_outgoing():
    assert ORDER_TRANSITIONS["CANCELLED"] == set()
    assert ORDER_TRANSITIONS["RETURNED"] == set()
    assert ORDER_TRANSITIONS["FAILED_ROUTE"] == set()
    assert STOCK_TRANSITIONS["TO_SELLER"] == set()
    with pytest.raises(KeyError):
        transition_order("CANCELLED", "CREATED")
