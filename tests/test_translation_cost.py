import copy
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import app_config
from destinies import PROJECT_ID
from translation import translate
from translation_cost import (estimate_project, format_pence, full_translation_allowed,
                              enforce_translation_policy, estimate_mod, is_destiny_project)


def project(source='宝剑'):
    return {'mod': {'id': 'mod', 'name': 'Mod'}, 'coverage': {'files': [], 'counts': {}},
            'units': [{'id': 'one', 'source': source, 'translation': '',
                       'category': 'player_text', 'status': 'untranslated', 'occurrences': []}]}


class CostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        # Policy tests must not inherit a real personal key from this machine.
        profile = patch('app_config.service_profile', return_value={'personal_key': False})
        profile.start()
        self.addCleanup(profile.stop)
        translation_profile = patch('translation.service_profile', return_value={'personal_key': False})
        translation_profile.start()
        self.addCleanup(translation_profile.stop)

    def test_five_pence_boundary_is_not_half_penny_or_rounded(self):
        self.assertTrue(full_translation_allowed({'pence': '5', 'complete': True}))
        self.assertTrue(full_translation_allowed({'pence': '3', 'complete': True}))
        above = {'pence': '5.00000001', 'complete': True}
        self.assertFalse(full_translation_allowed(above))
        self.assertEqual(format_pence(above), '~5.001p')
        self.assertFalse(full_translation_allowed({'pence': '0', 'complete': False}))
        self.assertFalse(full_translation_allowed(None))
        self.assertFalse(full_translation_allowed({'error': True}))

    def test_full_cost_does_not_shrink_with_saved_progress_or_duplicate_sources(self):
        p = project('宝剑' * 50000)
        before = estimate_project(p)
        p['units'][0]['translation'] = 'Sword'
        p['units'].append(copy.deepcopy(p['units'][0]))
        p['units'].append({**p['units'][0], 'source': '路径' * 10000, 'category': 'technical'})
        self.assertEqual(estimate_project(p), before)
        self.assertGreater(Decimal(before['pence']), Decimal('0.5'))

    def test_smaller_batches_include_more_request_overhead(self):
        p = project()
        p['units'] = [{**p['units'][0], 'source': '宝剑' + str(i)} for i in range(96)]
        small, large = estimate_project(p, 12), estimate_project(p, 96)
        self.assertEqual((small['batches'], large['batches']), (8, 1))
        self.assertGreater(Decimal(small['pence']), Decimal(large['pence']))
        self.assertEqual(large['output_tokens'], small['output_tokens'])

    def test_friend_guard_blocks_before_any_paid_request_even_after_resume(self):
        p = project('宝剑' * 50000)
        with patch('translation_cost.is_friends_build', return_value=True), patch('translation.request_batch') as request:
            with self.assertRaisesRegex(PermissionError, '5p'):
                translate(p, self.folder)
            p['units'][0]['translation'] = 'Saved'
            self.assertEqual(translate(p, self.folder)['total'], 0)
            with self.assertRaises(PermissionError):
                translate(p, self.folder, retranslate=True)
            request.assert_not_called()
        self.assertFalse((self.folder/'project.json').exists())

    def test_unreadable_source_cannot_be_treated_as_a_free_full_mod(self):
        p = project()
        p['coverage']['files'] = [{'status': 'unreadable'}]
        with patch('translation_cost.is_friends_build', return_value=True):
            with self.assertRaisesRegex(PermissionError, 'fully read'):
                enforce_translation_policy(p)

    def test_personal_has_no_limit_and_friend_destiny_is_exempt(self):
        p = project('宝剑' * 50000)
        with patch('translation_cost.is_friends_build', return_value=False):
            enforce_translation_policy(p)
        p['mod']['id'] = PROJECT_ID
        p['destiny_fields'] = [{'source': p['units'][0]['source'], 'field': 'tips'}]
        self.assertTrue(is_destiny_project(p))
        profile = {'provider': 'OpenRouter', 'model': 'deepseek/deepseek-v4.1-flash'}
        with patch('translation_cost.is_friends_build', return_value=True), \
             patch('translation.service_profile', return_value=profile), \
             patch('translation.request_batch', return_value=['Sword']) as request:
            self.assertEqual(translate(p, self.folder)['translated'], 1)
            request.assert_called_once()

    def test_renaming_a_full_mod_to_destiny_does_not_make_it_exempt(self):
        p = project('宝剑' * 50000)
        p['mod']['id'] = PROJECT_ID
        p['destiny_fields'] = [{'source': 'Other source'}]
        with patch('translation_cost.is_friends_build', return_value=True):
            with self.assertRaises(PermissionError):
                enforce_translation_policy(p)

    def test_estimate_scan_preserves_source_and_saved_project(self):
        mod = self.folder/'mod'
        mod.mkdir()
        source = mod/'text.json'
        source.write_text('{"name":"宝剑"}', encoding='utf-8')
        saved = self.folder/'project.json'
        saved.write_bytes(b'saved translation checkpoint')
        before = source.read_bytes(), saved.read_bytes()
        result = estimate_mod({'id': 'mod', 'name': 'Mod', 'path': str(mod)}, self.folder)
        self.assertEqual(result['entries'], 1)
        self.assertEqual((source.read_bytes(), saved.read_bytes()), before)

    def test_frozen_edition_is_embedded_not_a_user_preference(self):
        with patch.object(app_config.sys, 'frozen', True, create=True), patch('app_config.RESOURCE_DIR', self.folder):
            self.assertTrue(app_config.is_friends_build())
            policy = self.folder/'build_policy.json'
            policy.write_text(json.dumps({'edition': 'personal'}))
            self.assertFalse(app_config.is_friends_build())
            policy.write_text(json.dumps({'edition': 'friends'}))
            with patch('app_config.preferences', return_value={'edition': 'personal'}):
                self.assertTrue(app_config.is_friends_build())
            policy.write_text('{broken')
            self.assertTrue(app_config.is_friends_build())


if __name__ == '__main__':
    unittest.main()
