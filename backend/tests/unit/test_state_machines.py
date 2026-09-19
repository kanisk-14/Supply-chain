"""State-machine unit tests.

The machines are pure definitions: asserting the valid and invalid transitions
from the specification, plus rejection of unknown states, terminal states, and
self-transitions.
"""

import pytest

from app.common.exceptions import InvalidStateTransitionError
from app.state_machines.order import OrderStateMachine, OrderStatus, order_state_machine
from app.state_machines.shipment import (
    ShipmentStateMachine,
    ShipmentStatus,
    shipment_state_machine,
)


class TestOrderStateMachine:
    @pytest.mark.parametrize(
        "current,target",
        [
            (OrderStatus.PLACED, OrderStatus.CONFIRMED),
            (OrderStatus.PLACED, OrderStatus.CANCELLED),
            (OrderStatus.CONFIRMED, OrderStatus.FULFILLED),
            (OrderStatus.CONFIRMED, OrderStatus.CANCELLED),
        ],
    )
    def test_valid_transitions(self, current, target):
        assert order_state_machine.can_transition(current, target)
        assert order_state_machine.transition(current, target) == target

    @pytest.mark.parametrize(
        "current,target",
        [
            (OrderStatus.FULFILLED, OrderStatus.PLACED),
            (OrderStatus.CANCELLED, OrderStatus.CONFIRMED),
            (OrderStatus.PLACED, OrderStatus.FULFILLED),
            (OrderStatus.CONFIRMED, OrderStatus.PLACED),
            (OrderStatus.FULFILLED, OrderStatus.CANCELLED),
            (OrderStatus.CANCELLED, OrderStatus.FULFILLED),
            (OrderStatus.FULFILLED, OrderStatus.FULFILLED),  # self-transition
            (OrderStatus.CANCELLED, OrderStatus.CANCELLED),  # self-transition
        ],
    )
    def test_invalid_transitions_raise(self, current, target):
        assert not order_state_machine.can_transition(current, target)
        with pytest.raises(InvalidStateTransitionError):
            order_state_machine.transition(current, target)

    def test_is_valid_state(self):
        assert order_state_machine.is_valid_state(OrderStatus.PLACED)
        assert not order_state_machine.is_valid_state("NONSENSE")

    def test_unknown_state_raises(self):
        with pytest.raises(InvalidStateTransitionError):
            order_state_machine.transition("NONSENSE", OrderStatus.PLACED)

    def test_initial_state(self):
        assert OrderStateMachine.initial == OrderStatus.PLACED

    def test_states_cover_model_enum(self):
        assert order_state_machine.states == set(OrderStatus)


class TestShipmentStateMachine:
    @pytest.mark.parametrize(
        "current,target",
        [
            (ShipmentStatus.PACKED, ShipmentStatus.IN_TRANSIT),
            (ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELIVERED),
        ],
    )
    def test_valid_transitions(self, current, target):
        assert shipment_state_machine.can_transition(current, target)
        assert shipment_state_machine.transition(current, target) == target

    @pytest.mark.parametrize(
        "current,target",
        [
            # Skipping a stage is intentionally NOT supported.
            (ShipmentStatus.PACKED, ShipmentStatus.DELIVERED),
            (ShipmentStatus.DELIVERED, ShipmentStatus.IN_TRANSIT),
            (ShipmentStatus.DELIVERED, ShipmentStatus.PACKED),
            (ShipmentStatus.PACKED, ShipmentStatus.PACKED),  # self-transition
            (ShipmentStatus.IN_TRANSIT, ShipmentStatus.IN_TRANSIT),
            (ShipmentStatus.DELIVERED, ShipmentStatus.DELIVERED),
        ],
    )
    def test_invalid_transitions_raise(self, current, target):
        assert not shipment_state_machine.can_transition(current, target)
        with pytest.raises(InvalidStateTransitionError):
            shipment_state_machine.transition(current, target)

    def test_initial_state(self):
        assert ShipmentStateMachine.initial == ShipmentStatus.PACKED

    def test_delayed_is_not_a_persisted_state(self):
        assert not shipment_state_machine.is_valid_state("DELAYED")

    def test_states_cover_model_enum(self):
        assert shipment_state_machine.states == set(ShipmentStatus)

    def test_reachable_from(self):
        assert shipment_state_machine.reachable_from(ShipmentStatus.PACKED) == {
            ShipmentStatus.IN_TRANSIT
        }


class TestErrorContract:
    def test_transition_error_is_app_error_with_409(self):
        with pytest.raises(InvalidStateTransitionError) as excinfo:
            order_state_machine.transition(OrderStatus.FULFILLED, OrderStatus.PLACED)
        assert excinfo.value.status_code == 409
        assert excinfo.value.code == "INVALID_STATE_TRANSITION"