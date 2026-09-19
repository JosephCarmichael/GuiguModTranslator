"""Report which saved mod projects already hold a complete translation."""
from __future__ import annotations

from pathlib import Path

from extractor import APP, CJK, read_json, validate_translation


def valid_unit(unit):
    value = unit.get('translation')
    return (isinstance(value, str) and bool(value.strip()) and not CJK.search(value)
            and unit.get('status') != 'needs_review' and not unit.get('retranslation_pending')
            and not validate_translation(unit.get('source', ''), value))


def projects_root(root=None):
    return Path(root) if root else APP / 'projects'


def project_path(mod_id, root=None):
    return projects_root(root) / str(mod_id) / 'project.json'


def status_of(project, mod_id=''):
    """Same completeness rule the translation job uses for its final state."""
    units = [u for u in project.get('units', []) if u.get('category') != 'technical']
    translated = sum(bool(valid_unit(u)) for u in units)
    pending = len(units) - translated
    coverage = project.get('coverage', {})
    gaps = (any(f.get('status') in ('unreadable', 'partial') for f in coverage.get('files', []))
            or any(coverage.get('counts', {}).get(key, 0) for key in ('unreadable', 'partial')))
    mod_id = mod_id or project.get('mod', {}).get('id', '')
    if str(mod_id) == 'character-creation-destinies':
        gaps = (gaps or bool(coverage.get('destiny_gaps')) or not coverage.get('runtime_inventory')
                or bool(coverage.get('runtime_warnings')))
    return {'complete': bool(units) and not pending and not gaps, 'translated': translated,
            'total': len(units), 'pending': pending, 'coverage_gaps': gaps}


def saved_status(mod_id, root=None):
    """None means this mod has no saved translation project yet."""
    path = project_path(mod_id, root)
    if not path.is_file():
        return None
    try:
        return status_of(read_json(path), mod_id)
    except Exception as exc:
        return {'complete': False, 'translated': 0, 'total': 0, 'pending': 0,
                'coverage_gaps': False, 'error': type(exc).__name__ + ': ' + str(exc)}


def scan_statuses(mods, root=None):
    return {str(mod['id']): saved_status(mod['id'], root) for mod in mods}


def job_status(mod_id, result):
    """The finished job is authoritative: it just wrote the project files."""
    if 'saved_status' in result:
        return result['saved_status']
    if result.get('state') == 'success':
        total = int(result.get('count', 0) or 0)
        return {'complete': bool(total), 'translated': total, 'total': total, 'pending': 0,
                'coverage_gaps': False}
    total = int(result.get('count', 0) or 0) + int(result.get('pending', 0) or 0)
    return {'complete': False, 'translated': int(result.get('count', 0) or 0), 'total': total,
            'pending': int(result.get('pending', 0) or 0),
            'coverage_gaps': bool(result.get('coverage_gaps'))}


def tick(status):
    """A saved, complete translation ticks the mod in the list."""
    return '\u2713 ' if status and status.get('complete') else ''


def note(status):
    if not status:
        return ''
    if status.get('complete'):
        return f'{status["total"]:,} saved translations complete'
    if status.get('error'):
        return 'Saved translation project could not be read'
    if status.get('pending'):
        return f'{status["translated"]:,} of {status["total"]:,} saved; {status["pending"]:,} still need translation or review'
    if status.get('coverage_gaps'):
        return 'Saved translation is complete, but some files could not be read'
    return ''
