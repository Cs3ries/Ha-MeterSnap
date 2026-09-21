"""Resource lifecycle checks runnable without a Home Assistant installation."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'meter_snap'
package = ModuleType('meter_snap_resource_tests')
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location(package.__name__ + '.frontend_setup', ROOT / 'frontend_setup.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Resources:
    def __init__(self, items):
        self.items = items
        self.loaded = False
        self.loads = 0
        self.writes = 0

    async def async_load(self):
        self.loads += 1

    def async_items(self):
        return self.items

    async def async_create_item(self, data):
        self.writes += 1
        self.items.append(dict(id='new', url=data['url'], type=data['res_type']))

    async def async_update_item(self, item_id, data):
        self.writes += 1
        next(i for i in self.items if i['id'] == item_id).update(url=data['url'], type=data['res_type'])

    async def async_delete_item(self, item_id):
        self.writes += 1
        self.items[:] = [i for i in self.items if i['id'] != item_id]


class ResourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_and_repeat(self):
        r = Resources([])
        hass = SimpleNamespace(data={'lovelace': SimpleNamespace(resources=r)})
        await module.async_register_card(hass)
        await module.async_register_card(hass)
        self.assertEqual((r.loads, r.writes, len(r.items)), (1, 1, 1))
        self.assertEqual(r.items[0]['url'], module.CARD_URL)

    async def test_migrate_duplicates_preserve_other_resources(self):
        other = dict(id='other', url='/local/another-card.js', type='module')
        remote = dict(id='remote', url='https://example.org/meter-snap-card.js', type='module')
        r = Resources([dict(id='old', url='/local/meter-snap-card.js?v=old', type='js'), dict(id='duplicate', url='/meter_snap_frontend/meter-snap-card.js', type='module'), other.copy(), remote.copy()])
        await module.async_register_card(SimpleNamespace(data={'lovelace': {'resources': r}}))
        self.assertEqual(r.items, [dict(id='old', url=module.CARD_URL, type='module'), other, remote])

    async def test_yaml_untouched(self):
        r = SimpleNamespace(data=[dict(url='/local/test.js', type='module')])
        await module.async_register_card(SimpleNamespace(data={'lovelace': SimpleNamespace(resources=r)}))
        self.assertEqual(r.data, [dict(url='/local/test.js', type='module')])

    async def test_failure_does_not_break_integration(self):
        r = Resources([])
        r.async_create_item = AsyncMock(side_effect=RuntimeError('write failed'))
        with self.assertLogs(module._LOGGER, level='ERROR'):
            await module.async_register_card(SimpleNamespace(data={'lovelace': SimpleNamespace(resources=r)}))


if __name__ == '__main__':
    unittest.main()
