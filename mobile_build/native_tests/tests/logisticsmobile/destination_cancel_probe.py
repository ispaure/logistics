"""Native callback acceptance for cancelling an in-flight New folder operation."""
import asyncio
import json
from pathlib import Path
from threading import Event
import traceback

from tests.logisticsmobile.destination_probe import DestinationProbe


class DestinationCancelProbe(DestinationProbe):
    async def check_destinations(self):
        report = dict(success=False, cases=[], backend=type(self._impl).__module__)
        release = Event()
        import commonUtils.runtime.resources.mutations as mutations
        original = mutations.create_resource_folder
        try:
            self.show_cloud(present=False)
            restoring = getattr(self, 'cloud_restore_task', None)
            if restoring is not None:
                await restoring
            self.show_home()
            self.choose_document_type()
            form = self.body
            destination = self.native_host.state.destination
            origin = (destination, len(self.routes.screens[destination]), len(self.adaptive.detail_routes))
            picker = self.editor_picker()
            await picker.show_document_creation('Cancelled.md', origin)
            await asyncio.sleep(.4)
            root = picker.editor_provider(picker.save_as_storage.value).root
            started = Event()
            def delayed(*args, **kwargs):
                started.set()
                if not release.wait(10):
                    raise TimeoutError('Cancellation fixture did not release')
                return original(*args, **kwargs)
            mutations.create_resource_folder = delayed
            picker.new_folder_name.value = 'Cancelled folder'
            task = self.loop.create_task(picker.create_picker_folder())
            await self.wait(started.is_set, timeout=10)
            picker.cancel_text_destination()
            release.set()
            await task
            await self.wait(lambda: picker.creation is None, timeout=10)
            await asyncio.sleep(.4)
            from mobile.routes import contains
            assert contains(self.body, form), 'Cancel did not restore the source creation form'
            assert not (root / 'Cancelled folder').exists()
            assert not (root / 'Cancelled.md').exists()
            report.update(success=True, cases=['native-deferred-new-folder-cancel'])
        except BaseException:
            report['error'] = traceback.format_exc()
        finally:
            release.set()
            mutations.create_resource_folder = original
        (Path(self.paths.cache) / 'destination-cancel-result.json').write_text(json.dumps(report, indent=2))
