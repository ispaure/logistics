"""Small deterministic codec fixtures; caller owns the disposable directory."""
from pathlib import Path
from contextlib import contextmanager
from hashlib import sha256
import json
import os
import shutil
import subprocess


@contextmanager
def layout_evidence(window, path):
    """Save screenshots on assertion failure, or explicitly for visual review."""
    def save():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(path)):
            raise OSError('Could not save layout screenshot: ' + str(path))
    try:
        yield
    except Exception as error:
        try:
            save()
        except Exception as capture_error:
            error.add_note('Layout screenshot capture failed: ' + str(capture_error))
        raise
    else:
        if os.environ.get('LOGISTICS_TEST_SCREENSHOTS') == '1':
            save()


def bundled_movie(name, root):
    """Copy an integrity-checked synthetic clip into the caller's workspace."""
    assets = Path(__file__).with_name('fixtures') / 'video'
    manifest = json.loads((assets / 'manifest.json').read_text())
    if manifest.get('schema') != 1 or Path(name).name != name:
        raise ValueError('Unsupported video fixture manifest or name.')
    data = (assets / name).read_bytes()
    if sha256(data).hexdigest() != manifest['files'][name]['sha256']:
        raise ValueError('Video fixture checksum changed: ' + name)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    result = root / name
    result.write_bytes(data)
    return result


def codec_matrix(root, ffmpeg='ffmpeg', *, duration=2, regenerate=False):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if ffmpeg == 'ffmpeg' and duration == 2 and not regenerate:
        manifest = json.loads((Path(__file__).with_name('fixtures') / 'video/manifest.json').read_text())
        rows = manifest['codec_matrix']
        if len(rows) != 13:
            raise ValueError('The complete recorded codec fixture matrix is required.')
        return [(row['container'], row['video'], row['audio'], bundled_movie(row['file'], root)) for row in rows]
    fixtures = []
    for container in ('mp4', 'mkv'):
        for video, encoder in (('h264', 'libx264'), ('hevc', 'libx265')):
            for audio, audio_encoder in (('aac', 'aac'), ('opus', 'libopus')):
                path = root / f'{video}-{audio}.{container}'
                command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'lavfi', '-i', 'testsrc2=size=128x72:rate=12',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
                    '-t', str(duration), '-c:v', encoder, '-preset', 'ultrafast', '-threads', '1',
                    '-pix_fmt', 'yuv420p', '-c:a', audio_encoder]
                if video == 'hevc':
                    command += ['-x265-params', 'pools=1:frame-threads=1:log-level=error', '-tag:v', 'hvc1']
                command += ['-strict', '-2', str(path)]
                subprocess.run(command, check=True, capture_output=True, timeout=45)
                fixtures.append((container, video, audio, path))
    # Classic files exercise the existing decoder library, not just admission.
    for container, video, audio, encoder, audio_encoder in (
            ('avi', 'mpeg4', 'mp3', 'mpeg4', 'libmp3lame'),
            ('avi', 'mjpeg', 'pcm', 'mjpeg', 'pcm_s16le'),
            ('mkv', 'h264', 'ac3', 'libx264', 'ac3'),
            ('mkv', 'h264', 'eac3', 'libx264', 'eac3'),
            ('mkv', 'h264', 'flac', 'libx264', 'flac')):
        path = root / f'{video}-{audio}.{container}'
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'lavfi', '-i', 'testsrc2=size=128x72:rate=12',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
            '-t', str(duration), '-c:v', encoder, '-threads', '1',
            '-c:a', audio_encoder, str(path)], check=True, capture_output=True, timeout=45)
        fixtures.append((container, video, audio, path))
    return fixtures


def hdr_movies(root, ffmpeg='ffmpeg', *, duration=30):
    """10-bit BT.2020 PQ and HLG samples; not a display calibration pattern."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    fixtures = []
    for name, transfer in (('pq', 'smpte2084'), ('hlg', 'arib-std-b67')):
        path = root / f'hevc-hdr-{name}.mp4'
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'lavfi', '-i', 'testsrc2=size=128x72:rate=12',
            '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
            '-t', str(duration), '-c:v', 'libx265', '-preset', 'ultrafast',
            '-threads', '1', '-pix_fmt', 'yuv420p10le',
            '-x265-params', 'pools=1:frame-threads=1:log-level=error:colorprim=9:colormatrix=9:transfer=' + ('16' if name == 'pq' else '18'),
            '-color_primaries', 'bt2020', '-color_trc', transfer, '-colorspace', 'bt2020nc',
            '-tag:v', 'hvc1', '-c:a', 'aac', str(path)],
            check=True, capture_output=True, timeout=45)
        fixtures.append(('mp4', 'hevc', 'aac', path))
    return fixtures


def multitrack_movie(root, source, ffmpeg='ffmpeg'):
    root = Path(root)
    subtitles = root / 'tracks.srt'
    subtitles.write_text('1\n00:00:00,000 --> 00:00:01,900\nEmbedded fixture caption\n')
    output = root / 'tracks.mkv'
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source),
        '-i', str(subtitles), '-map', '0:v:0', '-map', '0:a:0', '-map', '0:a:0', '-map', '1:s:0',
        '-c', 'copy', '-metadata:s:a:0', 'language=eng', '-metadata:s:a:1', 'language=fra',
        '-metadata:s:s:0', 'language=eng', str(output)],
        check=True, capture_output=True, timeout=30)
    return output


def orientation_fixtures(root):
    """Asymmetric corner colors reveal every EXIF rotation/mirror on native APIs."""
    import json
    from io import BytesIO
    from PIL import Image, ImageOps
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    source = Image.new('RGB', (30, 50))
    for box, color in (((0, 0, 15, 25), 'red'), ((15, 0, 30, 25), 'green'),
                       ((0, 25, 15, 50), 'blue'), ((15, 25, 30, 50), 'yellow')):
        source.paste(color, box)
    manifest = []
    for format in ('JPEG', 'WEBP', 'PNG'):
        for orientation in range(1, 9):
            metadata = Image.Exif()
            metadata[274] = orientation
            data = BytesIO()
            source.save(data, format=format, exif=metadata)
            name = f'{format.lower()}-{orientation}'
            root.joinpath(name + '.source').write_bytes(data.getvalue())
            with Image.open(BytesIO(data.getvalue())) as encoded:
                expected = ImageOps.exif_transpose(encoded).convert('RGB')
                corners = [(2, 2), (expected.width - 3, 2), (2, expected.height - 3),
                           (expected.width - 3, expected.height - 3)]
                manifest.append(dict(name=name, size=list(expected.size),
                    corners=[list(expected.getpixel(point)) for point in corners]))
    root.joinpath('manifest.json').write_text(json.dumps(manifest))


def chapter_movie(root, container='mkv', ffmpeg='ffmpeg', *, regenerate=False):
    """A short movie with named chapter boundaries, for real decoder/menu tests."""
    if container == 'mkv' and ffmpeg == 'ffmpeg' and not regenerate:
        return bundled_movie('chapters.mkv', root)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    metadata = root / 'chapters.ffmeta'
    metadata.write_text(';FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=6000\ntitle=Opening\n'
                        '[CHAPTER]\nTIMEBASE=1/1000\nSTART=6000\nEND=12000\ntitle=Second scene\n')
    output = root / ('chapters.' + container)
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y',
        '-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=25', '-f', 'ffmetadata', '-i', str(metadata),
        '-t', '12', '-map', '0:v', '-map_metadata', '1', '-map_chapters', '1',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-threads', '1', str(output)],
        check=True, capture_output=True, timeout=30)
    return output


def refresh_bundled(ffmpeg='ffmpeg'):
    """Regenerate the committed clips used by deterministic decoder tests."""
    if not shutil.which(ffmpeg):
        raise RuntimeError('FFmpeg is required to regenerate the recorded fixtures.')
    from logistics_build.build_retention import scratch
    destination = Path(__file__).with_name('fixtures') / 'video'
    with scratch() as root:
        matrix = codec_matrix(root / 'codecs', ffmpeg, regenerate=True)
        chapter = chapter_movie(root / 'chapters', ffmpeg=ffmpeg, regenerate=True)
        speed, black = root / 'speed-with-audio.mkv', root / 'black.mkv'
        subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
            'testsrc2=size=128x72:rate=12:duration=24', '-f', 'lavfi', '-i',
            'sine=frequency=440:sample_rate=48000:duration=24', '-c:v', 'libx264',
            '-preset', 'ultrafast', '-threads', '1', '-c:a', 'aac', str(speed)], check=True, timeout=40)
        subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
            'color=c=black:s=320x180:r=15:d=12', '-c:v', 'libx264', '-preset', 'ultrafast',
            '-threads', '1', str(black)], check=True, timeout=30)
        destination.mkdir(parents=True, exist_ok=True)
        manifest = dict(schema=1, source='Generated testsrc2/color patterns and sine tones.',
            generator='tests.readers.video_fixtures.refresh_bundled',
            ffmpeg_version=subprocess.check_output([ffmpeg, '-version'], text=True).splitlines()[0],
            codec_matrix=[dict(container=c, video=v, audio=a, file=p.name) for c, v, a, p in matrix], files={})
        for path in [*(row[3] for row in matrix), chapter, speed, black]:
            data = path.read_bytes()
            (destination / path.name).write_bytes(data)
            manifest['files'][path.name] = dict(bytes=len(data), sha256=sha256(data).hexdigest())
        (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    refresh_bundled()


def luminance_movie(root, transfer='pq', *, duration=12, ffmpeg='ffmpeg'):
    """Eight neutral 10-bit BT.2020 bands at known display luminances (nits)."""
    import math
    import struct
    if transfer not in {'pq', 'hlg'}:
        raise ValueError('Expected PQ or HLG.')
    root = Path(root)
    levels = (.1, 1, 10, 100, 203, 400, 1000, 4000) if transfer == 'pq' else (.1, 1, 10, 50, 100, 203, 400, 1000)
    def signal(nits):
        if transfer == 'pq':
            linear = (nits / 10000) ** (2610 / 16384)
            return ((3424 / 4096 + 2413 / 128 * linear) / (1 + 2392 / 128 * linear)) ** (2523 / 32)
        linear = (nits / 1000) ** (1 / 1.2)
        a, b, c = .17883277, .28466892, .55991073
        return math.sqrt(3 * linear) if linear <= 1 / 12 else a * math.log(12 * linear - b) + c
    width, height = 320, 180
    row = b''.join(struct.pack('<H', round(64 + 876 * signal(levels[x * 8 // width]))) for x in range(width))
    frame = row * height + struct.pack('<H', 512) * (width * height // 2)
    raw, output = root / f'luminance-{transfer}.yuv', root / f'luminance-{transfer}.mp4'
    raw.write_bytes(frame)
    try:
        subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-stream_loop', '-1',
            '-f', 'rawvideo', '-pix_fmt', 'yuv420p10le', '-s', '320x180', '-r', '12', '-i', str(raw),
            '-t', str(duration), '-c:v', 'libx265', '-preset', 'ultrafast', '-threads', '1',
            '-x265-params', 'pools=1:frame-threads=1:log-level=error:colorprim=9:transfer=' + ('16' if transfer == 'pq' else '18') + ':colormatrix=9',
            '-color_primaries', 'bt2020', '-color_trc', 'smpte2084' if transfer == 'pq' else 'arib-std-b67',
            '-colorspace', 'bt2020nc', '-tag:v', 'hvc1', str(output)], check=True, capture_output=True, timeout=45)
    finally:
        raw.unlink(missing_ok=True)
    return output, levels
