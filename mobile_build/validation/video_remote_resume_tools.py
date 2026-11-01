"""Measure real iOS VLC resume through rclone ranges, with synthetic MKV only."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
from time import monotonic, sleep

from logistics_build.build_retention import scratch
from mobile_build.validation.video_chrome_tools import run
from features.rclone import executable, session
from features.rclone.remote_resources import RemoteResources
from features.video.playback import VideoContent
from features.video.transport import VideoTransport
from tests.local_crypt_fixture import crypt_fixture


def exercise(framework, output, *, unknown_duration=False):
    binary = executable.get_rclone_path()
    calls = []
    with scratch() as workspace, crypt_fixture(workspace, binary) as fixture:
        movie = fixture.plain / 'resume.mkv'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=12',
            '-t', '180', '-c:v', 'libx265', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p10le',
            '-x265-params', 'pools=1:frame-threads=1:log-level=error:keyint=24:bitrate=1200:vbv-maxrate=1200:vbv-bufsize=1200:colorprim=9:transfer=16:colormatrix=9',
            '-color_primaries', 'bt2020', '-color_trc', 'smpte2084', '-colorspace', 'bt2020nc', str(movie)], check=True)
        session.remember(fixture.context, dict(session.credentials(fixture.context), Plain=dict(type='alias', remote=str(fixture.plain))))
        class MeasuredRemote(RemoteResources):
            @contextmanager
            def open(self, path):
                with super().open(path) as stream:
                    read = stream.read_range
                    def measured(offset, count):
                        row = dict(offset=offset, count=count, start=monotonic())
                        calls.append(row)
                        sleep(.15 + count / (2 * 1024 * 1024))
                        try:
                            return read(offset, count)
                        finally:
                            row['seconds'] = monotonic() - row['start']
                    stream.read_range = measured
                    yield stream
        provider = MeasuredRemote(fixture.context, 'Plain', binary=binary)
        content = VideoContent(provider, movie.name)
        transport = VideoTransport(content)
        try:
            run(framework, output, 'iPhone Duo', hdr=True, resume=120000,
                movie=movie, url=transport.url, duration=180000, unknown_duration=unknown_duration)
            # This constant-bitrate fixture must leave the middle third unread:
            # initial metadata and the two-minute cue suffice for first frames.
            size = movie.stat().st_size
            assert not any(size / 3 < row['offset'] < size / 2 for row in calls), 'MKV resume scanned the preceding clusters'
        finally:
            transport.close()
            content.close()
            provider.close()
            output.mkdir(parents=True, exist_ok=True)
            first = min((row['start'] for row in calls), default=0)
            for row in calls:
                row['start'] -= first
            (output / 'ranges.json').write_text(json.dumps(dict(size=movie.stat().st_size, ranges=calls,
                scope='Real rclone alias ranges; 150 ms plus 2 MiB/s simulated delay; no Dropbox account'), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--framework', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--unknown-duration', action='store_true')
    args = parser.parse_args()
    exercise(args.framework.resolve(), args.output.resolve(), unknown_duration=args.unknown_duration)
