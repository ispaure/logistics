"""Document workspace actions follow contributed tools in the launch catalog."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from types import SimpleNamespace as State
from unittest import TestCase
from commonUtils.testing.stages import TestStage
from desktop.navigation.catalog import LaunchCatalog

TEST_STAGE = TestStage.REGRESSION


class CatalogOrderingTests(TestCase):
    def test_workspace_actions_stay_after_contributed_tools(self):
        item = State(page_id='fixture.page', navigation_icon='fixture', name='Fixture', launch_description='Fixture tool')
        registry = State(get_feature_states=lambda: [],
            get_pages=lambda: [State(feature_name='fixture', contribution=item)],
            get_document_launchers=lambda: [])
        page = object()
        catalog = LaunchCatalog(core_types={}, registry_provider=registry)
        snapshot = catalog.snapshot([], {('fixture', 'fixture.page'): page},
            is_present=lambda candidate: candidate is page, actions=State(count=1))
        self.assertEqual([entry.key for entry in snapshot.destinations],
                         ['bulk_rename', 'feature:fixture:fixture.page', 'actions'])
