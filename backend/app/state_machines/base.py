"""Reusable finite state machine definition.

A ``StateMachine`` declares a fixed set of states and an explicit, directed
transition map. Transitions that are not declared are simply invalid — they
raise :class:`~app.common.exceptions.InvalidStateTransitionError`.

Deliberate choices:
- ``PACKED -> DELIVERED`` is NOT configured in the shipment machine.
- ``FULFILLED`` and ``CANCELLED`` are terminal states.
"""

from __future__ import annotations

from typing import Any

from app.common.exceptions import InvalidStateTransitionError


class StateMachine:
    """Declarative FSM. Subclass and set the class attributes."""

    name: str = "state_machine"
    initial: Any = None
    states: set[Any] = set()
    transitions: dict[Any, set[Any]] = {}

    def is_valid_state(self, state: Any) -> bool:
        return state in self.states

    def validate_state(self, state: Any) -> None:
        if not self.is_valid_state(state):
            raise InvalidStateTransitionError(
                f"{self.name}: unknown state {state!r}"
            )

    def can_transition(self, current: Any, target: Any) -> bool:
        self.validate_state(current)
        if target not in self.states:
            return False
        return target in self.transitions.get(current, set())

    def transition(self, current: Any, target: Any) -> Any:
        """Return ``target`` if the transition is allowed, otherwise raise.

        Never mutates anything — persistence and history are owned by the
        service layer.
        """
        self.validate_state(current)
        if not self.can_transition(current, target):
            raise InvalidStateTransitionError(
                f"{self.name}: invalid transition {current} -> {target}"
            )
        return target

    def reachable_from(self, current: Any) -> set[Any]:
        self.validate_state(current)
        return set(self.transitions.get(current, set()))