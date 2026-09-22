"""Exercise the actual setup/options flow with lightweight HA form adapters."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'meter_snap'


class Field:
    def __init__(self, key, default=None):
        self.key = key
        self.default = default


class Flow:
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__()

    def async_show_form(self, **kwargs):
        return {'type': 'form', **kwargs}

    def async_show_menu(self, **kwargs):
        return {'type': 'menu', **kwargs}

    def async_create_entry(self, **kwargs):
        return {'type': 'create_entry', **kwargs}


class DashboardFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        names = ['homeassistant', 'homeassistant.config_entries', 'homeassistant.core',
                 'homeassistant.data_entry_flow', 'homeassistant.helpers',
                 'homeassistant.helpers.config_validation', 'homeassistant.helpers.aiohttp_client',
                 'aiohttp', 'voluptuous']
        modules = {name: ModuleType(name) for name in names}
        modules['homeassistant'].config_entries = modules['homeassistant.config_entries']
        modules['homeassistant.config_entries'].ConfigFlow = Flow
        modules['homeassistant.config_entries'].OptionsFlow = Flow
        modules['homeassistant.core'].callback = lambda fn: fn
        modules['homeassistant.data_entry_flow'].FlowResult = dict
        modules['homeassistant.helpers.config_validation'].boolean = bool
        modules['homeassistant.helpers.config_validation'].string = str
        modules['homeassistant.helpers.aiohttp_client'].async_get_clientsession = lambda hass: None
        modules['voluptuous'].Schema = lambda fields: fields
        modules['voluptuous'].Required = Field
        modules['voluptuous'].Coerce = lambda kind: kind
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        package = ModuleType('meter_snap_flow_tests')
        package.__path__ = [str(ROOT)]
        sys.modules[package.__name__] = package
        spec = importlib.util.spec_from_file_location(package.__name__ + '.config_flow', ROOT / 'config_flow.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    async def test_initial_flow_offers_dashboard_after_gas_and_defaults_off(self):
        for enable in [False, True]:
            with self.subTest(enable=enable):
                flow = self.module.MeterSnapConfigFlow()
                flow._data = {'electricity_enabled': True, 'api_key': 'unchanged'}
                form = await flow.async_step_gas({'gas_enabled': False})
                self.assertEqual(form['step_id'], 'dashboard')
                field = next(iter(form['data_schema']))
                self.assertEqual((field.key, field.default), ('energy_dashboard', False))
                result = await flow.async_step_dashboard({'energy_dashboard': enable})
                self.assertEqual(result['type'], 'create_entry')
                self.assertEqual(result['data'], {'electricity_enabled': True, 'gas_enabled': False, 'api_key': 'unchanged', 'energy_dashboard': enable})

    async def test_options_menu_enable_disable_preserves_tariffs_and_credentials(self):
        entry = SimpleNamespace(data={'api_key': 'unchanged', 'electricity_unit_price': 0.32}, options={'gas_unit_price': 0.10})
        flow = self.module.MeterSnapOptionsFlow(entry)
        menu = await flow.async_step_init()
        self.assertIn('dashboard', menu['menu_options'])
        result = await flow.async_step_dashboard({'energy_dashboard': True})
        self.assertEqual(result['data']['api_key'], 'unchanged')
        self.assertEqual(result['data']['electricity_unit_price'], 0.32)
        self.assertEqual(result['data']['gas_unit_price'], 0.10)
        entry.options = result['data']
        flow = self.module.MeterSnapOptionsFlow(entry)
        form = await flow.async_step_dashboard()
        self.assertTrue(next(iter(form['data_schema'])).default)
        result = await flow.async_step_dashboard({'energy_dashboard': False})
        self.assertFalse(result['data']['energy_dashboard'])
        self.assertEqual(result['data']['api_key'], 'unchanged')


if __name__ == '__main__':
    unittest.main()
