"""Shared transfer plans and single-use approval handoff; no toolkit or engine I/O."""
from dataclasses import dataclass, field
from threading import RLock
from typing import Callable
from weakref import WeakKeyDictionary
from commonUtils.runtime.operations import check_cancelled
from .review import ReviewRequest, ReviewSession


def _not_cancelled():
    return False


def _ignore_progress(*args, **kwargs):
    pass


@dataclass(frozen=True)
class TransferContext:
    cancelled: Callable[[], bool] = _not_cancelled
    progress: Callable = _ignore_progress


@dataclass(frozen=True)
class TransferPlan:
    """Platform adapter's captured review and mandatory execution policy."""
    request: ReviewRequest
    scanner: Callable = field(repr=False)
    valid: Callable[[], bool] = field(repr=False)
    execute: Callable = field(repr=False)


@dataclass(frozen=True, eq=False)
class PreparedTransfer:
    request: ReviewRequest
    review: ReviewSession


@dataclass
class _Approval:
    plan: TransferPlan
    used: bool = False


class TransferService:
    """Own approval consumption, preserving platform preflight and engine lifetimes.

    Retrying execution, including after a failed preflight, requires a new review.
    An approval cannot be moved to a different plan, runtime or set of options.
    """
    def __init__(self):
        self._prepared = WeakKeyDictionary()
        self._lock = RLock()

    def prepare(self, plan: TransferPlan) -> PreparedTransfer:
        review = ReviewSession(plan.request, plan.scanner, plan.valid)
        prepared = PreparedTransfer(plan.request, review)
        with self._lock:
            self._prepared[prepared] = _Approval(plan)
        return prepared

    def execute(self, prepared: PreparedTransfer, context=TransferContext()):
        with self._lock:
            if not isinstance(prepared, PreparedTransfer) or prepared not in self._prepared:
                raise ValueError('This transfer review belongs to another runtime.')
            approval = self._prepared[prepared]
            if approval.used:
                raise ValueError('This transfer approval was already used. Review again.')
            plan, review = approval.plan, prepared.review
            if (review.request is not plan.request or review.scanner is not plan.scanner
                    or review.valid is not plan.valid or not review.approved):
                raise ValueError('Connection or review changed. Review the transfer again.')
            approval.used = True
        check_cancelled(context.cancelled)
        return plan.execute(plan.request, context)
