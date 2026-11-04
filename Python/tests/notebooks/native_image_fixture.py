"""Regenerate only the public native image fixture with reproducible test entropy.

The fixed entropy is scoped to this host-only generator, never runtime crypto.
"""
from contextlib import ExitStack
from hashlib import sha256
from io import BytesIO
from itertools import count
from pathlib import Path
from unittest.mock import patch
from uuid import UUID
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

FIXTURE = Path(__file__).resolve().parents[3] / 'mobile_build/native_tests/tests/logisticsmobile/notebook-image-fixture.rmdoc'
PASSWORD = 'image-qa-password'


def generate():
    from .image_fixtures import fixture_bytes
    identities, entropy = count(1), count(1)
    def identity():
        return UUID(int=next(identities))
    def token(length):
        data=b''
        while len(data)<length:
            data+=sha256(('public-notebook-image-fixture:'+str(next(entropy))).encode()).digest()
        return data[:length]
    with ExitStack() as context:
        for module in ('notebook','ink','images'):
            context.enter_context(patch('features.notebooks.'+module+'.uuid4',side_effect=identity))
        context.enter_context(patch('features.notebooks.notebook.time.time',return_value=1700000000))
        context.enter_context(patch('secrets.token_bytes',side_effect=token))
        raw=fixture_bytes()
    # ZIP timestamps are packaging metadata, independent of notebook/PDF bytes.
    result=BytesIO()
    with ZipFile(BytesIO(raw)) as source, ZipFile(result,'w',compression=ZIP_DEFLATED) as target:
        for name in sorted(source.namelist()):
            member=ZipInfo(name,date_time=(2023,11,14,22,13,20))
            member.compress_type=ZIP_DEFLATED
            member.create_system=3
            member.external_attr=0o100644<<16
            target.writestr(member,source.read(name))
    return result.getvalue()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write',action='store_true')
    args=parser.parse_args()
    data=generate()
    if args.write:
        FIXTURE.write_bytes(data)
    elif FIXTURE.read_bytes()!=data:
        raise SystemExit('Public native image fixture differs; regenerate explicitly with --write')
    print(sha256(data).hexdigest(),len(data))
