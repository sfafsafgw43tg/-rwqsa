"""Template folder and PDF creation tests, independent of the desktop runtime."""
from pathlib import Path
import sys

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.templates import TemplateLibrary, PAGE_SIZES
from app.core.document import Document


@pytest.fixture
def library(tmp_path):
    return TemplateLibrary(tmp_path / 'templates')


def test_empty_folder_is_created(library):
    assert library.list() == []
    assert library.folder.is_dir()


@pytest.mark.parametrize('size', list(PAGE_SIZES))
@pytest.mark.parametrize('landscape', [False, True])
def test_new_blank_pdf_geometry(library, size, landscape):
    path = library.create('Pusty', page_size=size, landscape=landscape, pages=3)
    expected = PAGE_SIZES[size][::-1] if landscape else PAGE_SIZES[size]
    with pymupdf.open(path) as doc:
        assert len(doc) == 3
        assert not doc[0].get_text().strip()
        assert (doc[0].rect.width, doc[0].rect.height) == pytest.approx(expected, abs=.01)
    entries = library.list()
    assert len(entries) == 1
    assert entries[0].name == 'Pusty.pdf'
    assert entries[0].size > 0


def test_new_template_with_polish_content_and_literal_html(library):
    path = library.create('Zażółć', title='Żółć i łąka', text='Numer: AB12CD34\nImię: Łukasz\n<script>test</script>')
    with pymupdf.open(path) as pdf:
        text = pdf[0].get_text()
        assert 'Żółć i łąka' in text
        assert 'Łukasz' in text
        assert '<script>test</script>' in text
        assert 'AB12CD34' in text
    document = Document(path)
    try:
        assert any(i.value == 'AB12CD34' for i in document.items)
    finally:
        document.close()


def test_overflow_does_not_publish_partial_pdf(library):
    with pytest.raises(ValueError, match='nie mieści'):
        library.create('Too long', page_size='A5', text='Test zdania.\n' * 600)
    assert library.list() == []


def test_import_casefold_collisions_never_overwrite(library, tmp_path):
    source = tmp_path / 'invoice.pdf'
    with pymupdf.open() as doc:
        doc.new_page().insert_text((40, 60), 'Original 123456')
        doc.save(source)
    before = source.read_bytes()
    first = library.import_pdf(source)
    second = library.import_pdf(source, 'INVOICE.PDF')
    third = library.import_pdf(source)
    assert first.name == 'invoice.pdf'
    assert second.name == 'INVOICE (2).pdf'
    assert third.name == 'invoice (3).pdf'
    assert first.read_bytes() == before == second.read_bytes() == source.read_bytes()


def test_manual_files_subfolders_and_removed_files(library):
    path = library.create('zebra')
    sub = library.folder / 'Umowy'
    sub.mkdir()
    moved = sub / 'umowa.PDF'
    path.rename(moved)
    (library.folder / 'readme.txt').write_text('Not a PDF')
    (library.folder / 'folder.pdf').mkdir()
    assert [e.name for e in library.list()] == ['Umowy/umowa.PDF']
    moved.unlink()
    assert library.list() == []


def test_template_working_copy_not_changed(library, tmp_path):
    path = library.create('Szablon', text='Numer: AB12CD34')
    before = path.read_bytes()
    doc = Document(path)
    try:
        item = next(i for i in doc.items if i.value == 'AB12CD34')
        doc.change({item.id: 'CD34EF56'})
        doc.apply()
        output = tmp_path / 'result.pdf'
        doc.save(output)
        with pytest.raises(ValueError):
            doc.save(path)
        new_template = library.import_pdf(doc.result, 'Nowy wzór')
        assert path.read_bytes() == before
        with pymupdf.open(new_template) as pdf:
            assert 'CD34EF56' in pdf[0].get_text()
    finally:
        doc.close()


@pytest.mark.parametrize('name', ['', '   ', '...'])
def test_empty_names_rejected(library, name):
    with pytest.raises(ValueError):
        library.create(name)


@pytest.mark.parametrize('name', ['../../escape', 'CON', 'aux.pdf', 'Umowa: wzór?'])
def test_names_are_safe_and_windows_compatible(library, name):
    path = library.create(name)
    assert path.parent == library.folder
    assert not any(c in path.name for c in ':?*/\\')
    assert path.stem.upper() not in ('CON', 'AUX')


def test_invalid_and_password_protected_import(library, tmp_path):
    bad = tmp_path / 'bad.pdf'
    bad.write_bytes(b'not a pdf')
    with pytest.raises(Exception):
        library.import_pdf(bad)
    encrypted = tmp_path / 'secret.pdf'
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(encrypted, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='secret')
    with pytest.raises(ValueError, match='hasłem'):
        library.import_pdf(encrypted)
    assert library.list() == []


@pytest.mark.parametrize('options', [{'pages': 0}, {'pages': 101}, {'page_size': 'bad'}])
def test_invalid_creation_options(library, options):
    with pytest.raises(ValueError):
        library.create('Bad', **options)
    assert library.list() == []
