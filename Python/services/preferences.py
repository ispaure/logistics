"""Application-wide personal preference reset, independent of the Settings widget."""
from dataclasses import dataclass

from commonUtils.configuration.monitor import settings_monitor
from features import registry
from features.settings import reset_personal_configuration


@dataclass(frozen=True)
class ResetOutcome:
    refresh_errors: tuple[str, ...] = ()


def reset_personal_preferences(*, refresh_callbacks=()):
    """Commit storage/feature reset, then notify tools and refresh retained views.

    Storage/activation failures roll back and propagate. A view failure after
    commit is reported separately; it cannot undo a successful preference reset.
    Pending application edits and user documents remain owned by their views.
    """
    with reset_personal_configuration():
        registry.reset_feature_defaults()
    settings_monitor().notify()
    errors = []
    for refresh in refresh_callbacks:
        try:
            if refresh() is False:
                raise ValueError('A settings view could not reload')
        except Exception as error:
            errors.append(str(error))
    return ResetOutcome(tuple(errors))
