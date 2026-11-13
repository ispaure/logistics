"""Reader allocation policy; all measured content remains session-only in RAM.

Managed reserves exclude interpreter, WebKit and operating-system allocations.
Go's native archive pool has the matching 128 MiB admission limit. The original
128 MiB per-archive limit remains supported; a second snapshot needs free space.
"""
MIB = 1024 * 1024
NATIVE_ARCHIVE_POOL = 128 * MIB
PRIVATE_BUFFERS = 32 * MIB
# One displayed bitmap and its replacement, plus one bounded decode scratch page.
BITMAP_RESERVE = 128 * MIB
DECODE_RESERVE = 64 * MIB
BRIDGE_RESERVE = 32 * MIB
MANAGED_RESERVE = (NATIVE_ARCHIVE_POOL + PRIVATE_BUFFERS + BITMAP_RESERVE
                   + DECODE_RESERVE + BRIDGE_RESERVE)


def content_sources(source):
    """Include decoded storage behind a generic retained-content wrapper."""
    seen = set()
    while source is not None and id(source) not in seen:
        seen.add(id(source))
        yield source
        source = getattr(source, 'backend', None)


def trim_content_cache(source):
    for item in content_sources(source):
        cache = getattr(item, 'cache', None)
        if cache is not None:
            cache.clear()
            item.cache_bytes = 0


def private_buffer_bytes(owners):
    """Count distinct reader/source buffers, member caches and current edit strings."""
    seen, total = set(), 0
    def count(value):
        nonlocal total
        if isinstance(value, (bytes, bytearray, str)) and id(value) not in seen:
            seen.add(id(value))
            total += len(value) * (4 if isinstance(value, str) else 1)
    for owner in owners:
        reader = getattr(owner, 'crypt_reader', None)
        source = getattr(reader, 'source', None)
        count(getattr(reader, 'data', None))
        for item in content_sources(source):
            count(getattr(item, 'data', None))
            for value in getattr(item, 'cache', {}).values():
                count(value)
        count(getattr(reader, 'text', None))
        count(getattr(getattr(owner, 'crypt_text', None), 'value', None))
    return total
