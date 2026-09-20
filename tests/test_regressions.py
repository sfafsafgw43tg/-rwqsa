"""Run: python -m pytest tests/test_regressions.py -q."""
import datetime as dt
import hashlib
from pathlib import Path
import random
import re
import sys

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.classification import normalize_text
from app.core import analyzer, batch, dates, filedates, fonts, ocr, replacer, report
from app.core.document import Document
from app.core.randomize import randomize_items, random_value
from app.shortcut import prepare_icon


@pytest.fixture
def pdf(tmp_path):
    def make(text, name='source.pdf', rotation=0):
        path = tmp_path / name
        with pymupdf.open() as doc:
            page = doc.new_page(width=600, height=800)
            font = fonts.resolve_font('Arial')['fontfile']
            if font:
                page.insert_font(fontname='test', fontfile=font)
            page.insert_text((40, 60), text, fontname='test' if font else 'helv', fontsize=12)
            page.set_rotation(rotation)
            doc.save(path)
        return path
    return make


@pytest.mark.parametrize('value', ['AB12CD34', 'abc12DEF34', 'N123abc', '12abc34', 'FV/2024/01/15', 'AA-12/BB34'])
def test_glued_identifiers(pdf, value):
    items, _ = analyzer.analyze_document(str(pdf('Numer: ' + value)))
    assert any(i.value == value for i in items)
    assert not any(i.value != value and i.value in value for i in items)


@pytest.mark.parametrize('value,typ', [('PESEL85010112345', 'PESEL'), ('Kwota: 100,00zł', 'kwota'),
                                     ('VAT: 23%', 'procent'), ('Ilość: 2', 'numer')])
def test_labels_and_units_stuck_to_digits(pdf, value, typ):
    items, _ = analyzer.analyze_document(str(pdf(value)))
    assert any(i.type == typ for i in items)


def test_grosz_crash_and_false_detection(pdf):
    items, _ = analyzer.analyze_document(str(pdf('Słownie: 00/100 Jan Kowalski')))
    assert any(i.value == 'Jan Kowalski' for i in items)
    # All-text mode keeps the fraction intact instead of discarding it.
    assert not any(i.value in ('00', '100') for i in items)
    assert sum(i.value == '00/100' and i.type == 'ułamek' for i in items) == 1


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_exact_glyph_geometry(pdf, rotation):
    path = pdf('Numer: 123456', rotation=rotation)
    items, _ = analyzer.analyze_document(str(path))
    item = next(i for i in items if i.value == '123456')
    with pymupdf.open(path) as doc:
        assert item.rect == pytest.approx(tuple(doc[0].search_for('123456')[0]), abs=.01)


def test_no_cross_column_date_suppression(tmp_path):
    path = tmp_path / 'columns.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((30, 60), '15.01.2024')
        page.insert_text((300, 60), '29.02.2024')
        doc.save(path)
    items, _ = analyzer.analyze_document(str(path))
    assert {i.value for i in items if i.type == 'data'} == {'15.01.2024', '29.02.2024'}


def test_mixed_identifier_spans(tmp_path):
    path = tmp_path / 'spans.pdf'
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((40, 60), 'AB12', fontname='helv', fontsize=12)
        x = 40 + pymupdf.get_text_length('AB12', fontname='helv', fontsize=12)
        page.insert_text((x, 60), 'CD34', fontname='hebo', fontsize=12)
        doc.save(path)
    items, _ = analyzer.analyze_document(str(path))
    item = next(i for i in items if i.value == 'AB12CD34')
    assert len(item.pieces) == 2
    output = tmp_path / 'edited.pdf'
    reports = replacer.apply_replacements(str(path), str(output), [(item, 'EF56GH78')])
    assert reports[0]['status'].startswith('ok')
    with pymupdf.open(output) as doc:
        assert 'EF56GH78' in doc[0].get_text()
        assert 'AB12' not in doc[0].get_text()


def test_replacement_preserves_label_and_neighbours(pdf, tmp_path):
    path = pdf('Numer: 123456; koniec')
    item = next(i for i in analyzer.analyze_document(str(path))[0] if i.value == '123456')
    output = tmp_path / 'out.pdf'
    replacer.apply_replacements(str(path), str(output), [(item, '654321')])
    with pymupdf.open(output) as doc:
        text = normalize_text(doc[0].get_text())
        assert 'Numer:' in text and 'koniec' in text and '654321' in text and '123456' not in text


def test_overflow_leaves_original_intact(pdf, tmp_path):
    path = pdf('Numer: 123456')
    item = next(i for i in analyzer.analyze_document(str(path))[0] if i.value == '123456')
    out = tmp_path / 'out.pdf'
    reps = replacer.apply_replacements(str(path), str(out), [(item, 'X' * 1000)])
    assert reps[0]['status'].startswith('pominięto')
    with pymupdf.open(out) as doc:
        assert '123456' in doc[0].get_text()
        assert 'XXXX' not in doc[0].get_text()


def test_reject_source_overwrite(pdf):
    path = pdf('Numer: 123456')
    with pytest.raises(ValueError):
        replacer.apply_replacements(str(path), str(path), [])


def test_undo_redo_stale_result_and_safe_save(pdf, tmp_path):
    path = pdf('Numer: 123456')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    doc = Document(path)
    try:
        item = next(i for i in doc.items if i.value == '123456')
        doc.change({item.id: '654321'})
        assert doc.dirty
        doc.apply()
        assert doc.current_result
        doc.change({})
        assert not doc.current_result
        with pytest.raises(ValueError):
            doc.save(tmp_path / 'stale.pdf')
        doc.undo()
        assert doc.current_result
        doc.redo()
        doc.apply()
        with pymupdf.open(doc.result) as result:
            assert '123456' in result[0].get_text()  # no stale server new_value
        doc.save(tmp_path / 'saved.pdf')
        assert not doc.dirty
        with pytest.raises(ValueError):
            doc.save(path)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before
        workdir = doc.source.parent
    finally:
        doc.close()
    assert not workdir.exists()


def test_pdf_validation(tmp_path):
    invalid = tmp_path / 'invalid.pdf'
    invalid.write_text('not a PDF')
    with pytest.raises(Exception):
        Document(invalid)
    protected = tmp_path / 'protected.pdf'
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(protected, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='secret')
    with pytest.raises(ValueError, match='hasłem'):
        Document(protected)


@pytest.mark.parametrize('text,typ', [('PESEL: 44051401359', 'PESEL'), ('NIP: 5260001246', 'NIP'),
                                     ('Numer konta: 61 1090 1014 0000 0712 1981 2874', 'nr konta'),
                                     ('Numer: aB12CD34', 'symbol'), ('Data: 29.02.2024', 'data')])
def test_randomization_validity_and_format(pdf, text, typ):
    item = next(i for i in analyzer.analyze_document(str(pdf(text)))[0] if i.type == typ)
    rng = random.Random(7)
    for _ in range(50):
        value = random_value(item, rng)
        assert value != item.value
        digits = re.sub(r'\D', '', value)
        if typ == 'PESEL':
            assert analyzer.pesel_valid(digits)
            month = int(digits[2:4])
            dt.date((2000 if month > 20 else 1900) + int(digits[:2]), month % 20, int(digits[4:6]))
        elif typ == 'NIP':
            assert analyzer.nip_valid(digits)
        elif typ == 'nr konta':
            assert int(digits[2:] + '2521' + digits[:2]) % 97 == 1
            assert len(value) == len(item.value)
        elif typ == 'symbol':
            assert len(value) == len(item.value)
            assert [c.isdigit() for c in value] == [c.isdigit() for c in item.value]
            assert [c.isupper() for c in value] == [c.isupper() for c in item.value]
        else:
            assert dates.find_dates(value)[0].date is not None


def test_random_same_values_and_equivalent_dates(pdf):
    items, _ = analyzer.analyze_document(str(pdf('15.01.2024  2024-01-15  AB12CD34  AB12CD34')))
    values = randomize_items(items, random.Random(12))
    dates_values = [dates.find_dates(values[i.id])[0].date for i in items if i.type == 'data']
    assert len(dates_values) == 2 and len(set(dates_values)) == 1
    symbols = [values[i.id] for i in items if i.type == 'symbol']
    assert len(symbols) == 2 and len(set(symbols)) == 1


def test_batch_does_not_match_wrong_old_value(pdf):
    items, _ = analyzer.analyze_document(str(pdf('Numer: 123456')))
    item = next(i for i in items if i.value == '123456')
    assert batch._match_items(items, [{'opis': item.label, 'stara': '999999', 'nowa': '111111'}]) == []
    assert batch._match_items(items, [{'opis': item.label, 'stara': '', 'nowa': '111111'}])


def test_mapping_validation(tmp_path):
    path = tmp_path / 'map.json'
    path.write_text('{"nowa": "foo"}')
    with pytest.raises(ValueError):
        report.import_mapping(str(path))


def test_invalid_calendar_dates():
    assert not dates.find_dates('31.02.2024')
    assert not dates.find_dates('29.02.2023')
    assert dates.find_dates('29.02.2024')


def test_embedded_font_flags():
    font = fonts.resolve_font('Arial')
    if not font['fontfile']:
        pytest.skip('No system font')
    info = fonts.font_from_buffer(Path(font['fontfile']).read_bytes())
    assert info and info['source'] == 'embedded'


def test_file_timestamp_and_xmp_preservation(pdf, tmp_path):
    path = pdf('Numer: 123456')
    with pymupdf.open(path) as doc:
        doc.set_xml_metadata('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Keep me</dc:title></rdf:Description></rdf:RDF></x:xmpmeta>')
        doc.saveIncr()
    changed = dt.datetime(2020, 1, 2, 12, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    filedates.set_pdf_dates(str(path), modification=changed)
    with pymupdf.open(path) as doc:
        assert 'Keep me' in doc.get_xml_metadata()
        assert '20200102100000' in doc.metadata['modDate']
    doc = Document(path)
    try:
        doc.apply()
        out = tmp_path / 'dated.pdf'
        doc.save(out, modified=changed)
        assert out.stat().st_mtime == pytest.approx(changed.timestamp(), abs=1)
    finally:
        doc.close()


def test_ocr_geometry_and_duplicate_pages(pdf, monkeypatch):
    path = pdf('Numer: 123456')
    monkeypatch.setattr(ocr, 'ocr_words_with_geometry', lambda *a, **k: [
        {'text': 'AB12CD34', 'bbox': (40, 40, 140, 55), 'line': (1, 1, 1)}])
    with pymupdf.open(path) as doc:
        doc[0].set_rotation(90)
        lines = ocr.ocr_page_lines(doc[0])
        assert doc[0].rotation == 90
        items = analyzer.analyze_lines(lines, ocr=True)
        assert items[0].rect == pytest.approx((40, 40, 140, 55))


def test_icon_uses_supplied_image(tmp_path, monkeypatch):
    from PIL import Image
    from app import shortcut
    monkeypatch.setattr(shortcut, 'ROOT', tmp_path)
    Image.new('RGBA', (256, 256), '#ff0000').save(tmp_path / 'csssanvas.png')
    output = prepare_icon()
    with Image.open(output) as icon:
        assert icon.getpixel((128, 128))[:3] == (255, 0, 0)


def test_desktop_has_no_web_server_import():
    entry = Path('uruchom.py').read_text()
    assert 'app.desktop' in entry
    assert 'Flask' not in Path('requirements.txt').read_text()
    for path in [Path('app/desktop.py'), Path('app/core/document.py')]:
        text = path.read_text()
        assert 'import webbrowser' not in text and 'import socket' not in text


def test_ocr_repeat_keeps_ids_and_page_identity(tmp_path, monkeypatch):
    path = tmp_path / 'blank.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.new_page()
        pdf.save(path)
    monkeypatch.setattr(ocr, 'ocr_words_with_geometry', lambda *a, **k: [
        {'text': 'AB12CD34', 'bbox': (40, 40, 140, 55), 'line': (1, 1, 1)}])
    document = Document(path)
    try:
        assert document.run_ocr() == 2
        ids = [it.id for it in document.items]
        assert len(set(ids)) == 2
        assert {it.page for it in document.items} == {0, 1}
        document.change({ids[0]: 'EF56GH78'})
        assert document.run_ocr() == 2
        assert [it.id for it in document.items] == ids
        assert document.changed[ids[0]] == 'EF56GH78'
    finally:
        document.close()


def test_expand_respects_suffix_in_same_pdf_word(pdf, tmp_path):
    path = pdf('123456;suffix')
    item = next(i for i in analyzer.analyze_document(str(path))[0] if i.value == '123456')
    with pymupdf.open(path) as doc:
        assert replacer.free_space_right(doc[0], item.rect) < 1
    out = tmp_path / 'expanded.pdf'
    replacer.apply_replacements(str(path), str(out), [(item, '11111111111')],
                                replacer.ReplaceOptions(allow_expand=True))
    with pymupdf.open(out) as doc:
        assert 'suffix' in doc[0].get_text()
