"""Order lifecycle state machine.

    PLACED → CONFIRMED → FULFILLED
       ↓
    CANCELLED

Valid transitions:
    PLACED → CONFIRMED
    PLACED → CANCELLED
    CONFIRMED → FULFILLED
    CONFIRMED → CANCELLED

Phase 4/5 only are valid. Everything else raises
:class:`~app.common.exceptions.InvalidStateTransitionError`.
"""

from __future__ import annotations

from enum import Enum

from app.state_machines.base import StateMachine


class OrderStatus(str, Enum):
    PLACED = "PLACED"
    CONFIRMED = "CONFIRMED"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class OrderStateMachine(StateMachine):
    name = "order"
    initial = OrderStatus.PLACED
    states = set(OrderStatus)
    transitions = {
        OrderStatus.PLACED: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
        OrderStatus.CONFIRMED: {OrderStatus.FULFILLED, OrderStatus.CANCELLED},
        OrderStatus.FULFILLED: set(),
        OrderStatus.CANCELLED: set(),
    }


order_state_machine = OrderStateMachine()