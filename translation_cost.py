"""Local full-mod cost estimates and the friends edition's translation policy."""
import math
import tempfile
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from app_config import is_friends_build, translation_batch_size
from extractor import CJK, Scanner

# Verified against OpenRouter's model feed on 2026-09-13. Use peak, uncached
# rates, not the lower weekend/off-peak headline price. USD per million tokens.
INPUT_USD_PER_M = Decimal('0.30')
OUTPUT_USD_PER_M = Decimal('1.20')
# ECB EUR cross rates, 2026-09-11 (latest working day at verification).
USD_TO_GBP = Decimal('0.85815') / Decimal('1.1592')
FRIENDS_LIMIT_PENCE = Decimal('5')  # Five pence = GBP 0.05.
ESTIMATE_MARGIN = Decimal('1.30')
PRICING_NOTE = ('DeepSeek V4.1 Flash peak rates: $0.30 input / $1.20 output per million tokens '
                '(verified 13 September 2026). GBP conversion: ECB, 11 September 2026. '
                'Includes request overhead and a 30% allowance. Estimates cover all extracted '
                'nontechnical text, including saved translations, and are not a billing guarantee. '
                'Retries, output length, prices and exchange rates can change actual cost.')


def is_destiny_project(project):
    from destinies import PROJECT_ID
    fields = project.get('destiny_fields')
    if project.get('mod', {}).get('id') != PROJECT_ID or not isinstance(fields, list):
        return False
    sources = {f.get('source') for f in fields}
    return all(u['source'] in sources and u['category'] == 'player_text' for u in project['units'])


def estimate_project(project, batch_size=None):
    from translation import protect
    batch_size = translation_batch_size() if batch_size is None else batch_size
    from app_config import BATCH_SIZE_CHOICES
    if type(batch_size) is not int or batch_size not in BATCH_SIZE_CHOICES:
        raise ValueError('Invalid estimate batch size')
    # Match the translator's unique source entries, source-character target and
    # batch limit. Ignore saved progress: this is the cost of the entire mod.
    sources = list(dict.fromkeys(u['source'] for u in project['units'] if u['category'] != 'technical'))
    input_tokens = output_tokens = batches = batch_count = batch_chars = 0
    for source in sources:
        if batch_count == 0 or batch_count >= batch_size or batch_chars + len(source) > 6000:
            batches += 1
            batch_count = batch_chars = 0
        masked, _ = protect(source)
        chinese = len(CJK.findall(masked))
        other = math.ceil((len(masked) - chinese) / 3)
        input_tokens += chinese + other + 4  # JSON quoting and separators.
        output_tokens += math.ceil(chinese * 1.5) + other + 4
        batch_count += 1
        batch_chars += len(source)
    input_tokens += batches * 250  # System instructions and message framing.
    usd = (input_tokens * INPUT_USD_PER_M + output_tokens * OUTPUT_USD_PER_M) / Decimal(1000000)
    pence = usd * USD_TO_GBP * 100 * ESTIMATE_MARGIN
    counts = project.get('coverage', {}).get('counts', {})
    incomplete = any(counts.get(s, 0) for s in ('unreadable', 'partial')) or any(
        f.get('status') in ('unreadable', 'partial') for f in project.get('coverage', {}).get('files', []))
    return {'pence': str(pence), 'entries': len(sources), 'batches': batches,
            'input_tokens': input_tokens, 'output_tokens': output_tokens,
            'complete': not incomplete, 'batch_size': batch_size}


def format_pence(estimate):
    amount = Decimal(estimate['pence']).quantize(Decimal('0.001'), rounding=ROUND_CEILING)
    return ('~' if estimate.get('complete', True) else '≥') + f'{amount:f}p'


def full_translation_allowed(estimate):
    return bool(estimate and estimate.get('complete') and Decimal(estimate['pence']) <= FRIENDS_LIMIT_PENCE)


def enforce_translation_policy(project, batch_size=None, profile=None):
    if not is_friends_build() or is_destiny_project(project):
        return
    if profile is None:
        from app_config import service_profile
        profile = service_profile()
    if profile.get('personal_key'):
        return
    estimate = estimate_project(project, batch_size)
    if not full_translation_allowed(estimate):
        reason = ('Some source files could not be fully read.' if not estimate['complete'] else
                  'The full-mod estimate is ' + format_pence(estimate) + '.')
        raise PermissionError(reason + ' The shared key allows full translation only up to '
                              '5p (£0.05). Add your own OpenRouter key in Options > API key to remove this limit. '
                              'Destiny-menu translation and installing saved translations remain available.')


def estimate_mod(mod, game, batch_size=None, stop=None):
    """Scan read-only; never overwrite a saved translation project for estimates."""
    from destinies import PROJECT_ID, scan_destinies
    if mod['id'] == PROJECT_ID:
        with tempfile.TemporaryDirectory(prefix='Guigu cost estimate ') as folder:
            project = scan_destinies(game, Path(folder), stop=stop)
    else:
        project = Scanner(mod, stop=stop).scan()
    return estimate_project(project, batch_size)
