"""Local synthetic data. Not anonymization: unidentified data remains in the PDF."""
from __future__ import annotations

import datetime as dt
import random
import re
import string
from .dates import format_same_style, date_key


def _digits(rng, n):
    return ''.join(str(rng.randrange(10)) for _ in range(n))


def _mask_digits(template, digits):
    values = iter(digits)
    return ''.join(next(values) if c.isdecimal() else c for c in template)


def random_value(item, rng=None):
    rng = rng or random.SystemRandom()
    text, typ = item.value, item.type
    digits = re.sub(r'\D', '', text)
    for _ in range(100):
        if typ == 'data' and item.date_hit:
            date = dt.date(2000, 1, 1) + dt.timedelta(days=rng.randrange(365 * 35))
            value = format_same_style(item.date_hit, date)
        elif typ == 'PESEL' and len(digits) == 11:
            date = dt.date(1960, 1, 1) + dt.timedelta(days=rng.randrange(365 * 65))
            month = date.month + (20 if date.year >= 2000 else 0)
            base = f'{date.year % 100:02}{month:02}{date.day:02}' + _digits(rng, 4)
            checksum = (-sum(int(c) * w for c, w in zip(base, [1,3,7,9,1,3,7,9,1,3]))) % 10
            value = _mask_digits(text, base + str(checksum))
        elif typ == 'NIP' and len(digits) == 10:
            base = _digits(rng, 9)
            checksum = sum(int(c) * w for c, w in zip(base, [6,5,7,2,3,4,5,6,7])) % 11
            if checksum == 10:
                continue
            value = _mask_digits(text, base + str(checksum))
        elif typ == 'REGON' and len(digits) in (9, 14):
            base = _digits(rng, 8)
            check = sum(int(c) * w for c, w in zip(base, [8,9,2,3,4,5,6,7])) % 11 % 10
            base += str(check)
            if len(digits) == 14:
                base += _digits(rng, 4)
                check = sum(int(c) * w for c, w in zip(base, [2,4,8,5,0,9,7,3,6,1,2,4,8])) % 11 % 10
                base += str(check)
            value = _mask_digits(text, base)
        elif typ == 'nr konta' and len(digits) == 26:
            base = _digits(rng, 24)
            check = 98 - int(base + '252100') % 97
            value = _mask_digits(text, f'{check:02}' + base)
        elif typ in ('imię i nazwisko', 'nazwisko', 'nazwa'):
            first = rng.choice(['Anna', 'Maria', 'Julia', 'Piotr', 'Adam', 'Jan'])
            last = rng.choice(['Nowak', 'Lis', 'Wójcik', 'Mazur', 'Zając', 'Król'])
            value = last if typ == 'nazwisko' else first + ' ' + last
        else:
            # Preserve punctuation, spaces, case and the letter/digit pattern.
            value = ''.join(str(rng.randrange(10)) if c.isdecimal() else
                            rng.choice(string.ascii_uppercase) if c.isalpha() and c.isupper() and typ == 'symbol' else
                            rng.choice(string.ascii_lowercase) if c.isalpha() and typ == 'symbol' else c
                            for c in text)
        if value != text:
            return value
    raise ValueError(f'Nie można wylosować innej wartości: {text}')


def randomize_items(items, rng=None):
    """Identical values receive identical replacements, also across date formats."""
    rng = rng or random.SystemRandom()
    cache, result, date_cache = {}, {}, {}
    for item in items:
        if item.date_hit and (key := date_key(item.date_hit)):
            if key not in date_cache:
                base = item.date_hit.date or dt.date(item.date_hit.year, item.date_hit.month, 1)
                date_cache[key] = base + dt.timedelta(days=rng.randint(366, 3650))
            result[item.id] = format_same_style(item.date_hit, date_cache[key])
        else:
            key = (item.type, item.value)
            if key not in cache:
                cache[key] = random_value(item, rng)
            result[item.id] = cache[key]
    return result
