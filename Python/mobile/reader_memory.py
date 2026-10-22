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
        count(getattr(source, 'data', None))
        count(getattr(reader, 'text', None))
        count(getattr(getattr(owner, 'crypt_text', None), 'value', None))
        for value in getattr(source, 'cache', {}).values():
            count(value)
    return total
