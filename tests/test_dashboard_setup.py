"""Dashboard provisioning checks without requiring a running HA instance."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'meter_snap'
package = ModuleType('meter_snap_dashboard_tests')
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
spec = importlib.util.spec_from_file_location(package.__name__ + '.dashboard_setup', ROOT / 'dashboard_setup.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ConfigNotFound(Exception):
    pass


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.saved = {}
        self.writes = []
        self.panels = {}
        saved, writes = self.saved, self.writes

        class Storage:
            def __init__(self, hass, config):
                self.config = config
                self.key = config['id']

            async def async_load(self, force):
                if self.key not in saved:
                    raise ConfigNotFound()
                return copy.deepcopy(saved[self.key])

            async def async_save(self, config):
                writes.append(copy.deepcopy(config))
                saved[self.key] = copy.deepcopy(config)

        self.frontend = ModuleType('homeassistant.components.frontend')
        self.frontend.async_panel_exists = lambda hass, url: url in self.panels
        self.frontend.async_register_built_in_panel = lambda hass, component, **kwargs: self.panels.update({kwargs['frontend_url_path']: kwargs})
        self.frontend.async_remove_panel = lambda hass, url: self.panels.pop(url, None)
        modules = {name: ModuleType(name) for name in [
            'homeassistant', 'homeassistant.components', 'homeassistant.components.lovelace',
            'homeassistant.components.lovelace.const', 'homeassistant.components.lovelace.dashboard',
        ]}
        modules['homeassistant.components.frontend'] = self.frontend
        modules['homeassistant.components'].frontend = self.frontend
        modules['homeassistant.components.lovelace.const'].ConfigNotFound = ConfigNotFound
        modules['homeassistant.components.lovelace.dashboard'].LovelaceStorage = Storage
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.other = object()
        self.dashboards = {'other-dashboard': self.other}
        self.hass = SimpleNamespace(data={'lovelace': SimpleNamespace(dashboards=self.dashboards)})

    async def test_seed_edit_unload_and_reload_preserves_contents(self):
        unload = await module.async_setup_dashboard(self.hass, {})
        self.assertIn(module.DASHBOARD_URL, self.panels)
        self.assertIs(self.dashboards['other-dashboard'], self.other)
        dashboard = self.dashboards[module.DASHBOARD_URL]
        edited = {'views': [{'title': 'My edited dashboard', 'cards': []}]}
        await dashboard.async_save(edited)
        unload()
        self.assertNotIn(module.DASHBOARD_URL, self.dashboards)
        self.assertNotIn(module.DASHBOARD_URL, self.panels)
        self.assertEqual(self.saved[module.DASHBOARD_ID], edited)
        await module.async_setup_dashboard(self.hass, {'gas_enabled': False})
        self.assertEqual(self.saved[module.DASHBOARD_ID], edited)
        self.assertEqual(len(self.writes), 2)  # one seed, one user edit

    async def test_existing_dashboard_or_panel_never_overwritten(self):
        for collision in ['dashboard', 'panel']:
            with self.subTest(collision=collision):
                target = self.dashboards if collision == 'dashboard' else self.panels
                target[module.DASHBOARD_URL] = self.other
                with self.assertRaises(RuntimeError):
                    await module.async_setup_dashboard(self.hass, {})
                self.assertIs(target[module.DASHBOARD_URL], self.other)
                self.assertEqual(self.writes, [])
                target.pop(module.DASHBOARD_URL)

    async def test_dict_lovelace_and_repeat_setup(self):
        self.hass.data['lovelace'] = {'dashboards': self.dashboards}
        await module.async_setup_dashboard(self.hass, {})
        with self.assertRaises(RuntimeError):
            await module.async_setup_dashboard(self.hass, {})
        self.assertEqual(len(self.writes), 1)

    async def test_panel_registration_failure_rolls_back_runtime(self):
        self.frontend.async_register_built_in_panel = Mock(side_effect=RuntimeError('registration failed'))
        with self.assertRaises(RuntimeError):
            await module.async_setup_dashboard(self.hass, {})
        self.assertNotIn(module.DASHBOARD_URL, self.dashboards)
        self.assertIs(self.dashboards['other-dashboard'], self.other)
        self.assertIn(module.DASHBOARD_ID, self.saved)  # retry retains saved contents

    def test_layout_respects_enabled_meters(self):
        for electricity, gas, meter in [(True, True, 'switchable'), (True, False, 'electricity'), (False, True, 'gas'), (False, False, None)]:
            with self.subTest(electricity=electricity, gas=gas):
                config = module.dashboard_config({'electricity_enabled': electricity, 'gas_enabled': gas})
                cards = config['views'][0]['cards']
                types = [card['type'] for card in cards]
                self.assertEqual('energy-usage-graph' in types, electricity)
                self.assertEqual('energy-gas-graph' in types, gas)
                self.assertIn('energy-date-selection', types)
                capture = next((card for card in cards if card['type'] == 'custom:meter-snap-card'), None)
                self.assertEqual(capture['meter'] if capture else None, meter)
                if capture:
                    self.assertEqual(capture['sections'], ['header', 'capture'])

    def test_translations_include_setup_and_options(self):
        for file in ['strings.json', 'translations/de.json', 'translations/en.json']:
            data = json.loads((ROOT / file).read_text())
            for flow in ['config', 'options']:
                self.assertIn('energy_dashboard', data[flow]['step']['dashboard']['data'])
            self.assertIn('dashboard', data['options']['step']['init']['menu_options'])


if __name__ == '__main__':
    unittest.main()
