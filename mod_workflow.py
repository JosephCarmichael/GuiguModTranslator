"""The single-button mod extraction and translation workflow."""
from extractor import extract
from translation import translate

def run_job(mod, folder, progress, stop):
    progress('Reading the mod’s text…')
    project = extract(mod, folder, lambda _: progress('Reading the mod’s text…'), stop)
    if stop():
        return {'state': 'cancelled', 'count': 0, 'folder': str(folder)}
    result = translate(project, folder, progress=progress, stop=stop, include_review=True)
    eligible = [u for u in project['units'] if u['category'] != 'technical']
    count = sum(bool(u['translation']) for u in eligible)
    pending = sum(not u['translation'] or u['status'] == 'needs_review' for u in eligible)
    gaps = any(f['status'] in ('unreadable', 'partial') for f in project['coverage']['files'])
    if result['cancelled']:
        state = 'cancelled'
    elif not eligible:
        state = 'empty'
    elif pending or gaps:
        state = 'partial'
    else:
        state = 'success'
    return {'state': state, 'count': count, 'pending': pending, 'coverage_gaps': gaps, 'folder': str(folder)}
