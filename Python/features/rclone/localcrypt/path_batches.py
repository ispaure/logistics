"""Bounded, call-local mapping of crypt (path, directory) pairs.

Shared by CLI and native adapters. No credential or plaintext cache outlives a
call, and a revoked/partial batch can never return a partial mapping.
"""


def map_path_entries(entries, resolve, *, check, batch_size=128, max_bytes=24 * 1024):
    """Deduplicate pairs, bound requests by count and bytes, preserve input order."""
    check()
    entries = list(entries)
    if batch_size < 1 or max_bytes < 1:
        raise ValueError('Invalid encrypted path batch limits.')
    unique = {}
    for entry in entries:
        if (not isinstance(entry, tuple) or len(entry) != 2 or not isinstance(entry[0], str)
                or type(entry[1]) is not bool or '\x00' in entry[0]):
            raise ValueError('Invalid encrypted path batch entry.')
        unique.setdefault(entry, None)
    batch, size = [], 0

    def flush():
        check()
        result = resolve(batch)
        check()
        if (not isinstance(result, (list, tuple)) or len(result) != len(batch)
                or not all(isinstance(path, str) and '\x00' not in path and (path or not entry[0])
                           for entry, path in zip(batch, result))):
            raise ValueError('Incomplete or invalid encrypted path batch result.')
        for entry, path in zip(batch, result):
            unique[entry] = path

    for entry in unique:
        # Reserve space for JSON/command quoting as well as the path itself.
        cost = 2 * len(entry[0].encode('utf-8')) + 64
        if cost > max_bytes:
            raise ValueError('Encrypted path exceeds the batch byte limit.')
        if batch and (len(batch) >= batch_size or size + cost > max_bytes):
            flush()
            batch, size = [], 0
        batch.append(entry)
        size += cost
    if batch:
        flush()
    check()
    return [unique[entry] for entry in entries]


def native_path_entries(client, remote, identity, entries, *, check, encode=False):
    """Map native crypt paths in bounded calls; decoding remains the default."""
    def resolve(batch):
        values = [dict(path=path, directory=directory, **({'encode': True} if encode else {}))
                  for path, directory in batch]
        return client.request('crypt_paths', remote=remote, identity=identity, entries=values)
    return map_path_entries(entries, resolve, check=check, batch_size=256)
