"""Credential-safe diagnostics shared by desktop and native presentation."""


def report_failure(operation, error):
    """Log error type and source locations, never exception text or frame locals.

    Credential exceptions may embed passwords, tokens, package contents or paths.
    Source locations preserve debugging context without recording that material.
    Callers supply a fixed operation label, never a package or remote name.
    """
    import traceback
    from commonUtils.runtime.diagnostics import Severity, log

    try:
        frames = traceback.extract_tb(error.__traceback__)
        locations = " -> ".join(f"{frame.name}:{frame.lineno}" for frame in frames)
        log(
            Severity.ERROR,
            "rclone credentials",
            f"{operation}: {type(error).__name__} at {locations}",
        )
    except Exception:
        # A failing diagnostic sink must never replace the credential error or
        # prevent the UI's failure/cleanup path. Do not fall back to raw text.
        pass
