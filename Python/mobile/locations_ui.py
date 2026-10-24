"""Files location commands retain safe identities and reject expired connections."""
import asyncio
from .locations import Locations


class LocationsUI:
    def pinned_locations(self):
        if not hasattr(self, 'locations'):
            self.locations = Locations(self.private_root)
        return self.locations

    def pin_local_folder(self, widget=None, **kwargs):
        try:
            if self.file_storage.value != 'Local files':
                raise ValueError('Encrypted folder paths stay private and cannot be pinned for restoration.')
            self.pinned_locations().pin('local', self.file_path)
            self.file_status.value = 'Folder pinned in Workspaces.'
        except (OSError, ValueError) as error:
            self.file_status.value = str(error)

    async def pin_remote_folder(self, widget=None, **kwargs):
        try:
            remote = self.cloud_open_remote
            if self.cloud_busy or not remote:
                raise ValueError('Browse a remote folder first.')
            if remote in self.cloud_crypt_remotes:
                raise ValueError('Encrypted folder paths stay private and cannot be pinned for restoration.')
            client, generation, path = self.cloud_client, self.cloud_client.generation, self.cloud_path
            identity = await asyncio.to_thread(client.connection_identity, remote)
            if not self.active_host or client is not self.cloud_client or client.generation != generation:
                return
            self.pinned_locations().pin('remote', path, identity)
            self.cloud_status.value = 'Folder pinned in Workspaces. It requires the same connection.'
        except (OSError, ValueError) as error:
            self.cloud_status.value = str(error)

    def pinned_opener(self, item):
        async def open_location(widget=None, **kwargs):
            try:
                if item['kind'] == 'local':
                    await self.show_local_location()
                    await self.browser_file_location(('Local files', item['path']))
                else:
                    self.show_cloud()
                    if getattr(self, 'cloud_restore_task', None):
                        await self.cloud_restore_task
                    if not self.active_host:
                        return
                    client, selector = self.cloud_client, self.cloud_remote
                    generation = client.generation
                    # Read the available names once. Workers and their results
                    # belong to this connection and these controls, even if the
                    # host replaces them while an identity lookup is running.
                    remotes = tuple(remote for remote in selector.items
                                    if remote not in self.cloud_crypt_remotes)
                    def current():
                        return (self.active_host and client is self.cloud_client
                                and client.generation == generation and selector is self.cloud_remote)
                    matches = []
                    for remote in remotes:
                        try:
                            identity = await asyncio.to_thread(client.connection_identity, remote)
                        except (OSError, ValueError, AttributeError):
                            if not current():
                                return
                            raise
                        if not current():
                            return
                        if identity == item['connection']:
                            matches.append(remote)
                    if len(matches) != 1:
                        raise ValueError('Pinned connection unavailable or changed. Load the original connection in Settings.')
                    selector.value = matches[0]
                    await self.browser_cloud_location((matches[0], item['path']))
            except (OSError, ValueError, AttributeError) as error:
                self.location_error = str(error)
                self.show_locations()
        return open_location

    def pinned_remover(self, key):
        def remove(widget=None, **kwargs):
            try:
                self.pinned_locations().remove(key)
                self.location_error = ''
            except (OSError, ValueError) as error:
                self.location_error = str(error)
            self.show_locations()
        return remove
