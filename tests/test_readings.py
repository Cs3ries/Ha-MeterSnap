"""Exercise real storage/validation logic with a minimal HA Store adapter."""
import asyncio
from copy import deepcopy
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / 'custom_components' / 'meter_snap'


class Store:
    def __init__(self, *args):
        self.data = None
        self.fail = False

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        if self.fail:
            raise OSError('disk full')
        self.data = deepcopy(data)


def stamp(day):
    return f'2026-01-{day:02d}T12:00:00+00:00'


class ReadingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        modules = {n: ModuleType(n) for n in ['homeassistant', 'homeassistant.core', 'homeassistant.helpers', 'homeassistant.helpers.storage']}
        modules['homeassistant.core'].HomeAssistant = object
        modules['homeassistant.helpers.storage'].Store = Store
        self.patch = patch.dict(sys.modules, modules)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        package = ModuleType('meter_snap_reading_tests')
        package.__path__ = [str(ROOT)]
        sys.modules[package.__name__] = package
        self.module = importlib.import_module(package.__name__ + '.coordinator')
        self.hass = SimpleNamespace(config=SimpleNamespace(path=lambda _: '/nonexistent/metersnap-test'))
        self.entry = SimpleNamespace(data={}, options={})
        self.c = self.module.MeterSnapCoordinator(self.hass, self.entry)

    async def add(self, value, day, **kwargs):
        return await self.c.async_add_reading('electricity', value, stamp(day), **kwargs)

    async def edit(self, entry, value, day, **kwargs):
        return await self.c.async_write_reading('electricity', value, stamp(day), entry_id=entry['id'], **kwargs)

    def total(self):
        return self.c.get_statistics('electricity')['total']

    async def test_invalid_numbers_and_dates_do_not_mutate(self):
        for value in [-1, float('nan'), float('inf'), '-Infinity', 'bad', '', None, True]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                await self.add(value, 1)
        for time in ['', 'nonsense', '2026-13-01T00:00:00', '2026-01-01']:
            with self.subTest(time=time), self.assertRaises(ValueError):
                await self.c.async_add_reading('electricity', 1, time)
        self.assertEqual(self.c.get_readings('electricity'), [])
        self.assertIsNone(self.c._store.data)

    async def test_duplicate_instants_with_timezone_offsets(self):
        await self.add(100, 1)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            await self.c.async_add_reading('electricity', 110, '2026-01-01T13:00:00+01:00')

    async def test_backfill_checks_both_neighbors(self):
        await self.add(100, 1)
        await self.add(130, 3)
        for value in [99, 131]:
            with self.assertRaisesRegex(ValueError, 'Decreasing'):
                await self.add(value, 2)
        await self.add(110, 2)
        self.assertEqual([r['consumption'] for r in self.c.get_readings('electricity')], [20, 10, 0])
        self.assertEqual(self.total(), 130)

    async def test_edit_recalculates_neighbors_and_preserves_id(self):
        await self.add(100, 1)
        middle = await self.add(110, 2)
        await self.add(130, 3)
        edited = await self.edit(middle, 115, 2, notes='corrected')
        self.assertEqual(edited['id'], middle['id'])
        self.assertEqual(edited['notes'], 'corrected')
        self.assertEqual([r['consumption'] for r in self.c.get_readings('electricity')], [15, 15, 0])
        self.assertEqual(self.total(), 130)
        with self.assertRaises(ValueError):
            await self.edit(middle, 140, 2)
        with self.assertRaises(ValueError):
            await self.edit(middle, 115, 3)

    async def test_correct_latest_then_continue_without_reset(self):
        await self.add(100, 1)
        latest = await self.add(130, 3)
        await self.edit(latest, 120, 3)
        self.assertEqual(self.total(), 130)
        await self.add(125, 4)
        self.assertEqual(self.total(), 135)

    async def test_delete_latest_does_not_count_same_consumption_twice(self):
        await self.add(100, 1)
        latest = await self.add(130, 3)
        await self.c.async_delete_reading('electricity', latest['id'])
        self.assertEqual(self.total(), 130)
        await self.add(140, 4)
        self.assertEqual(self.total(), 140)
        self.assertEqual(self.c.get_readings('electricity')[0]['consumption'], 40)

    async def test_replacement_consumption_and_statistics(self):
        await self.add(1000, 1)
        replacement = await self.add(5, 2, kind='replacement', old_reading=1010)
        await self.add(12, 3)
        self.assertEqual([r['consumption'] for r in self.c.get_readings('electricity')], [7, 10, 0])
        self.assertEqual(self.total(), 1017)
        with self.assertRaises(ValueError):
            await self.c.async_delete_reading('electricity', replacement['id'])
        with self.assertRaises(ValueError):
            await self.edit(replacement, 6, 2, kind='replacement', old_reading=999)

    async def test_multiple_replacements_and_backfill(self):
        await self.add(1000, 1)
        await self.add(5, 3, kind='replacement', old_reading=1030)
        await self.add(0, 5, kind='replacement', old_reading=15)
        await self.add(1010, 2)
        await self.add(10, 4)
        await self.add(2, 6)
        self.assertEqual(self.total(), 1042)
        self.assertEqual(sum(r['consumption'] for r in self.c.get_readings('electricity')), 42)

    async def test_missing_replacement_values_stay_unknown(self):
        await self.add(1000, 1)
        repl = await self.add(None, 2, kind='replacement', old_reading=None)
        await self.add(10, 3)
        rows = self.c.get_readings('electricity')
        self.assertTrue(rows[0]['incomplete'])
        self.assertIsNone(rows[0]['consumption'])
        self.assertIsNone(self.c.get_kpis('electricity')['projected_monthly_cost'])
        self.assertEqual(self.total(), 1000)
        await self.edit(repl, 5, 2, kind='replacement', old_reading=1010)
        self.assertEqual(self.c.get_readings('electricity')[0]['consumption'], 5)
        self.assertEqual(self.total(), 1000)
        await self.add(12, 4)
        self.assertEqual(self.total(), 1002)

    async def test_missing_new_start_marks_replacement(self):
        await self.add(1000, 1)
        repl = await self.add(None, 2, kind='replacement', old_reading=1010)
        self.assertTrue(repl['incomplete'])
        self.assertEqual(repl['consumption'], 10)

    async def test_warning_is_interval_aware_and_requires_matching_confirmation(self):
        await self.add(0, 1)
        warning = await self.add(200, 2)
        self.assertTrue(warning['warning'])
        self.assertEqual(len(self.c.get_readings('electricity')), 1)
        self.assertEqual(warning['warnings'][0]['daily_rate'], 200)
        stale = await self.add(210, 2, confirmation=warning['confirmation'])
        self.assertTrue(stale['warning'])
        saved = await self.add(200, 2, confirmation=warning['confirmation'])
        self.assertIn('id', saved)
        long_interval = await self.add(1000, 20)
        self.assertNotIn('warning', long_interval)

    async def test_warning_checks_successor_for_backfill(self):
        await self.add(0, 1)
        await self.add(150, 3)
        warning = await self.c.async_add_reading('electricity', 0, '2026-01-03T11:00:00+00:00')
        self.assertEqual(warning['warnings'][0]['daily_rate'], 3600)

    async def test_persistence_failure_rolls_back_and_does_not_notify(self):
        await self.add(100, 1)
        calls = []
        self.c.register_listener(lambda: calls.append(True))
        self.c._store.fail = True
        with self.assertRaises(OSError):
            await self.add(110, 2)
        self.assertEqual(self.total(), 100)
        self.assertEqual(len(self.c.get_readings('electricity')), 1)
        self.assertEqual(calls, [])

    async def test_concurrent_duplicate_writes_are_serialized(self):
        results = await asyncio.gather(self.add(1, 1), self.add(2, 1), return_exceptions=True)
        self.assertEqual(sum(isinstance(r, ValueError) for r in results), 1)
        self.assertEqual(len(self.c.get_readings('electricity')), 1)

    async def test_migration_retains_records_and_unknown_metadata(self):
        records = [dict(id='a', reading=100, timestamp=stamp(1), notes='keep'),
                   dict(id='b', reading=90, timestamp=stamp(2), notes='legacy decrease')]
        self.c._store.data = {'electricity': records, 'gas': [], 'future_metadata': {'keep': 1}}
        await self.c.async_setup()
        saved = self.c._store.data
        self.assertEqual(saved['future_metadata'], {'keep': 1})
        self.assertEqual([(r['id'], r['reading'], r['notes']) for r in saved['electricity']],
                         [(r['id'], r['reading'], r['notes']) for r in records])
        self.assertTrue(saved['electricity'][1]['incomplete'])
        self.assertIsNone(saved['electricity'][1]['consumption'])
        self.assertEqual(self.total(), 90)
        await self.edit(records[1], 110, 2)
        self.assertEqual(self.total(), 90)

    async def test_restart_retains_statistics_after_correction(self):
        await self.add(100, 1)
        latest = await self.add(120, 2)
        await self.edit(latest, 110, 2)
        other = self.module.MeterSnapCoordinator(self.hass, self.entry)
        other._store.data = deepcopy(self.c._store.data)
        await other.async_setup()
        self.c = other
        await self.add(115, 3)
        self.assertEqual(self.total(), 125)

    async def test_gas_conversion_does_not_revalue_previous_total(self):
        await self.c.async_add_reading('gas', 100, stamp(1))
        original = self.c.get_statistics('gas')['energy']
        self.entry.options['gas_calorific_value'] = 20
        self.assertEqual(self.c.get_statistics('gas')['energy'], original)
        await self.c.async_add_reading('gas', 101, stamp(2))
        self.assertAlmostEqual(self.c.get_statistics('gas')['energy'] - original, round(self.c._factor('gas'), 2))

    async def test_edit_timestamp_reorders_and_checks_neighbors(self):
        a = await self.add(100, 1)
        b = await self.add(120, 3)
        with self.assertRaises(ValueError):
            await self.edit(a, 100, 4)
        moved = await self.edit(b, 110, 2)
        self.assertEqual(moved['timestamp'], stamp(2))
        await self.add(115, 4)
        self.assertEqual(self.total(), 125)

    async def test_moving_older_reading_after_latest_rebases_without_jump(self):
        first = await self.add(100, 1)
        await self.add(120, 2)
        await self.edit(first, 125, 3)
        self.assertEqual(self.total(), 120)
        await self.add(130, 4)
        self.assertEqual(self.total(), 125)

    async def test_late_replacement_after_latest_deletion_never_crosses_meters(self):
        await self.add(900, 1)
        latest = await self.add(1000, 3)
        await self.c.async_delete_reading('electricity', latest['id'])
        await self.add(2000, 2, kind='replacement', old_reading=950)
        self.assertEqual(self.total(), 1000)
        await self.add(2010, 4)
        self.assertEqual(self.total(), 1010)

    async def test_sensor_values_use_persisted_totals(self):
        modules = {name: ModuleType(name) for name in [
            'homeassistant.components', 'homeassistant.components.sensor',
            'homeassistant.config_entries', 'homeassistant.const', 'homeassistant.helpers.entity_platform']}
        sensor = modules['homeassistant.components.sensor']
        sensor.SensorEntity = object
        sensor.SensorDeviceClass = SimpleNamespace(ENERGY='energy', GAS='gas', MONETARY='monetary')
        sensor.SensorStateClass = SimpleNamespace(TOTAL_INCREASING='total_increasing')
        modules['homeassistant.config_entries'].ConfigEntry = object
        modules['homeassistant.const'].UnitOfEnergy = SimpleNamespace(KILO_WATT_HOUR='kWh')
        modules['homeassistant.const'].UnitOfVolume = SimpleNamespace(CUBIC_METERS='m³')
        modules['homeassistant.helpers.entity_platform'].AddEntitiesCallback = object
        sys.modules['homeassistant.core'].callback = lambda fn: fn
        self.entry.entry_id = 'test'
        with patch.dict(sys.modules, modules):
            platform = importlib.import_module('meter_snap_reading_tests.sensor')
            entity = platform.MeterSnapReadingSensor(self.c, 'electricity', 'strom_stand', 'Stand', 'kWh', 'energy', 'total_increasing')
            await self.add(1000, 1)
            await self.add(5, 2, kind='replacement', old_reading=1010)
            self.assertEqual(entity.native_value, 1010)
            self.assertEqual(entity.extra_state_attributes['physical_reading'], 5)
            self.assertEqual(entity._attr_unique_id, 'meter_snap_test_strom_stand')
            await self.c.async_add_reading('gas', 100, stamp(1))
            gas = platform.MeterSnapGasEnergySensor(self.c, 'gas_energie_stand', 'Energy')
            self.assertEqual(gas.native_value, self.c.get_statistics('gas')['energy'])

    async def test_reading_api_edit_warning_and_delete_boundary(self):
        modules = {name: ModuleType(name) for name in [
            'aiohttp', 'homeassistant.components', 'homeassistant.components.http',
            'meter_snap_reading_tests.ocr_engine']}
        modules['aiohttp'].web = SimpleNamespace(Request=object, Response=object)
        class View:
            def json(self, data, status_code=200):
                return dict(data=data, status=status_code)
        modules['homeassistant.components.http'].HomeAssistantView = View
        modules['meter_snap_reading_tests.ocr_engine'].MeterSnapOCREngine = object
        self.hass.data = {'meter_snap': {'test': {'coordinator': self.c, 'ocr_engine': object()}}}
        with patch.dict(sys.modules, modules):
            views = importlib.import_module('meter_snap_reading_tests.views')
            view = views.MeterSnapReadingView()
            class Request:
                app = {'hass': self.hass}
                query = {}
                async def json(inner):
                    return inner.body
            req = Request()
            req.body = dict(reading=100, timestamp=stamp(1))
            first = (await view.post(req))['data']['entry']
            req.body = dict(reading=110, timestamp=stamp(1), id=first['id'], notes='API correction')
            self.assertTrue((await view.post(req))['data']['success'])
            self.assertEqual(self.total(), 100)
            req.body = dict(reading=1000, timestamp=stamp(2))
            result = await view.post(req)
            self.assertEqual(result['status'], 200)
            self.assertTrue(result['data']['warning'])
            req.body['confirmation'] = result['data']['confirmation']
            self.assertTrue((await view.post(req))['data']['success'])
            repl = await self.add(0, 3, kind='replacement', old_reading=1010)
            req.query = dict(id=repl['id'], meter_type='electricity')
            result = await view.delete(req)
            self.assertEqual(result['status'], 400)
            self.assertIn('Edit a meter replacement', result['data']['error'])


if __name__ == '__main__':
    unittest.main()
