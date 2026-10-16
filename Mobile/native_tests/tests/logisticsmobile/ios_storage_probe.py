"""Exercise actual Foundation migration APIs on a disposable native fixture."""
from types import SimpleNamespace


def exercise_ios_storage(app):
    from logisticsmobile.ios_storage import prepare_for_app
    from features.rclone.mobile.storage_location import collection_path, _shared_local_roots
    root = app.private_root / 'ios-storage-probe'
    documents = root / 'Documents'
    (documents / 'LocalFiles').mkdir(parents=True)
    (documents / 'LocalFiles/native.txt').write_bytes(b'ordinary native fixture')
    (documents / 'Credentials').mkdir()
    (documents / 'Credentials/probe.bin').write_bytes(b'wrapped native fixture')
    paths = SimpleNamespace(data=documents, config=root / 'Library/Application Support/Config')
    private = paths.config.parent / 'Logistics'
    try:
        assert prepare_for_app(SimpleNamespace(paths=paths)) == private
        local = documents / 'Local'
        assert collection_path(private) == local
        assert (local / 'native.txt').read_bytes() == b'ordinary native fixture'
        assert not (documents / 'Credentials').exists()
        assert (private / 'Credentials/probe.bin').read_bytes() == b'wrapped native fixture'
        assert prepare_for_app(SimpleNamespace(paths=paths)) == private
        assert collection_path(private, True) == private / 'LocalCryptFolders'
        assert not (documents / 'native.txt').exists()
        print('LOGISTICS_NATIVE_IOS_STORAGE=private-migration-and-shared-local-verified', flush=True)
    finally:
        _shared_local_roots.pop(private, None)
