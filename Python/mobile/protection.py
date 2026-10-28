"""Bind mobile composition to its shared process credential protection scope."""


def for_app(app):
    scope = getattr(app, '_protection', None)
    if scope is None:
        from features.rclone.mobile.cloud import CloudClient
        app._protection = scope = CloudClient.credential_state.protection.window()
    return scope
