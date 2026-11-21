"""Stop protected desktop narration when Qt reports a new default output."""
import logging

from commonUtils.ui import pyside as qt
from services.access_policy import session_only
from services.desktop_video_access import session_contexts
from services.documents.ui.audio_outputs import SelectedAudioOutput


def protected_document(control):
    owner = control.parent()
    while owner is not None:
        guard = getattr(owner, '_private_view_guard', None)
        if guard is not None:
            try:
                if guard.locked or session_only(guard.current_provider()):
                    return True
            except Exception:
                # A failed provider handoff cannot authorize continued speech.
                return True
        owner = owner.parent()
    return False


def stop_private_speech():
    from commonUtils.ui.readers.read_aloud import ReadAloud
    from features.lm.ui.answer_speech import AnswerSpeech

    process_private = bool(session_contexts())
    for window in qt.QApplication.topLevelWidgets():
        # Detached tabs and dialogs may also be children of a top-level window.
        if window.parentWidget() is None:
            for control_type in (ReadAloud, AnswerSpeech):
                for control in window.findChildren(control_type):
                    if control.session is not None and not control.session.closed and (
                            process_private or protected_document(control)):
                        # The playlist's override also invalidates pending loads.
                        try:
                            control.stop()
                        except Exception:
                            logging.getLogger(__name__).exception('Could not stop a protected speech control.')


def monitor_private_speech(app):
    monitor = SelectedAudioOutput(app)
    monitor.changed.connect(stop_private_speech)
    return monitor
