"""Qualify stream-copy MKV to fragmented MP4 HLS using synthetic media."""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import subprocess

from logistics_build.build_retention import scratch


def run(*command):
    return subprocess.run(command, check=True, text=True, capture_output=True, timeout=60).stdout


def probe(path, *options):
    return json.loads(run('ffprobe', '-v', 'error', *options, '-of', 'json', str(path)))


def remux(source, destination):
    """Copy the first video and audio tracks when they match the initial scope."""
    info = probe(source, '-show_entries', 'format=format_name:stream=codec_type,codec_name:stream_disposition=attached_pic')
    streams = info['streams']
    video = next((stream for stream in streams if stream['codec_type'] == 'video'), {})
    audio = next((stream for stream in streams if stream['codec_type'] == 'audio'), {})
    tag = {'h264': 'avc1', 'hevc': 'hvc1'}.get(video.get('codec_name'))
    if ('matroska' not in info['format']['format_name'].split(',') or not tag
            or video.get('disposition', {}).get('attached_pic') or audio.get('codec_name') != 'aac'):
        raise ValueError('The MKV probe requires H.264 or HEVC video and AAC audio.')
    destination.mkdir()
    playlist = destination / 'video.m3u8'
    run('ffmpeg', '-v', 'error', '-nostdin', '-i', str(source), '-map', '0:v:0', '-map', '0:a:0',
        '-c', 'copy', '-tag:v', tag, '-f', 'hls', '-hls_segment_type', 'fmp4', '-hls_time', '6',
        '-hls_playlist_type', 'vod', '-hls_segment_filename', str(destination / 'part-%05d.m4s'),
        str(playlist))
    return playlist, tag


def make_fixture(path, codec, audio='aac'):
    encoder = 'libx264' if codec == 'h264' else 'libx265'
    params = (['-x264-params', 'scenecut=0:open-gop=0'] if codec == 'h264' else [
        '-x265-params', 'pools=1:frame-threads=1:log-level=error:scenecut=0:open-gop=0'])
    run('ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=24',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-t', '19',
        '-c:v', encoder, '-preset', 'fast', '-threads', '1', '-pix_fmt', 'yuv420p',
        '-g', '48', '-bf', '2', *params, '-c:a', audio, str(path))


def stream_hashes(path):
    return run('ffmpeg', '-v', 'error', '-nostdin', '-i', str(path), '-map', '0:v:0', '-map', '0:a:0',
               '-c', 'copy', '-f', 'streamhash', '-').splitlines()


def video_packets(path):
    return probe(path, '-select_streams', 'v:0', '-show_packets', '-show_data_hash', 'sha256',
                 '-show_entries', 'packet=flags,dts,pts_time,data_hash')['packets']


def verify_seek(source, destination, tag, expected):
    # Input seek lands near the requested time before any packets are copied.
    run('ffmpeg', '-v', 'error', '-nostdin', '-ss', '12.5', '-i', str(source),
        '-map', '0:v:0', '-map', '0:a:0', '-t', '5.9', '-c', 'copy', '-tag:v', tag,
        '-movflags', '+frag_keyframe+empty_moov+default_base_moof', str(destination))
    packets = video_packets(destination)
    hashes = [packet['data_hash'] for packet in packets]
    if 'K' not in packets[0]['flags'] or hashes[:len(expected)] != expected:
        raise ValueError('Input seek did not restart on the requested fragment’s source keyframe.')
    first = next(packet for packet in video_packets(source) if packet['data_hash'] == hashes[0])
    return dict(requested_seconds=12.5, source_keyframe_seconds=float(first['pts_time']),
                matching_video_packets=len(expected))


def verify(source, playlist, tag):
    hashes = stream_hashes(source)
    if hashes != stream_hashes(playlist):
        raise ValueError('The HLS mux changed the compressed video or audio.')
    directory = playlist.parent
    initialization = directory / 'init.mp4'
    init = initialization.read_bytes()
    video_info = probe(initialization, '-select_streams', 'v:0',
                       '-show_entries', 'stream=codec_tag_string,time_base')['streams'][0]
    if video_info['codec_tag_string'] != tag:
        raise ValueError('Unexpected video sample entry in the initialization segment.')

    parts = sorted(directory.glob('part-*.m4s'))
    if len(parts) < 3:
        raise ValueError('Expected multiple independently testable fragments.')
    time_base = Fraction(video_info['time_base'])
    previous_dts = None
    results = []
    seek = None
    for part in parts:
        # A fresh decoder gets only the init and requested fragment, just as it
        # would after a seek. Earlier media fragments are absent from this file.
        fragment = directory / 'single.mp4'
        fragment.write_bytes(init + part.read_bytes())
        packets = video_packets(fragment)
        if not packets or 'K' not in packets[0]['flags']:
            raise ValueError('A fragment did not begin with a video sync sample.')
        dts = [packet['dts'] for packet in packets]
        if previous_dts is not None and abs((dts[0] - previous_dts) * time_base - Fraction(1, 24)) > Fraction(2, 1000):
            raise ValueError('Unexpected decode timestamp gap at a fragment boundary.')
        previous_dts = dts[-1]
        run('ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-i', str(fragment),
            '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-')
        if part == parts[2]:
            seek = verify_seek(source, directory / 'seek.mp4', tag, [packet['data_hash'] for packet in packets])
        results.append(dict(fragment=part.name, video_samples=len(packets), first_dts=dts[0]))
    return dict(sample_entry=tag, stream_hashes=hashes, fragments=results, seek=seek)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New JSON report under test-results')
    args = parser.parse_args()
    with scratch() as workspace:
        cases = {}
        for codec in ('h264', 'hevc'):
            source = workspace / (codec + '.mkv')
            make_fixture(source, codec)
            playlist, tag = remux(source, workspace / codec)
            cases[codec] = verify(source, playlist, tag)
        unsupported = workspace / 'opus.mkv'
        make_fixture(unsupported, 'h264', audio='libopus')
        try:
            remux(unsupported, workspace / 'opus')
        except ValueError:
            if (workspace / 'opus').exists():
                raise
        else:
            raise RuntimeError('The initial remux profile accepted Opus.')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as report:
            json.dump(dict(scope='Host FFmpeg with synthetic SDR MKVs', cases=cases,
                           opus_rejected=True), report, indent=2)
            report.write('\n')
    print(f'Remux validation passed. Report: {args.output}')


if __name__ == '__main__':
    main()
