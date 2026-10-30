"""Bind folder pins to current browser owners, without forwarding app state."""
import asyncio
from mobile.locations_controller import LocationHost


def locations_host(app):
    def local_folder():
        if app.file_storage.value != 'Local files':
            raise ValueError('Encrypted folder paths stay private and cannot be pinned for restoration.')
        return app.file_path

    async def remote_folder():
        cloud = app.cloud_controller()
        remote = cloud.cloud_open_remote
        if cloud.cloud_busy or not remote:
            raise ValueError('Browse a remote folder first.')
        if remote in cloud.cloud_crypt_remotes:
            raise ValueError('Encrypted folder paths stay private and cannot be pinned for restoration.')
        client, path = cloud.cloud_client, cloud.cloud_path
        generation = client.generation
        try:
            identity = await asyncio.to_thread(client.connection_identity, remote)
        except (OSError, ValueError):
            if not current(cloud, client, generation):
                return None
            raise
        return (path, identity) if current(cloud, client, generation) else None

    def current(cloud, client, generation):
        return (app.active_host and app.cloud_controller() is cloud
                and cloud.cloud_client is client and client.generation == generation)

    async def open_local(path):
        if not app.active_host:
            return
        opened = await app.show_local_location()
        if opened is False or not app.active_host:
            return
        await app.browser_file_location(('Local files', path))

    async def open_remote(identity, path):
        # The host owns scene restrictions and save/checkpoint vetoes. A direct
        # call to CloudController.show_cloud would bypass secondary-window rules.
        if not app.active_host or app.show_cloud() is False:
            return
        cloud = app.cloud_controller()
        origin = getattr(app, 'navigation_generation', None)
        def current_navigation():
            return (app.active_host and app.cloud_controller() is cloud
                    and getattr(app, 'navigation_generation', None) == origin)
        restore = getattr(cloud, 'cloud_restore_task', None)
        if restore is not None:
            # This task belongs to startup, independently of one pin request.
            await asyncio.shield(restore)
        if not current_navigation():
            return
        client, selector = cloud.cloud_client, cloud.cloud_remote
        generation = client.generation
        remotes = tuple(remote for remote in selector.items if remote not in cloud.cloud_crypt_remotes)
        def valid():
            return (current_navigation() and current(cloud, client, generation)
                    and cloud.cloud_remote is selector)
        matches = []
        for remote in remotes:
            try:
                found = await asyncio.to_thread(client.connection_identity, remote)
            except (OSError, ValueError, AttributeError):
                if not valid():
                    return
                raise
            if not valid():
                return
            if found == identity:
                matches.append(remote)
        if len(matches) != 1:
            raise ValueError('Pinned connection unavailable or changed. Load the original connection in Settings.')
        selector.value = matches[0]
        await cloud.browser_cloud_location((matches[0], path))

    return LocationHost(
        private_root=lambda: app.private_root,
        local_folder=local_folder, remote_folder=remote_folder,
        local_status=lambda message: setattr(app.file_status, 'value', message),
        remote_status=lambda message: setattr(app.cloud_controller().cloud_status, 'value', message),
        open_local=open_local, open_remote=open_remote, show_locations=app.show_locations)
