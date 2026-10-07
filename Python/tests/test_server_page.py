"""Server grouping, refresh selection, and plain-text detail presentation."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from unittest.mock import Mock, patch
import unittest

from commonUtils.ui import pyside as qt
from features.contributions import RegisteredContribution, ServerProviderContribution
from ui_new.pages.servers import ServersPage


class ServerPageTests(unittest.TestCase):
    def setUp(self):
        self.app = qt.QApplication.instance() or qt.QApplication([])
        self.servers = []
        self.providers = []
        patcher = patch('features.registry.get_server_providers',
                        side_effect=lambda: self.providers)
        patcher.start()
        self.addCleanup(patcher.stop)

    def provider(self, feature='feature', name='Servers'):
        provider = ServerProviderContribution(
            name=name,
            get_servers=Mock(side_effect=lambda: self.servers),
            get_display_name=lambda server: server['name'],
            get_group_name=lambda server: server['group'],
            get_details=lambda server: [('Location', server['path'])],
            get_actions=Mock(return_value=[]),
        )
        registered = RegisteredContribution(feature, feature.title(), provider)
        self.providers.append(registered)
        return registered

    def page(self):
        page = ServersPage()
        self.addCleanup(page.deleteLater)
        return page

    def test_grouped_server_selection_survives_refresh(self):
        registered = self.provider()
        self.servers = [dict(name='One', group='Group', path='/one'),
                        dict(name='Two', group='Group', path='/two')]
        page = self.page()
        key = page._get_server_key(registered, self.servers[1])
        page.server_tree.setCurrentItem(page._server_items[key])
        page.refresh()
        self.assertEqual(page.selected_server_key, key)
        self.assertIs(page.server_tree.currentItem(), page._server_items[key])
        self.assertEqual(registered.contribution.get_servers.call_count, 2)

    def test_same_named_servers_from_different_features_remain_distinct(self):
        self.provider('one')
        self.provider('two')
        self.servers = [dict(name='Shared', group='Group', path='/shared')]
        page = self.page()
        self.assertEqual(len(page._server_items), 2)
        self.assertEqual({key[0] for key in page._server_items}, {'one', 'two'})

    def test_refresh_removes_stale_selection_when_provider_becomes_empty(self):
        self.provider()
        self.servers = [dict(name='One', group='Group', path='/one')]
        page = self.page()
        self.servers.clear()
        page.refresh()
        self.assertIsNone(page.selected_server_key)
        self.assertFalse(page._server_items)
        labels = page.detail_scroll.widget().findChildren(qt.QLabel)
        self.assertTrue(any('no servers were discovered' in label.text() for label in labels))

    def test_server_names_and_detail_values_render_as_plain_text(self):
        self.provider(name='<b>Provider</b>')
        self.servers = [dict(name='<b>Server</b>', group='<b>Group</b>', path='<b>Path</b>')]
        page = self.page()
        labels = page.detail_scroll.widget().findChildren(qt.QLabel)
        expected = {'<b>Provider</b>', '<b>Server</b>', '<b>Group</b>', '<b>Path</b>'}
        selected = [label for label in labels if label.text() in expected]
        self.assertEqual({label.text() for label in selected}, expected)
        self.assertTrue(all(label.textFormat() == qt.Qt.TextFormat.PlainText for label in selected))
