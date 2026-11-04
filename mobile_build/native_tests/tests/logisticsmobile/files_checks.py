"""Native folder pins, retained browser state and reviewed managed pulls."""

from commonUtils.testing.stages import TestStage

from pathlib import Path

TEST_STAGE = TestStage.REGRESSION


async def exercise_files(app, passed):
    from unittest.mock import AsyncMock, patch
    from services.documents.locations import collection_path
    # Use the real native bridge and selected-item download handoff. Back must
    # never uncover the picker after clear() emptied and disabled its controls.
    await app.browser_cloud_location(('Fixture', 'logistics-native-check'))
    app.show_cloud()
    source = app.routes.body('files')
    row = next(row for row in app.cloud_rows.values() if row['path'].endswith('fixture.txt'))
    await app.download_remote_item(row)
    picker = app.editor_picker()
    shared = picker.editor_storage_roots['Shared files']
    assert not shared.include_collections
    assert not any(row['name'] in ('Local', 'Received Files') for row in shared.list())
    picker.save_as_name.value = 'selected-download.txt'
    with patch.object(app.main_window, 'dialog', new=AsyncMock(return_value=True)):
        assert await picker.complete_destination(), app.cloud_status.value
    assert (collection_path(app.private_root) / 'selected-download.txt').read_bytes() == b'Native rclone fixture\n'
    assert app.routes.back()
    assert app.routes.body('files') is source
    assert app.cloud_path == 'logistics-native-check'
    assert not app.cloud_busy and not app.transfer_busy
    app.routes.return_to('home')
    app.routes.return_to('files')
    assert app.routes.body('files') is source
    assert 'text-destination' not in [screen[0] for screen in app.routes.screens['files']]
    app.show_locations()
    assert all(button.enabled for button in app.folder_source_buttons.values())
    assert await app.show_files(local_root=True)
    await app.browser_cloud_location(('Fixture', ''))
    app.cloud_entries.value = next(key for key, row in app.cloud_rows.items() if row['path'] == 'logistics-native-check')
    from .review_checks import approve_transfer
    app.begin_transfer_review(remote='Fixture', folder='logistics-native-check', storage='Local')
    await approve_transfer(app)
    store = app.mirror_store()
    job = next(iter(store.jobs.values()))
    target = app.private_root / 'LocalFiles' / job['target']
    assert (target / 'fixture.txt').read_bytes() == b'Native rclone fixture\n'
    locations = app.locations_controller()
    await locations.pin_remote_folder()
    assert any(item['kind'] == 'remote' for item in locations.pinned_locations().items), app.cloud_status.value
    await app.open_mirror_copy(job['id'])
    browser = app.file_browser
    browser.show_tiles()
    browser.sort.value = 'Name Z–A'
    locations.pin_local_folder()
    pin = next(item for item in locations.pinned_locations().items if item['kind'] == 'local')
    app.show_settings()
    await app.show_files()
    assert app.file_browser is browser and browser.mode == 'Tiles'
    assert browser.sort.value == 'Name Z–A' and app.file_path == job['target']
    await locations.pinned_opener(pin)()
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
    assert Locations(app.private_root).items == locations.pinned_locations().items
    # Return to list presentation for independent cases that follow this one.
    browser.show_list()
    await app.browser_file_location(('Local files', ''))
    assert Path(app.private_root / 'locations.json').is_file()
    passed.append('native_files_pins_and_reviewed_pulls')
