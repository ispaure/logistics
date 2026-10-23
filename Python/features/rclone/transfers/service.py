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
    active: Callable[[], bool] | None = field(default=None, repr=False)


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
    def __init__(self, plan_factory=None):
        self._plan_factory = plan_factory
        self._prepared = WeakKeyDictionary()
        self._lock = RLock()

    def review(self, request) -> PreparedTransfer:
        """Resolve a captured platform request without presentation or execution."""
        if self._plan_factory is None:
            raise TypeError('This transfer service has no platform adapter.')
        return self.prepare(self._plan_factory(request))

    def run(self, request, context=TransferContext()):
        """Run an explicitly requested programmatic transfer without a review UI.

        Interactive commands use review/execute. Automation retains its existing
        noninteractive API, with the same captured access and platform preflight.
        """
        if self._plan_factory is None:
            raise TypeError('This transfer service has no platform adapter.')
        check_cancelled(context.cancelled)
        plan = self._plan_factory(request)
        if not plan.valid():
            raise ValueError('Connection or target changed. Start the transfer again.')
        active = plan.active or plan.valid
        execution = TransferContext(lambda: context.cancelled() or not active(), context.progress)
        check_cancelled(execution.cancelled)
        return plan.execute(plan.request, execution)

    def prepare(self, plan: TransferPlan) -> PreparedTransfer:
        if not plan.valid():
            raise ValueError('Connection or target changed. Review the transfer again.')
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
        # Review bindings include records which execution may legitimately save.
        # The active binding tracks only access lifetime throughout execution.
        active = plan.active or plan.valid
        execution = TransferContext(lambda: context.cancelled() or not active(), context.progress)
        check_cancelled(execution.cancelled)
        return plan.execute(plan.request, execution)
