"""A snapshot shared by Android/iOS can refresh generated payloads safely."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from Scripts.mobile_payload import stage_payload


class MobilePayloadTests(unittest.TestCase):
    def test_refresh_and_failed_stage_restore_previous_payload(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'.manager-source.json').write_text('{}')
            payload=root/'mobile_build/payload'
            payload.mkdir(parents=True)
            (payload/'proof').write_text('old')
            def success(argv, cwd):
                self.assertFalse(payload.exists())
                payload.mkdir()
                (payload/'proof').write_text('new')
            stage_payload(root,'python',success)
            self.assertEqual((payload/'proof').read_text(),'new')
            def failure(argv,cwd):
                payload.mkdir()
                (payload/'partial').write_text('unfinished')
                raise OSError('stage failed')
            with self.assertRaises(OSError):
                stage_payload(root,'python',failure)
            self.assertEqual((payload/'proof').read_text(),'new')
            self.assertFalse((payload/'partial').exists())
            self.assertFalse([p for p in (root/'test-results/build-scratch').iterdir() if p.is_dir()])

    def test_reject_unowned_source_and_linked_payload(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaises(ValueError):
                stage_payload(root,'python',lambda *args:None)
            (root/'.manager-source.json').write_text('{}')
            (root/'mobile_build').mkdir()
            (root/'outside').mkdir()
            (root/'mobile_build/payload').symlink_to(root/'outside',target_is_directory=True)
            with self.assertRaises(ValueError):
                stage_payload(root,'python',lambda *args:None)


if __name__=='__main__':
    unittest.main()
