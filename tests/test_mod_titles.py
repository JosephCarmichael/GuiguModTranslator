import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mod_titles
import saved_translations as saved
from mod_titles import (apply_titles, display_name, load_titles, needs_title, save_titles,
                        saved_title, translate_titles)
from saved_translations import job_status, note, scan_statuses, saved_status, status_of, tick

PROFILE = {'provider': 'OpenRouter', 'model': 'deepseek/deepseek-v4.1-flash', 'api_key': 'test-key'}


class TitleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        patcher = patch('mod_titles.data_dir', return_value=self.data)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mods = [{'id': '111', 'name': '宝剑门', 'path': 'a'},
                     {'id': '222', 'name': 'English mod', 'path': 'b'},
                     {'id': '333', 'name': '灵力大改', 'path': 'c'}]

    def test_unknown_chinese_titles_are_translated_once_and_saved(self):
        calls, batches = [], []
        def fake(texts, profile, target, stop, glossary=None, gate=None):
            calls.append(list(texts))
            return ['Sword Sect', 'Spirit Overhaul']
        with patch('app_config.service_profile', return_value=PROFILE), \
             patch('translation.request_batch', side_effect=fake):
            first = translate_titles(self.mods, {}, on_save=batches.append)
        self.assertEqual(first['translated'], 2)
        self.assertEqual(calls, [['宝剑门', '灵力大改']])  # English names cost nothing.
        self.assertEqual(batches[-1]['111']['title'], 'Sword Sect')
        self.assertEqual(load_titles()['333']['title'], 'Spirit Overhaul')
        self.assertEqual(display_name(self.mods[0], load_titles()), 'Sword Sect (宝剑门)')
        with patch('translation.request_batch') as request:
            again = translate_titles(self.mods, load_titles())
            request.assert_not_called()
        self.assertEqual(again['translated'], 0)
        self.assertEqual(again['saved'], 2)

    def test_renamed_mod_is_translated_again_and_the_old_title_is_dropped(self):
        titles = {'111': {'source': '宝剑门', 'title': 'Sword Sect'}}
        self.assertEqual(saved_title(titles, {'id': '111', 'name': '宝剑门'}), 'Sword Sect')
        renamed = {'id': '111', 'name': '新宝剑门'}
        self.assertIsNone(saved_title(titles, renamed))
        self.assertTrue(needs_title(renamed, titles))
        self.assertFalse(needs_title({'id': '222', 'name': 'English mod'}, titles))

    def test_apply_titles_only_marks_mods_with_a_matching_saved_name(self):
        titles = {'111': {'source': '宝剑门', 'title': 'Sword Sect'}}
        mods = [dict(mod) for mod in self.mods]
        mods[0]['title'] = 'Stale title'
        apply_titles(mods, titles)
        self.assertEqual(mods[0]['title'], 'Sword Sect')
        self.assertNotIn('title', mods[2])
        mods[0]['name'] = '新宝剑门'
        apply_titles(mods, titles)
        self.assertNotIn('title', mods[0])

    def test_bad_provider_output_is_never_saved_as_a_title(self):
        mods = [{'id': str(i), 'name': name} for i, name in enumerate(['宝剑门', '灵力大改', '丹药铺', '法宝阁'])]
        values = ['宝剑门', '   ', '还在中文', 'Good Title']
        with patch('app_config.service_profile', return_value=PROFILE), \
             patch('translation.request_batch', return_value=values):
            result = translate_titles(mods, {})
        self.assertEqual(result['translated'], 1)
        self.assertEqual(result['failed'], 3)
        self.assertEqual(list(load_titles()), ['3'])
        self.assertEqual(load_titles()['3']['title'], 'Good Title')

    def test_titles_are_saved_after_each_batch_and_batches_stay_small(self):
        mods = [{'id': str(i), 'name': '模组' + str(i)} for i in range(5)]
        calls, saved_batches = [], []
        def fake(texts, profile, target, stop, glossary=None, gate=None):
            calls.append(len(texts))
            return ['Mod ' + str(len(calls)) + ' ' + str(i) for i in range(len(texts))]
        with patch.object(mod_titles, 'TITLE_BATCH', 2), \
             patch('app_config.service_profile', return_value=PROFILE), \
             patch('translation.request_batch', side_effect=fake):
            result = translate_titles(mods, {}, on_save=saved_batches.append)
        self.assertEqual(calls, [2, 2, 1])
        self.assertEqual(result['translated'], 5)
        self.assertEqual(len(saved_batches), 3)
        self.assertEqual(len(load_titles()), 5)

    def test_a_provider_problem_keeps_the_chinese_name_for_the_next_launch(self):
        with patch('app_config.service_profile', side_effect=ValueError('No translation access')):
            missing = translate_titles(self.mods, {})
        self.assertEqual(missing['error'], 'No translation access')
        self.assertEqual(missing['translated'], 0)
        self.assertEqual(load_titles(), {})
        with patch('app_config.service_profile', return_value=PROFILE), \
             patch('translation.request_batch', side_effect=RuntimeError('HTTP 429')):
            failed = translate_titles(self.mods, {})
        self.assertIn('429', failed['error'])
        self.assertEqual(failed['translated'], 0)
        self.assertEqual(load_titles(), {})

    def test_unsaved_titles_fall_back_to_the_original_name(self):
        self.assertEqual(display_name({'id': '1', 'name': '宝剑门'}, {}), '宝剑门')
        self.assertEqual(display_name({'id': '1', 'name': 'Sword', 'title': 'Sword'}, {}), 'Sword')

    def test_translated_author_label_is_not_an_added_placeholder(self):
        self.assertFalse(mod_titles.validate_title('[无邪]万古神话', '[Wuxie] Eternal Myth'))
        self.assertTrue(mod_titles.validate_title('[无邪]神话 {0}', '[Wuxie] Myth'))


def project(units, coverage=None, mod_id='mod'):
    return {'mod': {'id': mod_id, 'name': 'Mod'}, 'units': units,
            'coverage': coverage if coverage is not None else {'files': [{'status': 'scanned'}], 'counts': {}}}


def unit(source, translation='', status='untranslated', category='player_text'):
    return {'id': source, 'source': source, 'translation': translation, 'status': status,
            'category': category, 'occurrences': []}


class SavedTranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'projects'

    def write(self, mod_id, value):
        folder = self.root / mod_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / 'project.json').write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def test_a_fully_translated_project_is_ticked(self):
        status = status_of(project([unit('剑', 'Sword', 'machine'),
                                    unit('灵力', 'Spirit', 'edited'),
                                    unit('图标.png', '', 'technical', 'technical')]))
        self.assertTrue(status['complete'])
        # Technical identifiers are never part of the count or the tick.
        self.assertEqual((status['translated'], status['total']), (2, 2))
        self.assertEqual(tick(status), '\u2713 ')

    def test_untranslated_review_text_and_unreadable_files_block_the_tick(self):
        pending = status_of(project([unit('剑', 'Sword', 'machine'), unit('灵力')]))
        self.assertFalse(pending['complete'])
        self.assertEqual(tick(pending), '')
        self.assertIn('1 still need translation', note(pending))
        review = status_of(project([unit('剑', 'Sword', 'needs_review')]))
        self.assertFalse(review['complete'])
        unreadable = status_of(project([unit('剑', 'Sword', 'machine')],
                                       {'files': [{'status': 'unreadable'}], 'counts': {'unreadable': 1}}))
        self.assertFalse(unreadable['complete'])
        self.assertTrue(unreadable['coverage_gaps'])
        self.assertIn('could not be read', note(unreadable))

    def test_an_empty_project_is_never_complete(self):
        self.assertFalse(status_of(project([]))['complete'])
        self.assertFalse(status_of(project([unit('图标.png', 'icon', 'technical', 'technical')]))['complete'])

    def test_destiny_project_also_needs_its_runtime_inventory(self):
        units = [unit('剑', 'Sword', 'machine')]
        covered = status_of(project(units, {'files': [], 'runtime_inventory': True}, 'character-creation-destinies'),
                            'character-creation-destinies')
        self.assertTrue(covered['complete'])
        missing = status_of(project(units, {'files': [], 'runtime_inventory': False}, 'character-creation-destinies'),
                            'character-creation-destinies')
        self.assertFalse(missing['complete'])
        self.assertTrue(missing['coverage_gaps'])

    def test_mods_without_a_saved_project_are_not_ticked(self):
        self.assertIsNone(saved_status('missing', self.root))
        self.assertEqual(tick(None), '')
        self.assertEqual(note(None), '')

    def test_scan_reads_saved_projects_and_survives_damaged_files(self):
        self.write('good', project([unit('剑', 'Sword', 'machine')], mod_id='good'))
        (self.root / 'bad').mkdir(parents=True)
        (self.root / 'bad' / 'project.json').write_text('{broken', encoding='utf-8')
        mods = [{'id': 'good'}, {'id': 'bad'}, {'id': 'none'}]
        statuses = scan_statuses(mods, self.root)
        self.assertTrue(statuses['good']['complete'])
        self.assertEqual(tick(statuses['good']), '\u2713 ')
        self.assertFalse(statuses['bad']['complete'])
        self.assertIn('could not be read', note(statuses['bad']))
        self.assertIsNone(statuses['none'])

    def test_a_finished_job_updates_the_tick_without_rescanning(self):
        complete = job_status('mod', {'state': 'success', 'count': 42, 'pending': 0})
        self.assertTrue(complete['complete'])
        self.assertEqual(complete['total'], 42)
        partial = job_status('mod', {'state': 'partial', 'count': 40, 'pending': 2, 'coverage_gaps': False})
        self.assertFalse(partial['complete'])
        self.assertEqual((partial['translated'], partial['pending']), (40, 2))
        cancelled = job_status('mod', {'state': 'cancelled', 'count': 5, 'pending': 1})
        self.assertFalse(cancelled['complete'])


class SavedStatusWorkflowTests(unittest.TestCase):
    """The whole-sentence rule: a finished translation job ticks the mod."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.mod_folder = self.base / 'mod'
        self.mod_folder.mkdir()
        (self.mod_folder / 'items.json').write_text(
            json.dumps({'name': '宝剑', 'desc': '灵力恢复'}, ensure_ascii=False), encoding='utf-8')
        self.mod = {'id': 'tick-mod', 'name': '宝剑门', 'path': str(self.mod_folder), 'origin': 'test'}
        self.projects = self.base / 'projects'

    def test_a_finished_translation_is_ticked_on_the_next_scan(self):
        import mod_workflow
        translated = {'宝剑': 'Sword', '灵力恢复': 'Spirit recovery'}
        def fake_batch(texts, profile, target, stop, glossary=None, gate=None):
            return [translated[text] for text in texts]
        with patch('mod_workflow.preflight', return_value=None), \
             patch('mod_workflow.install', return_value={'count': 2, 'conflicts_resolved': 0}), \
             patch('translation.service_profile', return_value=PROFILE), \
             patch('translation.request_batch', side_effect=fake_batch):
            result = mod_workflow.run_job(self.mod, self.projects / self.mod['id'], lambda _: None,
                                          lambda: False, game=self.base, concurrency=4, batch_size=12)
        self.assertEqual(result['state'], 'success')
        statuses = scan_statuses([self.mod], self.projects)
        self.assertTrue(statuses['tick-mod']['complete'])
        self.assertEqual(tick(statuses['tick-mod']), '\u2713 ')
        self.assertEqual(note(statuses['tick-mod']), '2 saved translations complete')

    def test_a_partial_translation_has_no_tick(self):
        import mod_workflow
        def fake_batch(texts, profile, target, stop, glossary=None, gate=None):
            # The provider returns no usable wording for the second entry.
            return ['Sword' if text == '宝剑' else text for text in texts]
        with patch('mod_workflow.preflight', return_value=None), \
             patch('mod_workflow.install', return_value=None), \
             patch('translation.service_profile', return_value=PROFILE), \
             patch('translation.request_batch', side_effect=fake_batch):
            result = mod_workflow.run_job(self.mod, self.projects / self.mod['id'], lambda _: None,
                                          lambda: False, game=self.base, concurrency=4, batch_size=12)
        self.assertEqual(result['state'], 'partial')
        self.assertEqual(result['count'], 1)
        statuses = scan_statuses([self.mod], self.projects)
        self.assertFalse(statuses['tick-mod']['complete'])
        self.assertEqual(tick(statuses['tick-mod']), '')
        self.assertIn('still need translation', note(statuses['tick-mod']))


class TitleRefreshTests(unittest.TestCase):
    def test_mods_discovered_during_title_request_are_translated_after_it(self):
        import queue
        import threading
        import time
        from types import SimpleNamespace, MethodType
        from unittest.mock import Mock
        from desktop import App
        with tempfile.TemporaryDirectory() as directory:
            app = SimpleNamespace(mods={'1': {'id': '1', 'name': '宝剑门'}}, titles={}, title_running=False,
                                  title_refresh_pending=False, title_stop=threading.Event(), events=queue.Queue(),
                                  title_status=Mock(), render=Mock(), update_detail=Mock(), after=Mock())
            app.start_titles = MethodType(App.start_titles, app)
            app.poll = MethodType(App.poll, app)
            started, release = threading.Event(), threading.Event()
            calls = []
            def request(texts, *args, **kwargs):
                calls.append(texts)
                if len(calls) == 1:
                    started.set()
                    if not release.wait(5):
                        raise RuntimeError('Test did not release title request')
                return ['Sword Sect' for _ in texts]
            with patch('mod_titles.data_dir', return_value=Path(directory)), \
                 patch('shared_library.reuse_titles', return_value=0), \
                 patch('app_config.service_profile', return_value=PROFILE), \
                 patch('translation.request_batch', side_effect=request):
                app.start_titles()
                self.assertTrue(started.wait(5))
                app.mods['2'] = {'id': '2', 'name': '新宝剑门'}
                app.start_titles()
                release.set()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    App.poll(app)
                    if not app.title_running and len(app.titles) == 2:
                        break
                    time.sleep(.01)
                self.assertEqual(calls, [['宝剑门'], ['新宝剑门']])
                self.assertEqual(set(load_titles()), {'1', '2'})


if __name__ == '__main__':
    unittest.main()
