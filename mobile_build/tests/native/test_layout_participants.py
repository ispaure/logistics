"""Layout subscriptions retire independently of host and native widget lifetimes."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import gc
import weakref
import unittest

from mobile.layout_participants import LayoutFrame, LayoutParticipants


class Control:
    pass


class LayoutParticipantTests(unittest.TestCase):
    def test_replacement_and_disposal_reject_old_owner_callbacks(self):
        participants = LayoutParticipants()
        first, second = Control(), Control()
        calls = []
        old = participants.register('page', first, lambda owner, frame: calls.append(owner))
        current = participants.register('page', second, lambda owner, frame: calls.append(owner))
        old.dispose()
        participants.reflow(LayoutFrame(400, lambda *_: 360))
        self.assertEqual(calls, [second])
        current.dispose()
        participants.reflow(LayoutFrame(800, lambda *_: 760))
        self.assertEqual(calls, [second])

    def test_registry_does_not_retain_closed_controls_and_stops_during_retirement(self):
        participants = LayoutParticipants()
        owner = Control()
        reference = weakref.ref(owner)
        participants.register('page', owner, lambda owner, frame: self.fail('Retired control invoked'))
        del owner
        gc.collect()
        self.assertIsNone(reference())
        participants.reflow(LayoutFrame(400, None))
        self.assertFalse(participants.entries)
        owner = Control()
        participants.register('first', owner, lambda owner, frame: participants.dispose(), order=0)
        participants.register('second', owner, lambda owner, frame: self.fail('Callback after retirement'), order=1)
        participants.reflow(LayoutFrame(400, None))
        self.assertFalse(participants.entries)

    def test_host_rotation_reflows_registered_pages_and_exit_retires_them(self):
        # Application-level reflow is covered by the dummy-host fixture below;
        # no native screen/device is needed to verify callback ownership.
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from mobile.app import LogisticsMobile
        with TemporaryDirectory() as folder:
            LogisticsMobile.storage_root = Path(folder)
            app = LogisticsMobile('Logistics', 'io.github.ispaure.logisticsmobile')
            try:
                page = Control()
                calls = []
                app._layout_participants.register('fixture', page,
                    lambda owner, frame: calls.append(frame.width))
                app.resize_workspace()
                self.assertEqual(calls[-1], app.main_window.size.width)
                from mobile.application_lifecycle import lifecycle
                lifecycle(app).retire_for_replacement()
                before = list(calls)
                app._layout_participants.reflow(LayoutFrame(800, None))
                self.assertEqual(calls, before)
            finally:
                app.active_host = True
                app.main_window.close()
                app.loop.close()
                LogisticsMobile.storage_root = None
