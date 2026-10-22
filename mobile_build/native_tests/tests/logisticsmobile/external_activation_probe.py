"""Synthetic native proof of UIKit-driven portrait-phone/landscape-TV activation."""
import asyncio
import json
from pathlib import Path
import struct
import traceback
from uuid import uuid4
from zipfile import ZipFile
import zlib

from mobile.app import LogisticsMobile


class TVProbe(LogisticsMobile):
    def startup(self):
        self.storage_root = Path(self.paths.cache) / ('tv-fixture-' + uuid4().hex)
        super().startup()

    def on_running(self):
        if not getattr(self, '_tv_started', False):
            self._tv_started = True
            self.loop.create_task(self.check_tv())

    async def check_tv(self):
        result = {'success': False, 'cases': [], 'scope': 'UIKit-created noninteractive external scene using a simulator external display; no physical AirPlay receiver.'}
        try:
            while getattr(self, '_startup_in_progress', False):
                await asyncio.sleep(.1)
            await asyncio.sleep(1)
            from commonUtils.runtime.document_access import LocalDocuments
            from features.rclone.mobile.cloud import CloudClient
            from features.rclone.mobile.session_privacy import ResumePassword
            from mobile.external_display import sync, comic_canvas
            assert self.preferences.values['comic_layout'] == 'auto'
            assert self.preferences.values['comic_split_wide'] == 'true'
            def png(color, width=320, height=480):
                def chunk(kind, data):
                    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
                return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
                        + chunk(b'IDAT', zlib.compress((b'\0' + color * width) * height)) + chunk(b'IEND', b''))
            comic = self.private_root / 'TV.cbz'
            with ZipFile(comic, 'w') as archive:
                archive.writestr('1.png', png(b'\xff\x00\x00\xff'))
                archive.writestr('2.png', png(b'\x00\x00\xff\xff'))
                archive.writestr('3.png', png(b'\x00\xff\x00\xff', 640, 320))
                archive.writestr('4.png', png(b'\xff\x00\xff\xff'))
                archive.writestr('5.png', png(b'\x00\xff\xff\xff', 480, 480))
            store = self.reader_manager().catalog.library_store
            records = []
            for name in ('Volume 01.cbz', 'Volume 02.cbz', 'Volume 03.cbz'):
                source = self.private_root / name
                source.write_bytes(comic.read_bytes())
                records.append(store.import_book(LocalDocuments(), source))
            record = records[1]
            await self.open_book(record['id'])
            owner = self.reader_manager().active
            output = self.scene_manager.external_comics
            from rubicon.objc import ObjCClass
            for _ in range(150):
                if output.ios:
                    break
                await asyncio.sleep(.1)
            scenes = list(ObjCClass('UIApplication').sharedApplication.connectedScenes.allObjects())
            result['scene_roles'] = [str(s.session.role) for s in scenes]
            result['accessory_registered'] = output.ios_registration is not None
            result['accessory_available'] = bool(output.ios_registration[1].isAvailable) if output.ios_registration else None
            result['screens'] = [[float(s.bounds.size.width),float(s.bounds.size.height)] for s in ObjCClass('UIScreen').screens]
            result['registration_controller'] = str(output.ios_registration[0]) if output.ios_registration else None
            assert output.ios, 'UIKit never connected a noninteractive external scene'
            key = next(iter(output.ios))
            window, picture = output.ios[key]
            assert not window.isHidden(), 'UIKit TV window is hidden despite having a connected scene'
            assert str(window.windowScene.session.role) != 'UIWindowSceneSessionRoleApplication'
            result['external_bounds'] = [float(window.bounds.size.width), float(window.bounds.size.height)]
            result['phone_bounds'] = [float(self.native_scene.coordinateSpace.bounds.size.width), float(self.native_scene.coordinateSpace.bounds.size.height)]
            assert result['external_bounds'][0] > result['external_bounds'][1]
            assert result['phone_bounds'][0] < result['phone_bounds'][1]
            result['cases'].append('system_created_external_scene_while_phone_portrait')
            await asyncio.sleep(.5)
            assert picture.image is not None, 'No first comic image'
            assert picture.contentMode == 1
            assert float(picture.bounds.size.width) > 0
            assert picture.image == comic_canvas(owner.book_content)._impl.picture.image
            assert owner.comic_navigation.visible == (0, 1)
            assert self._comic_chrome_hidden
            assert output.ios_status is not None
            badge = output.ios_status[1]
            from mobile.screen_privacy import native_value
            result['badge_native'] = dict(hidden=bool(badge.isHidden()),
                superview=str(native_value(badge, 'superview')), window=str(native_value(badge, 'window')),
                expected_window=str(self.main_window._impl.native))
            assert native_value(badge, 'superview') == self.main_window._impl.native and not badge.isHidden()
            assert not badge.isUserInteractionEnabled()
            assert str(native_value(badge, 'text')) == 'Casting to TV'
            assert float(badge.frame.size.height) == 28
            result['badge_bounds'] = [float(badge.frame.origin.x), float(badge.frame.origin.y), float(badge.frame.size.width), float(badge.frame.size.height)]
            from .fixtures import capture_window
            await capture_window(self, Path(self.paths.cache) / 'casting-phone.png')
            result['cases'].append('casting_badge_visible_in_fullscreen')
            assert float(picture.image.size.width) == 640, 'Artificial gutter between pages'
            await owner.move_comic(-1)
            feedback = self._comic_boundary_feedback
            assert '← Swipe to read' in feedback.message
            assert feedback.native is not None and not feedback.native.isHidden()
            await asyncio.sleep(.1)
            await capture_window(self, Path(self.paths.cache) / 'comic-boundary-phone.png')
            await asyncio.sleep(2.6)
            assert not feedback.message and feedback.native is None
            await owner.move_comic(-1)
            assert self.readers.active is owner, 'First boundary swipe opened a volume'
            await owner.move_comic(-1)
            assert self.readers.active.book_record['id'] == records[0]['id']
            await self.readers.active.next_comic_file()
            owner = self.readers.active
            assert owner.book_record['id'] == record['id']
            result['cases'].append('native_direction_hint_expires_and_repeat_opens_previous_volume')
            first = picture.image
            result['cases'].append('native_aspect_fit_image')
            await owner.move_comic(1)
            assert owner.comic_navigation.visible == (2,)
            assert not owner.comic_navigation.split
            assert float(picture.image.size.width) > float(picture.image.size.height)
            await owner.move_comic(1)
            assert owner.comic_navigation.visible == (3, 4)
            result['cases'].append('sharing_two_pages_and_whole_wide_page')
            assert picture.image is not None and picture.image != first
            result['cases'].append('native_page_turn_publication')
            await owner.move_comic(1)
            assert self.readers.active is owner
            assert 'End of comic' in self._comic_boundary_feedback.message
            assert 'Swipe to read' not in self._comic_boundary_feedback.message
            await owner.move_comic(1)
            assert self.readers.active.book_record['id'] == records[2]['id']
            await self.readers.active.previous_comic_file()
            owner = self.readers.active
            result['cases'].append('native_end_hint_repeat_opens_next_volume')
            CloudClient._session_privacy = ResumePassword('synthetic-only')
            self.screen_privacy.refresh()
            assert picture.image is None, 'Session credentials left external pixels visible'
            assert output.ios_status is None
            result['cases'].append('session_credentials_blank_local_comic')
            CloudClient._session_privacy = None
            self.screen_privacy.refresh()
            assert picture.image is not None
            self.screen_privacy.conceal()
            assert picture.image is None
            self.screen_privacy.reveal()
            assert picture.image is not None
            result['cases'].append('conceal_and_reveal')
            self.show_settings()
            assert picture.image is None
            result['cases'].append('route_exit_blank')
            owner.show_library()
            sync(self, select=True)
            assert picture.image is not None
            original_preferences = self.preferences.path.read_bytes() if self.preferences.path.exists() else None
            phase = Path(self.paths.cache) / 'sharing-layout-phase.txt'
            async def until(predicate):
                for _ in range(300):
                    if predicate() and not owner.book_busy:
                        return
                    await asyncio.sleep(.1)
                raise AssertionError('Sharing layout did not follow the external display state')
            phase.write_text('disconnect')
            await until(lambda: not output.ios and owner.comic_navigation.visible == (owner.book_record['position'],))
            assert picture.image is None and output.ios_status is None
            await owner.move_book_page(2)
            assert owner.comic_navigation.split
            await owner.move_comic(1)
            assert owner.comic_navigation.half == 1
            phase.write_text('reconnect')
            await until(lambda: bool(output.ios) and not owner.comic_navigation.split)
            assert owner.comic_navigation.visible == (2,)
            assert output.ios_status is not None
            phase.write_text('disconnect-again')
            await until(lambda: not output.ios and owner.comic_navigation.split and owner.comic_navigation.half == 1)
            assert self.preferences.values['comic_layout'] == 'auto'
            assert self.preferences.values['comic_split_wide'] == 'true'
            assert (self.preferences.path.read_bytes() if self.preferences.path.exists() else None) == original_preferences
            phase.write_text('done')
            result['cases'].extend(['disconnect_releases_image', 'external_display_reconnect_restores_wide_half_without_saving_preferences'])
            self.main_window._impl.native.makeKeyAndVisible()
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        path = Path(self.paths.cache) / 'airplay-activation-result.json'
        path.write_text(json.dumps(result, indent=2))
        print('TV_RESULT ' + json.dumps(result), flush=True)


def main():
    TVProbe('TV Probe', 'io.github.ispaure.logisticsairplayqa').main_loop()
