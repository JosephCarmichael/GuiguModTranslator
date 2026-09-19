"""The single-button mod extraction and translation workflow."""
from extractor import extract, validate_translation
from translation import translate
from installer import install, preflight

def run_job(mod, folder, progress, stop, game=None, concurrency=None, batch_size=None, max_pence=None, retranslate=False):
    from app_config import installed_game
    game = game or installed_game()
    if game is None:
        raise ValueError('Choose your game folder before translating.')
    preflight(game)
    progress('Reading the mod’s text…')
    from destinies import PROJECT_ID, scan_destinies
    project = (scan_destinies(game, folder, progress, stop) if mod['id'] == PROJECT_ID else
               extract(mod, folder, lambda _: progress('Reading the mod’s text…'), stop))
    if stop():
        return {'state': 'cancelled', 'count': 0, 'folder': str(folder)}
    if max_pence is not None:
        from bulk_translation import within_price
        from translation_cost import estimate_project
        estimate = estimate_project(project, batch_size)
        if not within_price(estimate, max_pence):
            return {'state': 'skipped', 'reason': 'Current estimate is unavailable or above the selected per-mod price.',
                    'estimate': estimate, 'folder': str(folder)}
    result = translate(project, folder, progress=progress, stop=stop, include_review=True,
                       concurrency=concurrency, batch_size=batch_size, retranslate=retranslate)
    eligible = [u for u in project['units'] if u['category'] != 'technical']
    from saved_translations import status_of
    saved = status_of(project, mod['id'])
    count, pending, gaps = saved['translated'], saved['pending'], saved['coverage_gaps']
    if result['cancelled'] or stop():
        state = 'cancelled'
    elif not eligible:
        state = 'empty'
    elif pending or gaps:
        state = 'partial'
    else:
        state = 'success'
    installed = None
    ready = any(u['translation'] and u['status'] != 'needs_review' and
                not validate_translation(u['source'], u['translation']) for u in eligible)
    if state not in ('cancelled', 'empty') and ready:
        progress('Installing translations into the game…')
        installed = install(project, game)
    return {'state': state, 'count': count, 'pending': pending, 'coverage_gaps': gaps,
            'installation': installed, 'folder': str(folder), 'saved_status': saved}
