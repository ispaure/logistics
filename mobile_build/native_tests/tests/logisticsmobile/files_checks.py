"""Native folder pins, retained browser state and reviewed managed pulls."""
from pathlib import Path


async def exercise_files(app, passed):
    await app.browser_cloud_location(('Fixture', ''))
    app.cloud_entries.value = next(key for key, row in app.cloud_rows.items() if row['path'] == 'logistics-native-check')
    from .review_checks import approve_transfer
    app.begin_transfer_review(remote='Fixture', folder='logistics-native-check', storage='Local')
    await approve_transfer(app)
    store = app.mirror_store()
    job = next(iter(store.jobs.values()))
    target = app.private_root / 'LocalFiles' / job['target']
    assert (target / 'fixture.txt').read_bytes() == b'Native rclone fixture\n'
    await app.pin_remote_folder()
    assert any(item['kind'] == 'remote' for item in app.pinned_locations().items), app.cloud_status.value
    await app.open_mirror_copy(job['id'])
    browser = app.file_browser
    browser.show_tiles()
    browser.sort.value = 'Name Z–A'
    app.pin_local_folder()
    pin = next(item for item in app.pinned_locations().items if item['kind'] == 'local')
    app.show_settings()
    await app.show_files()
    assert app.file_browser is browser and browser.mode == 'Tiles'
    assert browser.sort.value == 'Name Z–A' and app.file_path == job['target']
    await app.pinned_opener(pin)()
    assert app.file_path == job['target']
    app.start_mirror_pull(job['id'])
    await approve_transfer(app)
    assert (target / 'fixture.txt').read_bytes() == b'Native rclone fixture\n'
    (target / 'fixture.txt').write_bytes(b'Locally edited native pull')
    app.start_mirror_pull(job['id'])
    await approve_transfer(app)
    assert (target / 'fixture.txt').read_bytes() == b'Native rclone fixture\n'
    from features.rclone.transfers.mobile.jobs import MirrorJobs
    from mobile.locations import Locations
    assert job['id'] in MirrorJobs(app.private_root).jobs
    assert Locations(app.private_root).items == app.pinned_locations().items
    # Return to list presentation for independent cases that follow this one.
    browser.show_list()
    await app.browser_file_location(('Local files', ''))
    assert Path(app.private_root / 'locations.json').is_file()
    passed.append('native_files_pins_and_reviewed_pulls')
