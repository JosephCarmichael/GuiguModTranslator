"""Dependency and round-trip check runnable from a copied executable."""
import json
import sys
import tempfile
from pathlib import Path

def check(report_path, live=False):
    report = {'frozen':bool(getattr(sys, 'frozen', False)), 'checks':[]}
    try:
        import tkinter as tk
        import yaml
        import openpyxl
        import dnfile
        import UnityPy
        import texture2ddecoder
        from UnityPy.helpers.Tpk import get_typetree_node
        from UnityPy.helpers.UnityVersion import UnityVersion
        from extractor import extract, read_json, MAGIC, MOD_KEY
        from translation import translate
        from app_config import service_profile
        from app_config import RESOURCE_DIR, is_friends_build, APP_VERSION
        report['app_version'] = APP_VERSION
        report['edition'] = 'friends' if is_friends_build() else 'personal'
        import hashlib
        from installer import LOADER
        runtime = RESOURCE_DIR / 'runtime'
        manifest = json.loads((runtime / 'manifest.json').read_text(encoding='utf-8'))
        assert hashlib.sha256((runtime / LOADER).read_bytes()).hexdigest() == manifest['sha256']
        dll = dnfile.dnPE(str(runtime / LOADER))
        assert str(dll.net.mdtables.Assembly.rows[0].Name) == 'GuiguModTranslation'
        dll.close()
        report['checks'].append('Bundled in-game loader and integrity manifest')
        from game_setup import verify_assets, install_files
        assets = verify_assets()
        report['setup_version'] = assets['melonloader_version']
        report['checks'].append('Bundled MelonLoader 0.5.4 and all first-launch tools pass integrity checks')
        import game_setup
        import windows_prerequisites
        assert windows_prerequisites.missing_runtimes() == []
        root = tk.Tk(); root.withdraw(); root.update(); root.destroy()
        report['checks'].append('Bundled Python and Tk GUI')
        node = get_typetree_node(49, UnityVersion.from_str('2020.3.9f1'))
        assert node
        report['checks'].append('Unity reader, native codecs and embedded type data')
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory); mod = temp/'mod'; mod.mkdir()
            data = json.dumps({'items':{'LocalText':[{'id':1,'key':'item1','ch':'<r>恢复灵力</r> {0}'}]}},ensure_ascii=False).encode()
            (mod/'ModExportData.cache').write_bytes(MAGIC+bytes((v+MOD_KEY[i%len(MOD_KEY)])&255 for i,v in enumerate(data)))
            (mod/'text.yml').write_text('text: 宝物说明',encoding='utf-8')
            book=openpyxl.Workbook();book.active['D5']='宝剑';book.save(mod/'text.xlsx');book.close()
            p=extract({'id':'portable-test','name':'Portable test','path':str(mod)},temp/'output')
            assert {u['source'] for u in p['units']}=={'<r>恢复灵力</r> {0}','宝物说明','宝剑'}
            assert not p['coverage']['counts'].get('unreadable')
            report['checks'].append('Encoded mod, YAML, Excel, JSON and CSV export')
            profile=service_profile()
            report['provider'],report['model']=profile['provider'],profile['model']
            report['checks'].append('Bundled translation access found (key not logged)')
            # Exercise the bundled thread pool, response ownership and saving
            # without making extra paid requests during portable validation.
            import io
            import threading
            from unittest.mock import patch
            import diagnostics
            from app_config import APP_DIR
            diagnostic_game = temp/'diagnostic-game'; diagnostic_game.mkdir()
            with patch('diagnostics.windows_events', return_value='offline crash fixture'), patch('diagnostics.steam_root', return_value=None):
                log_report = diagnostics.build_report(diagnostic_game, {'message':'50% portable check'}, temp/'no-app-data', temp/'no-player-data')
            clipboard_window = tk.Tk(); clipboard_window.withdraw(); clipboard_window.update()
            try:
                with patch('diagnostics.build_report', return_value=log_report):
                    logs = diagnostics.collect_logs(diagnostic_game, window_handle=clipboard_window.winfo_id())
                assert Path(logs['path']).parent == APP_DIR
                assert Path(logs['path']).read_text(encoding='utf-8-sig') == log_report
                if logs['copied']:
                    assert clipboard_window.clipboard_get() == log_report
                else:
                    assert logs['errors'] == ['Copying the report: Another app is using the clipboard.']
                    report.setdefault('unavailable_checks', []).append('Clipboard locked by another application; saved log contents verified')
            finally:
                clipboard_window.destroy()
            if logs['copied']:
                clipboard_reader = tk.Tk(); clipboard_reader.withdraw()
                try:
                    assert clipboard_reader.clipboard_get().replace('\r\n', '\n') == log_report
                finally:
                    clipboard_reader.destroy()
                report['checks'].append('Collect logs writes plain text beside the copied EXE and copies Unicode report to Windows clipboard')
                report['checks'].append('Copied logs remain available after the app window closes')
            else:
                report['checks'].append('Collect logs writes correct plain text beside the copied EXE when clipboard is unavailable')
            # Exercise actual embedded ZIP extraction and deployment in an
            # empty fixture. Only native game/process checks are substituted.
            clean = temp/'clean-game'; clean.mkdir()
            with patch('game_setup.validate_game', return_value=clean.resolve()), \
                 patch('game_setup.game_processes', return_value=set()):
                pending, generation = game_setup.setup_plan(clean)
                assert generation and 'version.dll' in pending
                game_setup.install_files(clean.resolve(), pending, lambda *_: None, lambda: False)
            assert (clean/'Mods'/LOADER).read_bytes() == (runtime/LOADER).read_bytes()
            assert (clean/'MelonLoader/Dependencies/Il2CppAssemblyGenerator/Cpp2IL/Cpp2IL.exe').is_file()
            assert not (clean/'MelonLoader/Managed/Assembly-CSharp.dll').exists()
            report['checks'].append('Clean deployment from embedded setup assets; no proprietary game assemblies bundled')
            import launch_repair
            repair_game = temp/'repair-library/steamapps/common/鬼谷八荒'
            repair_game.mkdir(parents=True)
            (repair_game/'guigubahuang.exe').write_bytes(b'fixture, not a game binary')
            steam_manifest = repair_game.parent.parent/'appmanifest_1468810.acf'
            steam_manifest.write_text('"AppState" { "appid" "1468810" "installdir" "鬼谷八荒" }', encoding='utf-8')
            repair_data = temp/'repair-appdata'; repair_data.mkdir()
            with patch('launch_repair.data_dir', return_value=repair_data), \
                 patch('app_config.data_dir', return_value=repair_data), \
                 patch('launch_repair.short_game_path', return_value=None), \
                 patch('launch_repair.steam_running', return_value=False), \
                 patch('game_setup.game_processes', return_value=set()), \
                 patch('launch_repair.unsupported_path', side_effect=lambda p: not str(p).isascii()):
                repaired = launch_repair.repair_game_path(repair_game, lambda *_: None, lambda: False)
            assert repaired.name == 'TaleOfImmortal' and repair_game.resolve() == repaired.resolve()
            assert (repair_game/'guigubahuang.exe').read_bytes() == b'fixture, not a game binary'
            assert (repaired/'UserData/GuiguModTranslator/setup-pending.json').is_file()
            assert '"installdir" "TaleOfImmortal"' in steam_manifest.read_text(encoding='utf-8')
            report['checks'].append('Launch repair: real Windows rename, junction, Steam manifest backup/update and required live-check marker')
            barrier = threading.Barrier(16, timeout=10)
            def fake_http(request, timeout):
                barrier.wait()
                texts = json.loads(json.loads(request.data)['messages'][1]['content'])
                values = [s.replace('灵力', 'Spirit ') for s in texts]
                return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps(values)}}]}).encode())
            parallel = {'mod': {'id': 'parallel'}, 'coverage': {'files': []}, 'units': [
                {'id': str(i), 'source': f'灵力{i} {{0}}', 'translation': '', 'status': 'untranslated',
                 'category': 'player_text', 'occurrences': []} for i in range(192)]}
            with patch('translation_cost.is_friends_build', return_value=False), patch('translation.urllib.request.urlopen', fake_http):
                result = translate(parallel, temp/'parallel-output', batch_size=12, concurrency=16)
            assert result['translated'] == 192 and result['failed'] == 0
            assert all(u['translation'] == u['source'].replace('灵力', 'Spirit ') for u in read_json(temp/'parallel-output/project.json')['units'])
            report['checks'].append('16 simultaneous requests with correct saved responses (offline transport)')
            attempts = []
            def busy_then_ready(request, timeout):
                attempts.append(1)
                if len(attempts) <= 4:
                    import urllib.error
                    raise urllib.error.HTTPError(request.full_url, 429, 'Busy', {'Retry-After': '0'}, None)
                texts = json.loads(json.loads(request.data)['messages'][1]['content'])
                return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps([s.replace('灵力', 'Spirit ') for s in texts])}}]}).encode())
            recovery = {'mod': {'id': 'recovery'}, 'coverage': {'files': []},
                        'units': [{**parallel['units'][0], 'translation': ''}]}
            with patch('translation.urllib.request.urlopen', busy_then_ready):
                result = translate(recovery, temp/'recovery-output', concurrency=16)
            assert result['translated'] == 1 and len(attempts) == 5
            assert (temp/'recovery-output/request-errors.jsonl').is_file()
            report['checks'].append('Recovery after four HTTP 429 responses with saved diagnostics (offline transport)')
            sizes = []
            def batch_http(request, timeout):
                texts = json.loads(json.loads(request.data)['messages'][1]['content'])
                sizes.append(len(texts))
                return io.BytesIO(json.dumps({'choices': [{'message': {'content': json.dumps([s.replace('灵力', 'Spirit ') for s in texts])}}]}).encode())
            larger = {'mod': {'id': 'larger-batches'}, 'coverage': {'files': []},
                      'units': [{**unit, 'translation': ''} for unit in parallel['units'][:96]]}
            with patch('translation_cost.is_friends_build', return_value=False), patch('translation.urllib.request.urlopen', batch_http):
                result = translate(larger, temp/'larger-output', concurrency=4, batch_size=48)
            assert result['translated'] == 96 and sizes == [48, 48]
            report['checks'].append('96 entries translated in two 48-entry requests (offline transport)')
            from translation import protect, restore
            from extractor import validate_translation
            source = '<灵力> 30%闪避 <color=red>{0}</color>'
            masked, tokens = protect(source)
            assert '灵力' in masked
            translated_text = restore(masked.replace('灵力', 'Spirit').replace('闪避', ' dodge'), tokens)
            assert not validate_translation(source, translated_text)
            report['checks'].append('Narration is translated while rich text, percentages and placeholders are preserved')
            from installer import install, uninstall, paths, read_store
            import copy
            first = {'mod': {'id': 'first', 'name': 'First', 'path': str(mod)},
                     'units': [{'id': 'sword', 'source': '宝剑', 'translation': 'Sword',
                                'status': 'edited', 'category': 'player_text'}]}
            second = copy.deepcopy(first)
            second['mod']['id'] = 'second'
            second['units'][0]['translation'] = 'Treasure sword'
            with patch('installer.preflight', return_value=(runtime / LOADER).read_bytes()):
                install(first, temp/'game')
                result = install(second, temp/'game')
            assert result['conflicts_resolved'] == 1
            _, store = paths(temp/'game')
            mods = read_store(store)['mods']
            assert mods['second']['install_order'] > mods['first']['install_order']
            assert mods['first']['entries']['宝剑'] == 'Sword'
            uninstall('second', temp/'game')
            assert read_store(store)['mods']['first']['entries']['宝剑'] == 'Sword'
            report['checks'].append('Conflicting installation succeeds, preserves other dictionaries and uninstalls independently')
            from translation_cost import enforce_translation_policy, estimate_project, full_translation_allowed
            expensive = {'mod': {'id': 'expensive'}, 'coverage': {'files': []},
                         'units': [{**parallel['units'][0], 'source': '宝剑' * 50000, 'translation': ''}]}
            assert not full_translation_allowed(estimate_project(expensive))
            if is_friends_build():
                with patch('translation.request_batch') as paid:
                    try:
                        translate(expensive, temp/'blocked')
                    except PermissionError as error:
                        assert '5p' in str(error)
                    else:
                        raise AssertionError('Friends full-mod limit was bypassed')
                    paid.assert_not_called()
                report['checks'].append('Friends limit blocks expensive mods before requests')
                import api_access
                personal_data = temp/'personal-key-data'; personal_data.mkdir()
                test_key = 'sk-or-v1-' + 'offline-personal-fixture-' * 3
                with patch('api_access.data_dir', return_value=personal_data), \
                     patch('app_config.data_dir', return_value=personal_data):
                    api_access.save_openrouter_key(test_key)
                    assert test_key not in (personal_data/api_access.ACCESS_FILE).read_text()
                    assert service_profile()['personal_key'] and service_profile()['api_key'] == test_key
                    import copy
                    with patch('translation.request_batch', return_value=['Sword']) as personal_request:
                        personal_result = translate(copy.deepcopy(expensive), temp/'personal-unlimited')
                    assert personal_result['translated'] == 1
                    assert personal_request.call_args.args[1]['api_key'] == test_key
                    api_access.use_shared_key()
                    assert not service_profile()['personal_key']
                    with patch('translation.request_batch') as shared_request:
                        try:
                            translate(copy.deepcopy(expensive), temp/'shared-limited-again')
                        except PermissionError:
                            pass
                        else:
                            raise AssertionError('Removing the personal key did not restore the shared cap')
                        shared_request.assert_not_called()
                report['checks'].append('Personal OpenRouter key: real Windows encryption, unlimited full-mod translation with chosen key, shared cap restored on removal (offline requests)')
            else:
                enforce_translation_policy(expensive)
                report['checks'].append('Personal edition has no full-mod cost restriction')
            from destinies import PROJECT_ID
            expensive['mod']['id'] = PROJECT_ID
            expensive['destiny_fields'] = [{'source': expensive['units'][0]['source'], 'field': 'tips'}]
            with patch('translation.request_batch', return_value=['Treasure sword']):
                result = translate(expensive, temp/'destiny-exempt')
            assert result['translated'] == 1
            report['checks'].append('Destiny-menu translation remains available above the limit (offline transport)')
            from bulk_translation import plan_bulk, run_bulk
            from extractor import save_project
            bulk_source = temp/'bulk-source'; bulk_source.mkdir()
            (bulk_source/'text.json').write_text('{"name":"宝剑","description":"灵力"}', encoding='utf-8')
            bulk_mod = {'id': 'bulk-resume', 'name': 'Bulk resume', 'path': str(bulk_source)}
            saved_folder = temp/'bulk-projects'/'bulk-resume'
            saved = extract(bulk_mod, saved_folder)
            for unit in saved['units']:
                if unit['source'] == '宝剑':
                    unit.update(translation='Preserved custom wording', status='edited')
            save_project(saved, saved_folder)
            queue = plan_bulk([bulk_mod], {'bulk-resume': estimate_project(saved)}, 200)
            assert len(queue['mods']) == 1
            with patch('mod_workflow.preflight'), patch('mod_workflow.install', return_value={'count': 2}), \
                 patch('translation.request_batch', return_value=['Spirit']) as bulk_request:
                bulk_result = run_bulk(queue['mods'], temp/'bulk-projects', 200, lambda *_: None,
                                       lambda: False, game=temp/'fixture-game')
                assert bulk_result['results'][0]['state'] == 'success'
                bulk_request.assert_called_once()
                assert bulk_request.call_args.args[0] == ['灵力']
                bulk_request.reset_mock()
                again = run_bulk(queue['mods'], temp/'bulk-projects', 200, lambda *_: None,
                                 lambda: False, game=temp/'fixture-game')
                assert again['results'][0]['state'] == 'success'
                bulk_request.assert_not_called()
            saved = read_json(saved_folder/'project.json')
            assert next(u['translation'] for u in saved['units'] if u['source'] == '宝剑') == 'Preserved custom wording'
            report['checks'].append('Translate all: price-filtered queue, saved translations reused, repeat run makes zero requests (offline transport)')
            from mod_titles import display_name, load_titles, translate_titles
            from saved_translations import scan_statuses, tick
            title_data = temp/'title-data'; title_data.mkdir()
            with patch('mod_titles.data_dir', return_value=title_data), \
                 patch('translation.request_batch', return_value=['Sword Sect']) as title_request:
                unknown = {'id': 'title-mod', 'name': '宝剑门'}
                titles = {}
                first = translate_titles([unknown, {'id': 'english-mod', 'name': 'English mod'}], titles)
                assert first['translated'] == 1 and title_request.call_count == 1
                assert title_request.call_args.args[0] == ['宝剑门']
                assert load_titles()['title-mod']['title'] == 'Sword Sect'
                assert display_name(unknown, load_titles()) == 'Sword Sect (宝剑门)'
                again = translate_titles([unknown], load_titles())
                assert again['translated'] == 0 and title_request.call_count == 1
            report['checks'].append('Mod titles: one request for unknown Chinese names, saved once and reused with the original name (offline transport)')
            tick_root = temp/'tick-projects'
            tick_folder = tick_root/'tick-mod'; tick_folder.mkdir(parents=True)
            (tick_folder/'project.json').write_text(json.dumps({'mod': {'id': 'tick-mod'}, 'coverage': {'files': [{'status': 'scanned'}]},
                'units': [{'id': '1', 'source': '宝剑', 'translation': 'Sword', 'status': 'machine', 'category': 'player_text', 'occurrences': []}]},
                ensure_ascii=False), encoding='utf-8')
            statuses = scan_statuses([{'id': 'tick-mod'}, {'id': 'untranslated-mod'}], tick_root)
            assert statuses['tick-mod']['complete'] and tick(statuses['tick-mod']) == '✓ '
            assert statuses['untranslated-mod'] is None and tick(statuses['untranslated-mod']) == ''
            report['checks'].append('A saved, fully translated mod is ticked; a mod without a saved project is not ticked')
            from translation_balance import BalanceTracker, balance_text
            from translation import request_batch
            balance = BalanceTracker(temp/'balance-cache')
            balance_profile = {'provider': 'OpenRouter', 'api_key': 'sk-or-v1-offline-balance-fixture',
                               'endpoint': 'https://example.invalid/completions', 'model': 'fixture'}
            with patch('translation_balance.fetch_key_info', return_value={'limit': 1, 'limit_remaining': '.57', 'usage': '.43'}):
                assert balance.refresh(balance_profile)
            billed = {'id': 'fixture-billed-response', 'usage': {'cost': '.01'},
                      'choices': [{'message': {'content': '["Spirit"]'}}]}
            with patch('translation_balance.tracker', return_value=balance), \
                 patch('translation.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(billed).encode())):
                assert request_batch(['灵力'], balance_profile, 'en', lambda: False) == ['Spirit']
            assert balance.snapshot(balance_profile)['remaining_usd'] == '0.56'
            with patch('translation_balance.fetch_key_info', return_value={'limit': 1, 'limit_remaining': '.56', 'usage': '.44'}):
                assert balance.refresh(balance_profile)
            assert balance.snapshot(balance_profile)['remaining_usd'] == '0.56'
            assert '$0.5600' in balance_text(balance.snapshot(balance_profile))[1]
            assert balance_profile['api_key'] not in balance.path.read_text()
            report['checks'].append('Balance: confirmed response cost deducted, GBP conversion, cache without keys and live reconciliation without double subtraction (offline endpoint)')
            # Exercise the new modules from the copied executable as well as source.
            from thumbnails import load_thumbnail
            from PIL import Image
            preview = io.BytesIO()
            Image.new('RGB', (180, 90), '#385ee8').save(preview, format='PNG')
            raw = preview.getvalue()
            (mod/'ModProjectPreview.png').write_bytes(MAGIC + bytes((v + MOD_KEY[i % len(MOD_KEY)]) & 255 for i, v in enumerate(raw)))
            assert load_thumbnail({'path': str(mod)}).size == (56, 56)
            report['checks'].append('Game-encoded mod preview decodes and resizes in the portable app')
            import shared_library
            shared_project = {'mod': {'id': 'portable-shared'}, 'coverage': {'files': []}, 'units': [
                {'id': 'shared', 'source': '宝剑', 'translation': 'Sword', 'status': 'edited', 'category': 'player_text'}]}
            shared_source = temp/'shared-source/portable-shared'; shared_source.mkdir(parents=True)
            (shared_source/'project.json').write_text(json.dumps(shared_project), encoding='utf-8')
            with patch('shared_library.RESOURCE_DIR', temp/'shared-assets'), patch('shared_library.data_dir', return_value=temp/'shared-data'):
                shared_library.export_library(shared_source.parent, temp/'shared-assets/shared-library')
                shared_project['units'][0]['translation'] = ''
                assert shared_library.apply_shared(shared_project) == 1
                assert shared_project['units'][0]['translation'] == 'Sword'
            report['checks'].append('Shared translation export and exact-match reuse without credentials or API requests')
            import app_updates
            import zipfile
            zipped = io.BytesIO()
            with zipfile.ZipFile(zipped, 'w') as archive:
                archive.writestr('GuiguModTranslator/GuiguModTranslator.exe', b'offline update fixture')
            payload = zipped.getvalue()
            metadata = {'version': '9.0.0', 'edition': report['edition'], 'asset': {'id': 1},
                        'sha256': hashlib.sha256(payload).hexdigest(), 'exe_sha256': hashlib.sha256(b'offline update fixture').hexdigest()}
            with patch('app_updates.open_request', return_value=io.BytesIO(payload)), patch('app_updates.data_dir', return_value=temp/'update-data'):
                staged = app_updates.prepare_update(metadata)
                assert Path(staged['executable']).read_bytes() == b'offline update fixture'
            report['checks'].append('App update archive and executable checksums verified before staging (offline transport)')
            if live:
                p['units']=[u for u in p['units'] if u['source'].startswith('<r>')]
                result=translate(p,temp/'output')
                assert result['translated']==1 and result['failed']==0
                report['translation']=p['units'][0]['translation']
                report['checks'].append('Live DeepSeek translation with formatting preserved')
        report['result']='passed'
    except Exception as exc:
        report['result']='failed'
        report['error']=str(exc)
    Path(report_path).parent.mkdir(parents=True,exist_ok=True)
    Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if report['result']!='passed':
        raise SystemExit(1)
