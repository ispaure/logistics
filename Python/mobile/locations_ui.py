"""Folder pin persistence and commands; connection details stay with composition."""
from .locations import Locations


class LocationsUI:
    def pinned_locations(self):
        if not hasattr(self, 'locations'):
            self.locations = Locations(self.host.private_root())
        return self.locations

    def pin_local_folder(self, widget=None, **kwargs):
        try:
            self.pinned_locations().pin('local', self.host.local_folder())
            self.host.local_status('Folder pinned in Workspaces.')
        except (OSError, ValueError) as error:
            self.host.local_status(str(error))

    async def pin_remote_folder(self, widget=None, **kwargs):
        try:
            target = await self.host.remote_folder()
            if target is None:  # The originating connection or window retired.
                return
            path, identity = target
            self.pinned_locations().pin('remote', path, identity)
            self.host.remote_status('Folder pinned in Workspaces. It requires the same connection.')
        except (OSError, ValueError) as error:
            self.host.remote_status(str(error))

    def pinned_opener(self, item):
        async def open_location(widget=None, **kwargs):
            try:
                if item['kind'] == 'local':
                    await self.host.open_local(item['path'])
                else:
                    await self.host.open_remote(item['connection'], item['path'])
            except (OSError, ValueError, AttributeError) as error:
                self.location_error = str(error)
                self.host.show_locations()
        return open_location

    def pinned_remover(self, key):
        def remove(widget=None, **kwargs):
            try:
                self.pinned_locations().remove(key)
                self.location_error = ''
            except (OSError, ValueError) as error:
                self.location_error = str(error)
            self.host.show_locations()
        return remove
