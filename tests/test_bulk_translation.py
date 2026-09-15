import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bulk_translation import plan_bulk, run_bulk, within_price, money, bulk_summary
from destinies import PROJECT_ID
from extractor import extract, save_project, read_json
from mod_workflow import run_job
from translation import TranslationError
import app_config


def estimate(pence, complete=True):
    return {'pence': str(pence), 'complete': complete}


class BulkTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.mods = [{'id': str(i), 'name': 'Mod '+str(i)} for i in range(4)]

    def test_threshold_is_per_mod_inclusive_and_queue_is_cheapest_first(self):
        estimates = {'0': estimate(199), '1': estimate(5), '2': estimate(200), '3': estimate('200.001')}
        plan = plan_bulk(self.mods, estimates, 200)
        self.assertEqual([m['id'] for m in plan['mods']], ['1', '0', '2'])
        self.assertEqual(plan['total_pence'], '404')
        self.assertEqual(plan['excluded'], 1)
        self.assertEqual(money(plan['total_pence']), '£4.04')
        self.assertEqual(money(50), '50p')
        self.assertEqual(money(5), '5p')
        self.assertEqual(money(200), '£2.00')
        self.assertEqual([m['id'] for m in plan_bulk(self.mods, estimates, 5)['mods']], ['1'])

    def test_incomplete_unknown_and_bad_estimates_do_not_authorize_spending(self):
        estimates = {'0': estimate(0, False), '1': {'error': True}, '2': estimate('NaN')}
        result = plan_bulk(self.mods, estimates, 200)
        self.assertEqual(result['mods'], [])
        self.assertEqual((result['pending'], result['excluded']), (1, 3))
        for value in ('Infinity', '-1', 'bad'):
            self.assertFalse(within_price(estimate(value), 200))

    def test_shared_cap_is_preserved_and_destiny_aggregate_is_not_a_mod(self):
        mods = self.mods + [{'id': PROJECT_ID, 'name': 'Destinies'}]
        prices = {'0': estimate('.5'), '1': estimate('.50001'), '2': estimate(5), '3': estimate(30),
                  PROJECT_ID: estimate('.1')}
        result = plan_bulk(mods, prices, 200, limited=True)
        self.assertEqual([m['id'] for m in result['mods']], ['0', '1', '2'])
        self.assertEqual(len(plan_bulk(mods, prices, 200, limited=False)['mods']), 4)

    def test_cancel_preserves_completed_results_and_never_starts_next_mod(self):
        stopped = False
        def job(*args, **kwargs):
            nonlocal stopped
            stopped = True
            return {'state': 'success', 'folder': str(args[1])}
        with patch('mod_workflow.run_job', side_effect=job) as call:
            result = run_bulk(self.mods, self.root, 200, lambda *_: None, lambda: stopped, game=self.root)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result['state'], 'cancelled')
        self.assertEqual(result['not_started'], 3)
        self.assertEqual(read_json(self.root/'translate-all-last.json'), result)
        self.assertIn('1 complete', bulk_summary(result))

    def test_already_cancelled_starts_no_jobs(self):
        with patch('mod_workflow.run_job') as call:
            result = run_bulk(self.mods, self.root, 5, lambda *_: None, lambda: True, game=self.root)
        call.assert_not_called()
        self.assertEqual(result['not_started'], 4)

    def test_provider_failure_stops_queue_and_keeps_earlier_success(self):
        with patch('mod_workflow.run_job', side_effect=[{'state': 'success'}, TranslationError('Insufficient funds')]) as call:
            result = run_bulk(self.mods, self.root, 5, lambda *_: None, lambda: False, game=self.root)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(result['not_started'], 2)
        self.assertIn('Insufficient funds', bulk_summary(result))
        self.assertEqual(result['results'][0]['state'], 'success')

    def test_skips_and_partial_results_continue_without_claiming_full_success(self):
        with patch('mod_workflow.run_job', side_effect=[{'state': s} for s in ('skipped', 'partial', 'empty', 'success')]) as call:
            result = run_bulk(self.mods, self.root, 50, lambda *_: None, lambda: False,
                              game=self.root, concurrency=8, batch_size=24)
        self.assertEqual(call.call_count, 4)
        self.assertEqual(call.call_args.kwargs['max_pence'], 50)
        self.assertEqual(call.call_args.kwargs['batch_size'], 24)
        self.assertIn('1 partial', bulk_summary(result))
        self.assertIn('1 skipped', bulk_summary(result))

    def test_fresh_extracted_price_is_checked_before_translation_requests(self):
        mod = self.root/'source'; mod.mkdir()
        (mod/'text.json').write_text(json.dumps({'text': '宝剑'*100000}), encoding='utf-8')
        info = {'id': 'fresh', 'name': 'Fresh', 'path': str(mod)}
        with patch('mod_workflow.preflight'), patch('mod_workflow.translate') as translate:
            result = run_job(info, self.root/'saved', lambda *_: None, lambda: False,
                             game=self.root, max_pence=5)
        self.assertEqual(result['state'], 'skipped')
        translate.assert_not_called()

    def test_bulk_resumes_saved_projects_and_repeat_run_makes_no_requests(self):
        mods = []
        for i in range(2):
            source = self.root/('source'+str(i)); source.mkdir()
            (source/'text.json').write_text('{"name":"宝剑","description":"灵力"}', encoding='utf-8')
            info = {'id': str(i), 'name': str(i), 'path': str(source)}
            mods.append(info)
            folder = self.root/'projects'/str(i)
            project = extract(info, folder)
            for unit in project['units']:
                if unit['source'] == '宝剑':
                    unit.update(translation='My saved wording', status='edited')
            save_project(project, folder)
        with patch('mod_workflow.preflight'), patch('mod_workflow.install', return_value={'count': 2}), \
             patch('translation.service_profile', return_value={'provider': 'OpenRouter', 'model': 'fixture', 'personal_key': True}), \
             patch('translation.request_batch', return_value=['Spirit']) as request:
            result = run_bulk(mods, self.root/'projects', 200, lambda *_: None, lambda: False, game=self.root)
            self.assertEqual(request.call_count, 2)
            self.assertTrue(all(call.args[0] == ['灵力'] for call in request.call_args_list))
            request.reset_mock()
            again = run_bulk(mods, self.root/'projects', 200, lambda *_: None, lambda: False, game=self.root)
            request.assert_not_called()
        self.assertTrue(all(item['state'] == 'success' for item in result['results'] + again['results']))
        for mod in mods:
            saved = read_json(self.root/'projects'/mod['id']/'project.json')
            self.assertEqual(next(u['translation'] for u in saved['units'] if u['source'] == '宝剑'), 'My saved wording')

    def test_frozen_update_in_a_new_folder_reuses_existing_user_data(self):
        with patch.dict(os.environ, {'LOCALAPPDATA': str(self.root)}), \
             patch.object(app_config.sys, 'frozen', True, create=True):
            with patch.dict(os.environ):
                os.environ.pop('GUIGU_TRANSLATOR_DATA', None)
                with patch('app_config.APP_DIR', self.root/'old-exe'):
                    previous = app_config.data_dir()
                    (previous/'saved-sentinel.json').write_text('existing translations')
                    app_config.save_preferences(bulk_price_pence=200)
                with patch('app_config.APP_DIR', self.root/'new-exe'):
                    self.assertEqual(app_config.data_dir(), previous)
                    self.assertEqual((app_config.data_dir()/'saved-sentinel.json').read_text(), 'existing translations')
                    self.assertEqual(app_config.bulk_price_pence(), 200)


if __name__ == '__main__': unittest.main()
