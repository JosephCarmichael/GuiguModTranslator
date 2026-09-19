"""Per-mod price selection and a sequential, resumable translation queue."""
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path

MIN_PRICE_PENCE = 5
MAX_PRICE_PENCE = 200


def validate_price(value):
    if type(value) is not int or not MIN_PRICE_PENCE <= value <= MAX_PRICE_PENCE:
        raise ValueError('Choose a per-mod price between 5p and £2.')
    return value


def amount(estimate):
    if not estimate or estimate.get('error') or not estimate.get('complete'):
        return None
    try:
        value = Decimal(estimate['pence'])
        return value if value.is_finite() and value >= 0 else None
    except (InvalidOperation, KeyError, TypeError, ValueError):
        return None


def within_price(estimate, limit):
    validate_price(limit)
    value = amount(estimate)
    return value is not None and value <= limit


def money(pence):
    value = Decimal(pence)
    if value >= 100:
        return '£' + str((value / 100).quantize(Decimal('.01'), rounding=ROUND_CEILING))
    return format(value.quantize(Decimal('.01'), rounding=ROUND_CEILING).normalize(), 'f') + 'p'


def plan_bulk(mods, estimates, limit, limited=False):
    from destinies import PROJECT_ID
    from translation_cost import full_translation_allowed
    validate_price(limit)
    matches, pending, excluded = [], 0, 0
    for mod in mods:
        if mod['id'] == PROJECT_ID:
            continue  # The separate destiny action is not an individual mod.
        estimate = estimates.get(mod['id'])
        if estimate is None:
            pending += 1
        elif within_price(estimate, limit) and (not limited or full_translation_allowed(estimate)):
            matches.append(mod)
        else:
            excluded += 1
    matches.sort(key=lambda mod: (amount(estimates[mod['id']]), mod.get('name', '').casefold(), mod['id']))
    return {'mods': matches, 'pending': pending, 'excluded': excluded,
            'total_pence': str(sum((amount(estimates[m['id']]) for m in matches), Decimal(0)))}


def run_bulk(mods, project_root, limit, progress, stop, *, game, concurrency=None, batch_size=None, prepare_mod=None):
    from extractor import atomic_json
    from diagnostics import redact
    from mod_workflow import run_job
    validate_price(limit)
    root = Path(project_root)
    report = {'state': 'running', 'per_mod_limit_pence': limit, 'total_mods': len(mods), 'results': []}
    def save():
        atomic_json(root / 'translate-all-last.json', report)
    save()
    for index, mod in enumerate(mods):
        if stop():
            report['state'] = 'cancelled'
            break
        # Prefer the saved English title so the queue matches the mod list.
        name = mod.get('title') or mod.get('name', mod['id'])
        def update(message):
            progress(100 * index / max(1, len(mods)), f'{index + 1}/{len(mods)} · {name} · {message}')
        try:
            update('Checking current price and saved translations…')
            if prepare_mod:
                prepare_mod(mod)
            result = run_job(mod, root / mod['id'], update, stop, game=game,
                             concurrency=concurrency, batch_size=batch_size, max_pence=limit)
        except InterruptedError:
            result = {'state': 'cancelled'}
        except Exception as exc:
            result = {'state': 'error', 'message': redact(str(exc))}
        report['results'].append({'mod_id': mod['id'], 'mod_name': name, **result})
        if result['state'] == 'error':
            report['state'] = 'stopped'
        elif result['state'] == 'cancelled' or stop():
            report['state'] = 'cancelled'
        save()
        if report['state'] != 'running':
            break
        progress(100 * (index + 1) / max(1, len(mods)), f'{index + 1}/{len(mods)} · {name} · {result["state"]}')
    if report['state'] == 'running':
        report['state'] = 'complete'
    report['not_started'] = len(mods) - len(report['results'])
    save()
    return report


def bulk_summary(report):
    from collections import Counter
    counts = Counter(item['state'] for item in report['results'])
    prefix = {'complete': 'Translate all finished', 'cancelled': 'Translate all cancelled',
              'stopped': 'Translate all stopped'}[report['state']]
    parts = [f'{counts["success"]} complete']
    for key, label in (('partial', 'partial'), ('skipped', 'skipped after price check'),
                       ('empty', 'without readable text'), ('error', 'failed')):
        if counts[key]:
            parts.append(f'{counts[key]} {label}')
    if report['not_started']:
        parts.append(f'{report["not_started"]} not started')
    error = next((item.get('message', '') for item in report['results'] if item['state'] == 'error'), '')
    return prefix + ': ' + ', '.join(parts) + '. Saved translations are kept.' + (' ' + error if error else '')
