"""Trade State Machine defining valid state transitions and lifecycle guards."""

from typing import Dict, Optional, Set, Union

from src.domain.exceptions.trade import InvalidTradeStateError
from src.domain.value_objects.trade_status import TradeStatus


class TradeStateMachine:
    """State machine governing Trade lifecycle transitions and invariant validations."""

    _VALID_TRANSITIONS: Dict[TradeStatus, Set[TradeStatus]] = {
        TradeStatus.WAITING_ENTRY: {
            TradeStatus.OPEN,
            TradeStatus.CANCELLED,
        },
        TradeStatus.OPEN: {
            TradeStatus.PARTIAL,
            TradeStatus.CLOSED,
        },
        TradeStatus.PARTIAL: {
            TradeStatus.PARTIAL,  # e.g., subsequent TP2 fill after TP1
            TradeStatus.CLOSED,
        },
        TradeStatus.CLOSED: set(),     # Terminal State
        TradeStatus.CANCELLED: set(),  # Terminal State
    }

    @classmethod
    def can_transition(
        cls,
        current_status: Union[TradeStatus, str],
        target_status: Union[TradeStatus, str],
    ) -> bool:
        """Check whether transition from current_status to target_status is allowed."""
        curr = TradeStatus.from_str(current_status) if isinstance(current_status, (str, TradeStatus)) else current_status
        target = TradeStatus.from_str(target_status) if isinstance(target_status, (str, TradeStatus)) else target_status

        allowed_targets = cls._VALID_TRANSITIONS.get(curr, set())
        return target in allowed_targets

    @classmethod
    def validate_transition(
        cls,
        current_status: Union[TradeStatus, str],
        target_status: Union[TradeStatus, str],
        trade_id: Optional[int] = None,
    ) -> None:
        """Validate state transition and raise InvalidTradeStateError if illegal."""
        curr = TradeStatus.from_str(current_status) if isinstance(current_status, (str, TradeStatus)) else current_status
        target = TradeStatus.from_str(target_status) if isinstance(target_status, (str, TradeStatus)) else target_status

        if not cls.can_transition(curr, target):
            id_info = f" for Trade #{trade_id}" if trade_id is not None else ""
            raise InvalidTradeStateError(
                f"Invalid trade state transition{id_info}: cannot transition from '{curr.value}' to '{target.value}'.",
                trade_id=trade_id,
                details={
                    "current_status": curr.value,
                    "target_status": target.value,
                    "allowed_transitions": [s.value for s in cls._VALID_TRANSITIONS.get(curr, set())],
                },
            )
