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
