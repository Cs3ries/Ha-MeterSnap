"""Pure reading validation and interval rules (no Home Assistant dependency)."""
from datetime import datetime, timezone
import hashlib
import json
import math
from statistics import median


class ReadingError(ValueError):
    """An actionable input error, also understood by API clients."""


def parse_timestamp(value):
    try:
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        # Legacy naive timestamps were stored as UTC; retain that interpretation.
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ReadingError('Ungültiger Zeitpunkt / Invalid timestamp') from None


def number(value, optional=False):
    if optional and value is None:
        return None
    try:
        if isinstance(value, bool) or value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError
        result = float(value)
        if not math.isfinite(result) or result < 0:
            raise ValueError
        return round(result, 3)
    except (ValueError, TypeError, OverflowError):
        raise ReadingError('Stand muss eine endliche Zahl ab 0 sein / Reading must be a finite number >= 0') from None


def interval(previous, current):
    """A replacement closes the old meter and starts a new meter at one instant."""
    days = (parse_timestamp(current['timestamp']) - parse_timestamp(previous['timestamp'])).total_seconds() / 86400
    start = number(previous.get('reading'), optional=True)
    end = number(current.get('old_reading') if current.get('kind') == 'replacement' else current.get('reading'), optional=True)
    if days <= 0:
        raise ReadingError('Doppelter Ablesezeitpunkt / Duplicate reading timestamp')
    if start is None or end is None:
        return None, days
    if end < start:
        raise ReadingError('Sinkender Stand: Ablesung korrigieren oder Zählerwechsel erfassen / Decreasing reading: correct the reading or record a meter replacement')
    return round(end - start, 3), days


def sort_key(item):
    try:
        return parse_timestamp(item.get('timestamp'))
    except ReadingError:
        return datetime.min.replace(tzinfo=timezone.utc)


def validate_change(before, after, changed_id, meter):
    """Validate only affected edges so existing damaged records remain repairable."""
    old_edges = {(a['id'], b['id']) for a, b in zip(before, before[1:])}
    rates = []
    for a, b in zip(before, before[1:]):
        if changed_id in (a['id'], b['id']):
            continue
        try:
            delta, days = interval(a, b)
            if delta is not None:
                rates.append(delta / days)
        except ReadingError:
            pass
    # Conservative daily fallback without enough history, otherwise 5x historical median.
    reference = median(rates) if rates else 0
    limit = max(100 if meter == 'electricity' else 30, 5 * reference)
    warnings = []
    for item in after:
        if item['id'] == changed_id:
            instant = parse_timestamp(item['timestamp'])
            if any(other['id'] != changed_id and sort_key(other) == instant for other in after):
                raise ReadingError('Doppelter Ablesezeitpunkt / Duplicate reading timestamp')
    for a, b in zip(after, after[1:]):
        if changed_id not in (a['id'], b['id']) and (a['id'], b['id']) in old_edges:
            continue
        delta, days = interval(a, b)
        if delta is not None and delta / days > limit:
            warnings.append({'from': a['timestamp'], 'to': b['timestamp'], 'consumption': delta,
                             'days': days, 'daily_rate': delta / days, 'limit': limit,
                             'reference_daily_rate': reference})
    return warnings


def confirmation_token(items, warnings):
    # Derived metrics are deliberately excluded. Changes by another card invalidate confirmation.
    fields = ('id', 'kind', 'reading', 'old_reading', 'timestamp', 'notes')
    payload = [{k: item.get(k) for k in fields} for item in items]
    return hashlib.sha256(json.dumps([payload, warnings], sort_keys=True).encode()).hexdigest()
