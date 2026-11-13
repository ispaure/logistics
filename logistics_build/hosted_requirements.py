"""Shared, dependency-free full-family coverage and reviewed automatic push defaults."""
from datetime import datetime, timedelta, timezone

REQUIRED = {
    'validate': ('.github/workflows/archive-platform-checks.yml',
                 {'static', 'macos', 'windows', 'Fedora desktop'}),
    'mobile-build': ('.github/workflows/mobile-build.yml',
                     {'Build shared iOS test app', 'Build shared Android test app', 'Validate Android',
                      'Validate iOS iphone', 'Validate iOS duo', 'Validate iOS ipad',
                      'Require every selected native check'}),
    'mobile-runtime': ('.github/workflows/mobile-runtime.yml', {'ios', 'android'}),
}

# These digests bind the actual push filters, full target scope, diagnostic
# defaults, source-based test environment and reuse policy reviewed here.
# Update deliberately alongside a workflow change; unknown contracts never adopt.
PUSH_DEFAULTS = {
    'archive-platform-checks.yml': dict(family='validate', targets=('macos', 'linux', 'windows'),
        sha256='cf2638789c5e3201ff4ffab8c63015e1debe993db15f3076f224ef48d00ba9c9'),
    'mobile-build.yml': dict(family='mobile-build', targets=('ios', 'android'),
        sha256='0ff8dddc90a0d9929720bd54fe5c80557876e1a710cb20f33f3058f2f1f88f19'),
    'mobile-runtime.yml': dict(family='mobile-runtime', targets=('ios', 'android'),
        sha256='2ee75804da9812bdd5fc81d779e4e011ce0748563bce024e20cc59e79279814d'),
}


def complete_family_jobs(jobs, family, *, now=None, max_age=timedelta(hours=24)):
    """A top-level green conclusion never substitutes for complete fresh jobs."""
    now = now or datetime.now(timezone.utc)
    required = REQUIRED[family][1]
    selected = []
    for name in sorted(required):
        rows = [row for row in jobs if row.get('name') == name]
        if len(rows) != 1:
            raise ValueError('Hosted evidence lacks unambiguous full-family job coverage: ' + name)
        row = rows[0]
        if row.get('status') != 'completed' or row.get('conclusion') != 'success' or not row.get('completed_at'):
            raise ValueError('A required full-family hosted job did not pass: ' + name)
        stamp = datetime.fromisoformat(row['completed_at'].replace('Z', '+00:00'))
        if stamp.tzinfo is None or not timedelta(0) <= now - stamp <= max_age:
            raise ValueError('Hosted full-family job evidence is stale or invalid.')
        selected.append(stamp)
    return dict(jobs=sorted(required), oldest_completed_at=min(selected).isoformat())
