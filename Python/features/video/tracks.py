"""Compact audio identity shared by desktop menus and native HLS renditions."""

import re


def compact_codec(value):
    value = str(value or '').strip()
    key = re.sub(r'[^a-z0-9]', '', value.lower())
    aliases = {
        'a52': 'AC-3', 'ac3': 'AC-3', 'audiocoding3ac3': 'AC-3',
        'eac3': 'E-AC-3', 'audiocoding3eac3': 'E-AC-3', 'enhancedac3': 'E-AC-3',
        'a52baudioakaeac3': 'E-AC-3',
        'truehd': 'TrueHD', 'trhd': 'TrueHD', 'dolbytruehd': 'TrueHD',
        'mp4a': 'AAC', 'aac': 'AAC', 'mpeg4audioaac': 'AAC',
        'mpegaacaudio': 'AAC', 'mpegaacaudiomp4a': 'AAC',
        'dts': 'DTS', 'dtsc': 'DTS', 'dtsaudio': 'DTS',
        'flac': 'FLAC', 'opus': 'Opus', 'vorbis': 'Vorbis', 'mp3': 'MP3',
    }
    return aliases.get(key, value)


def audio_label(number, *, title='', description='', language='', codec='', channels=0,
                sample_rate=0, default=False, roles=()):
    """Keep supplied identity; never guess language or layout from channel count.

    Numbers disambiguate streams with identical/missing tags. 48 kHz is the
    ordinary movie rate, so show a rate only when it adds unusual information.
    """
    codec = compact_codec(codec)
    parts = []
    seen = set()
    generic = {'', 'und', 'unknown', 'undefined', 'audio'}
    if channels:
        generic.update(('surround', 'stereo', 'mono'))
    for value in (language, title, description, *roles):
        value = ' '.join(str(value or '').split())
        key = value.casefold()
        if key in generic or re.fullmatch(r'(?:audio\s*)?track\s*\d+', key):
            continue
        if compact_codec(value).casefold() == codec.casefold() or key in seen:
            continue
        seen.add(key)
        parts.append(value)
    if codec:
        parts.append(codec)
    if channels > 0:
        parts.append({1: 'Mono', 2: 'Stereo'}.get(channels, f'{channels} ch'))
    if sample_rate > 0 and sample_rate != 48000:
        parts.append(f'{sample_rate / 1000:g} kHz')
    if default:
        parts.append('Default')
    return ' · '.join([f'#{number}', *(parts or ['Audio'])])
