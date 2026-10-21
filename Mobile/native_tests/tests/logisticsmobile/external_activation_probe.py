"""Synthetic native proof of UIKit-driven portrait-phone/landscape-TV activation."""
import asyncio
import json
from pathlib import Path
import struct
import traceback
from uuid import uuid4
from zipfile import ZipFile
import zlib

from logisticsmobile.app import LogisticsMobile


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
            from logisticsmobile.external_display import sync
            self.preferences.save(comic_layout='single', comic_split_wide='false')
            def png(color):
                def chunk(kind, data):
                    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
                return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 320, 480, 8, 6, 0, 0, 0))
                        + chunk(b'IDAT', zlib.compress((b'\0' + color * 320) * 480)) + chunk(b'IEND', b''))
            comic = self.private_root / 'TV.cbz'
            with ZipFile(comic, 'w') as archive:
                archive.writestr('1.png', png(b'\xff\x00\x00\xff'))
                archive.writestr('2.png', png(b'\x00\x00\xff\xff'))
            record = self.reader_manager().catalog.library_store.import_book(LocalDocuments(), comic)
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
            assert picture.image == owner.book_content.children[0]._impl.picture.image
            first = picture.image
            result['cases'].append('native_aspect_fit_image')
            await owner.move_book_page(1)
            assert picture.image is not None and picture.image != first
            result['cases'].append('native_page_turn_publication')
            CloudClient._session_privacy = ResumePassword('synthetic-only')
            self.screen_privacy.refresh()
            assert picture.image is None, 'Session credentials left external pixels visible'
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
            output.disconnect_ios(window.windowScene)
            assert picture.image is None and not output.ios
            result['cases'].append('disconnect_releases_image')
            self.main_window._impl.native.makeKeyAndVisible()
            result['success'] = True
        except Exception:
            result['error'] = traceback.format_exc()
        path = Path(self.paths.cache) / 'airplay-activation-result.json'
        path.write_text(json.dumps(result, indent=2))
        print('TV_RESULT ' + json.dumps(result), flush=True)


def main():
    TVProbe('TV Probe', 'io.github.ispaure.logisticsairplayqa').main_loop()
