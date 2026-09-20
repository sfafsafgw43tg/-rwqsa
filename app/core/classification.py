"""Conservative local classification; unknown text is kept, never discarded."""
import re

# Sorting is separate from extraction and never changes PDF coordinates.
TYPE_ORDER = (
    'imię i nazwisko', 'nazwisko', 'nazwa firmy', 'adres', 'miejscowość',
    'kod pocztowy', 'email', 'adres www', 'data', 'PESEL', 'NIP', 'REGON',
    'nr konta', 'telefon', 'telefon?', 'kwota', 'kwota?', 'procent',
    'numer', 'symbol', 'ulica nr', 'ułamek', 'nazwa', 'nagłówek', 'etykieta', 'tekst', 'znak',
)
STRUCTURAL_TYPES = {'nagłówek', 'etykieta', 'tekst', 'znak'}

LETTERS = r'[^\W\d_]'
EMAIL = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+', re.UNICODE)
URL = re.compile(r'(?i)\b(?:https?://|www\.)[^\s<>]+')
CITY = re.compile(r'\s*(' + LETTERS + r'+(?:[ \t-]+' + LETTERS + r'+)*)')
STREET = re.compile(
    r'(?<!\w)(?P<street>' + LETTERS + r'[^\n:;,]*?)\s*'
    r'(?P<number>\d+[A-Za-z]?(?:/\d+[A-Za-z]?)?)(?=$|[,;]|\s+\d{2}-\d{3})'
)
STREET_PREFIX = re.compile(r'(?i)^(?:ul\.?|ulica|al\.?|aleja|aleje|os\.?|osiedle|pl\.?|plac)\s')
COMPANY = re.compile(r'(?i)\b(?:sp\.?\s*z\s*o\.?\s*o\.?|s\.a\.|ltd\.?|gmbh|inc\.?)\s*$')
HEADING = re.compile(r'(?i)^(?:faktura|umowa|załącznik|potwierdzenie|oświadczenie|wniosek|rachunek)\b')


# Some Windows fonts map the same space/hyphen glyph to NBSP or soft hyphen
# when embedded in a PDF. Normalize only 1:1 characters for matching/display;
# raw spans and glyph positions are retained for redaction and coverage.
_TRANSLATION = str.maketrans({'\u00a0': ' ', '\u202f': ' ', '\u00ad': '-',
                             '\u2010': '-', '\u2011': '-', '\u2212': '-'})


def normalize_text(text):
    return text.translate(_TRANSLATION)


def positional_key(item):
    return (item.page, round(item.rect[1], 1), item.rect[0])


def sort_items(items, mode='type'):
    if mode == 'position':
        return sorted(items, key=positional_key)
    if mode == 'value':
        return sorted(items, key=lambda item: (item.value.casefold(), positional_key(item)))
    rank = {typ: index for index, typ in enumerate(TYPE_ORDER)}
    return sorted(items, key=lambda item: (rank.get(item.type, len(rank)), item.type, positional_key(item)))


def postal_below(line, lines, postal_regex):
    x0, _, x1, y1 = line['bbox']
    for other in lines:
        ox0, oy0, ox1, _ = other['bbox']
        if (other is not line and -2 <= oy0 - y1 <= 30
                and min(x1, ox1) > max(x0, ox0) and postal_regex.search(other['text'])):
            return True
    return False


def fallback_type(fragment, line):
    """Only a category guess, not a gate controlling text visibility."""
    if not any(char.isalnum() for char in fragment):
        return 'znak', 1.0
    if HEADING.match(fragment.strip()):
        return 'nagłówek', .8
    if fragment.rstrip().endswith((':', '=')):
        return 'etykieta', .9
    if fragment.isupper() and len(fragment) > 3:
        return 'nagłówek', .45
    return 'tekst', .3
