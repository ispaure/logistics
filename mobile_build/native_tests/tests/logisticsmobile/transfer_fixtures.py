"""Test-only remote observations through the production folder Sync API."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


async def remote_files(client, job, *paths):
    with TemporaryDirectory(prefix='rclone-fixture-') as temporary:
        folder = Path(temporary).resolve()
        await asyncio.to_thread(client.request, 'mirror_sync', remote=job['remote'],
            path=job['prefix'], identity=job['identity'], local_path=str(folder),
            run=uuid4().hex, push=False, decrypted=not job['crypt'])
        return {path: (folder / path).read_bytes() if (folder / path).is_file() else None for path in paths}


async def seed_ciphertext(client, remote, info, mapped, source):
    with source.open('rb') as stream:
        await asyncio.to_thread(client.request, 'mirror_validate', remote=remote,
            path=mapped, identity=info['identity'], fd=stream.fileno())
    with TemporaryDirectory(prefix='rclone-seed-') as temporary:
        folder = Path(temporary).resolve()
        (folder / Path(mapped).name).write_bytes(source.read_bytes())
        await asyncio.to_thread(client.request, 'mirror_sync', remote=remote,
            path=info['prefix'], identity=info['identity'], local_path=str(folder),
            run=uuid4().hex, push=True)
