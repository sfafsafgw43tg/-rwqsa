"""All readable text remains visible; semantic classification never filters it out."""
from collections import Counter
from pathlib import Path
import random
import sys

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.classification import normalize_text
from app.core import analyzer, fonts, replacer
from app.core.classification import sort_items, STRUCTURAL_TYPES
from app.core.randomize import randomize_items


def page_with_text(document, lines, rotation=0, page_rotation=0):
    page = document.new_page(width=1100, height=800)
    font = fonts.resolve_font('Arial')['fontfile']
    assert font, 'Test requires a Unicode system font'
    page.insert_font(fontname='test', fontfile=font)
    for index, text in enumerate(lines):
        page.insert_text((200, 200 + index * 25), text, fontsize=12, fontname='test', rotate=rotation)
    page.set_rotation(page_rotation)
    return page


def assert_full_coverage(page):
    lines = analyzer.extract_lines(page)
    items = analyzer.analyze_lines(lines)
    wanted, actual = Counter(), Counter()
    for line in lines:
        for span in line['spans']:
            for index, char in enumerate(span.text):
                if not char.isspace():
                    wanted[(id(span), index, char)] += 1
    for item in items:
        assert item.pieces
        for piece in item.pieces:
            span = piece.span
            start = span.char_origins.index(piece.origin)
            assert span.text[start:start + len(piece.text)] == piece.text
            for offset, char in enumerate(piece.text):
                if not char.isspace():
                    actual[(id(span), start + offset, char)] += 1
    assert actual == wanted  # Each non-whitespace glyph appears exactly once.
    return items


@pytest.mark.parametrize('text', [
    'DAWID NOWAKOWSKI', 'DŁUGA 65A', '29-470 WROCŁAW',
    'UWAGI: dowolny tekst małymi literami, bez liczb.',
    'FAKTURA VAT', 'Słownie: cztery tysiące złotych 00/100.',
    '123ABC456 — ABC123 — każdy fragment.', 'e-mail: osoba123@example.pl',
    'https://example.pl/folder123?k=5', 'Spółka Przykład sp. z o.o.',
    'I A B C / + = :', 'PESEL85010112345', 'Zwykłe zdanie bez dopasowania',
    'MiXeDcAsE i ćma, 漢字', 'NIP: 5260001246, data: 29.02.2024',
])
def test_all_glyphs_once(text):
    with pymupdf.open() as document:
        page = page_with_text(document, [text])
        assert_full_coverage(page)


def test_screenshot_address_in_two_columns():
    # Anonymized name; same all-caps / street / postcode layout as the supplied image.
    with pymupdf.open() as document:
        page = page_with_text(document, [])
        for x in (40, 650):
            for y, text in [(80, 'DAWID NOWAKOWSKI'), (100, 'DŁUGA 65A'), (120, '29-470 WROCŁAW')]:
                page.insert_text((x, y), text, fontsize=12, fontname='test')
        items = assert_full_coverage(page)
        expected = Counter({('imię i nazwisko', 'DAWID NOWAKOWSKI'): 2,
                            ('adres', 'DŁUGA 65A'): 2,
                            ('kod pocztowy', '29-470'): 2,
                            ('miejscowość', 'WROCŁAW'): 2})
        assert Counter((it.type, it.value) for it in items) == expected
        for item in items:
            # Search the literal encoded glyphs, not the normalized UI value:
            # Arial on Windows may map the displayed '-' to soft hyphen.
            raw_value = ''.join(piece.text for piece in item.pieces)
            matches = page.search_for(raw_value, flags=pymupdf.TEXT_PRESERVE_WHITESPACE | pymupdf.TEXT_PRESERVE_LIGATURES)
            assert any(tuple(box) == pytest.approx(item.rect, abs=.01) for box in matches)
            assert item.rect[2] - item.rect[0] < 300  # no frame across columns


def test_specific_categories_and_fallback():
    with pymupdf.open() as document:
        page = page_with_text(document, ['FAKTURA VAT', 'uwagi: własny opis bez liczb',
                                         'e-mail: anna12@example.pl', 'strona: https://example.pl/a12',
                                         'Firma Alfa sp. z o.o.'])
        items = assert_full_coverage(page)
        pairs = {(it.type, it.value) for it in items}
        assert ('nagłówek', 'FAKTURA VAT') in pairs
        assert ('email', 'anna12@example.pl') in pairs
        assert ('adres www', 'https://example.pl/a12') in pairs
        assert ('nazwa firmy', 'Firma Alfa sp. z o.o.') in pairs
        assert any(it.type == 'tekst' for it in items)


def test_sorting_by_type_and_position():
    with pymupdf.open() as document:
        page = page_with_text(document, ['Numer: AB12CD34', 'DAWID NOWAKOWSKI', '29-470 WROCŁAW'])
        items = analyzer.analyze_page(page)
        grouped = sort_items(items)
        assert grouped[0].type == 'imię i nazwisko'
        types = [it.type for it in grouped]
        for typ in set(types):
            indices = [i for i, t in enumerate(types) if t == typ]
            assert indices == list(range(min(indices), max(indices) + 1))
        assert sort_items(items, 'position') == items
        assert [it.value.casefold() for it in sort_items(items, 'value')] == sorted(it.value.casefold() for it in items)
        assert {it.id for it in items} == {it.id for it in grouped}


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('page_rotation', [0, 90])
def test_rotated_text_coverage_and_replacement(tmp_path, rotation, page_rotation):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as document:
        page = page_with_text(document, ['AB12CD34'], rotation=rotation, page_rotation=page_rotation)
        items = assert_full_coverage(page)
        assert len(items) == 1
        assert items[0].rotation == rotation
        document.save(source)
    output = tmp_path / 'edited.pdf'
    reports = replacer.apply_replacements(str(source), str(output), [(items[0], 'CD34EF56')])
    assert reports[0]['status'].startswith('ok')
    with pymupdf.open(output) as document:
        text = normalize_text(document[0].get_text())
        assert 'AB12CD34' not in text
        assert 'CD34EF56' in text
        lines = analyzer.extract_lines(document[0])
        line = next(line for line in lines if 'CD34EF56' in line['text'])
        assert line['dir'] == pytest.approx(items[0].direction)


def test_arbitrary_rotation_is_listed_not_silently_lost(tmp_path):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as document:
        page = document.new_page()
        point = pymupdf.Point(200, 300)
        page.insert_text(point, 'ROTATED TEXT', morph=(point, pymupdf.Matrix(30)))
        items = assert_full_coverage(page)
        assert items and all(not item.editable for item in items)
        document.save(source)
    output = tmp_path / 'out.pdf'
    reports = replacer.apply_replacements(str(source), str(output), [(items[0], 'NEW TEXT')])
    assert reports[0]['status'].startswith('pominięto: dowolny kąt')
    with pymupdf.open(output) as document:
        assert 'ROTATED TEXT' in document[0].get_text()


def test_plain_text_replacement_keeps_adjacent_value(tmp_path):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as document:
        page = page_with_text(document, ['uwagi: test bez liczb', 'Numer: 123456'])
        items = analyzer.analyze_page(page)
        item = next(it for it in items if it.type == 'tekst')
        document.save(source)
    output = tmp_path / 'out.pdf'
    reports = replacer.apply_replacements(str(source), str(output), [(item, 'nowy opis')])
    assert reports[0]['status'].startswith('ok')
    with pymupdf.open(output) as document:
        text = normalize_text(document[0].get_text())
        assert 'nowy opis' in text
        assert '123456' in text
        assert 'test bez liczb' not in text


def test_randomization_does_not_fail_on_new_text_types():
    with pymupdf.open() as document:
        page = page_with_text(document, ['FAKTURA VAT', 'Numer: AB12CD34', 'DAWID NOWAKOWSKI',
                                         'uwagi: dowolny tekst', 'DŁUGA 65A', '29-470 WROCŁAW',
                                         'email: a@example.pl', 'www.example.pl'])
        items = analyzer.analyze_page(page)
        values = randomize_items(items, random.Random(23))
        for item in items:
            if item.type in STRUCTURAL_TYPES:
                assert item.id not in values
            elif item.id in values:
                assert values[item.id] != item.value
                if item.value.isupper():
                    assert values[item.id].isupper()
        selected = randomize_items(items, random.Random(34), include_text=True)
        assert all(it.id in selected for it in items if any(c.isalnum() for c in it.value))


def test_ocr_lines_also_keep_unclassified_words():
    span = analyzer.SpanInfo('dowolny tekst OCR', (20, 20, 170, 35), (20, 32), 'Helvetica', 12, 0, 0)
    line = {'text': span.text, 'bbox': span.bbox, 'spans': [span], 'dir': (1, 0)}
    items = analyzer.analyze_lines([line], ocr=True)
    assert ''.join(it.value.replace(' ', '') for it in items) == span.text.replace(' ', '')
    assert all(it.source == 'ocr' for it in items)


def test_low_confidence_ocr_word_is_visible_with_warning(monkeypatch):
    import pytesseract
    from app.core import ocr
    monkeypatch.setattr(ocr, 'tesseract_available', lambda: True)
    monkeypatch.setattr(pytesseract, 'get_languages', lambda **kwargs: ['pol'])
    data = {'text': ['niepewne', ''], 'conf': [12.5, -1], 'left': [40, 0], 'top': [60, 0],
            'width': [150, 0], 'height': [30, 0], 'block_num': [1, 0], 'par_num': [1, 0], 'line_num': [1, 0]}
    monkeypatch.setattr(pytesseract, 'image_to_data', lambda *args, **kwargs: data)
    with pymupdf.open() as document:
        page = document.new_page()
        lines = ocr.ocr_page_lines(page)
        items = analyzer.analyze_lines(lines, ocr=True)
        assert len(items) == 1
        assert items[0].value == 'niepewne'
        assert items[0].ocr_confidence == pytest.approx(.125)


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_edit_dense_rows_does_not_erase_adjacent_text(tmp_path, rotation):
    source = tmp_path / 'source.pdf'
    with pymupdf.open() as document:
        page = document.new_page()
        if rotation in (0, 180):
            neighbour = (200, 211)
        else:
            neighbour = (211, 200)
        page.insert_text((200, 200), 'JAN KOWALSKI', fontsize=12, rotate=rotation)
        page.insert_text(neighbour, 'DLUGA 65A', fontsize=12, rotate=rotation)
        document.save(source)
    items, _ = analyzer.analyze_document(str(source))
    person = next(it for it in items if it.value == 'JAN KOWALSKI')
    output = tmp_path / 'edited.pdf'
    reports = replacer.apply_replacements(str(source), str(output), [(person, 'ADAM NOWAK')])
    assert reports[0]['status'].startswith('ok')
    with pymupdf.open(output) as document:
        text = normalize_text(document[0].get_text())
        assert 'ADAM NOWAK' in text
        assert 'JAN KOWALSKI' not in text
        assert 'DLUGA 65A' in text


def test_windows_space_and_hyphen_aliases_preserve_offsets():
    text = 'DAWID\xa0NOWAKOWSKI'
    street = 'DŁUGA\xa065A'
    town = '29\xad470\xa0WROCŁAW'
    lines = []
    for y, value in [(20, text), (40, street), (60, town)]:
        span = analyzer.SpanInfo(value, (20, y, 220, y + 12), (20, y + 10), 'Arial', 12, 0, 0)
        lines.append({'text': value, 'spans': [span], 'bbox': span.bbox, 'dir': (1, 0)})
    items = analyzer.analyze_lines(lines)
    pairs = {(item.type, item.value) for item in items}
    assert ('imię i nazwisko', 'DAWID NOWAKOWSKI') in pairs
    assert ('adres', 'DŁUGA 65A') in pairs
    assert ('kod pocztowy', '29-470') in pairs
    assert ('miejscowość', 'WROCŁAW') in pairs
    assert any('\xa0' in piece.text for item in items for piece in item.pieces)
    assert any('\xad' in piece.text for item in items for piece in item.pieces)
    assert len(normalize_text(town)) == len(town)
