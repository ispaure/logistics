"""Small deterministic codec fixtures; caller owns the disposable directory."""
from pathlib import Path
import subprocess


def codec_matrix(root, ffmpeg='ffmpeg', *, duration=2):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
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


def chapter_movie(root, container='mkv', ffmpeg='ffmpeg'):
    """A short movie with named chapter boundaries, for real decoder/menu tests."""
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
