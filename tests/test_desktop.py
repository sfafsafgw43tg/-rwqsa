"""Native Qt integration tests; QT_QPA_PLATFORM=offscreen needs Qt system libs."""
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
import pymupdf

try:
    from PySide6.QtWidgets import QApplication
except ImportError as exc:
    if os.environ.get('PROXIMAL_REQUIRE_GUI_TESTS') == '1':
        raise
    pytest.skip(f'Qt system libraries unavailable: {exc}', allow_module_level=True)

from app.desktop import MainWindow, STYLE
from app.core.document import Document


@pytest.fixture(scope='module')
def app():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    return app


@pytest.fixture
def window(app, tmp_path):
    path = tmp_path / 'source.pdf'
    with pymupdf.open() as doc:
        for rotation in (0, 90):
            page = doc.new_page(width=600, height=800)
            page.insert_text((40, 60), 'Numer: AB12CD34')
            page.set_rotation(rotation)
        doc.save(path)
    window = MainWindow(templates_dir=tmp_path / 'templates')
    window.error = lambda message: pytest.fail(str(message))
    window.show()
    window.loaded(Document(path))
    app.processEvents()
    yield window
    window.doc.saved = window.doc.changed.copy()
    window.close()
    app.processEvents()


def test_native_window_table_boxes(window, app):
    assert window.windowTitle().endswith('PrOximAl edit')
    assert window.table.rowCount() == 2
    assert len(window.boxes) == 2
    box = window.boxes[0].rect()
    rect = window.visible_items[0].rect
    assert (box.x(), box.y(), box.right(), box.bottom()) == pytest.approx(rect)
    window.viewer.zoom(1.5)
    assert window.boxes[0].rect() == box
    window.resize(1000, 680)
    app.processEvents()
    assert window.boxes[0].rect() == box


def test_rotated_page_and_filter(window, app):
    window.set_page(1)
    assert window.page == 1
    assert window.visible_items[0].page == 1
    rect = pymupdf.Rect(window.visible_items[0].rect) * window.rotation_matrix
    box = window.boxes[0].rect()
    assert (box.x(), box.y(), box.right(), box.bottom()) == pytest.approx(tuple(rect))
    window.search.setText('missing')
    assert window.table.rowCount() == 0
    assert not window.boxes
    window.search.clear()
    window.page_only.setChecked(False)
    assert window.table.rowCount() == 4


def test_edit_randomize_undo_apply_export(window, app, tmp_path):
    window.table.item(0, 3).setText('EF56GH78')
    item = window.visible_items[0]
    assert window.doc.changed[item.id] == 'EF56GH78'
    window.table.selectRow(0)
    window.randomize(False)
    assert window.doc.changed[item.id] != 'AB12CD34'
    window.undo()
    assert window.doc.changed[item.id] == 'EF56GH78'
    window.redo()
    window.apply()
    deadline = time.monotonic() + 20
    while window.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert not window.busy
    assert window.doc.current_result
    assert window.result_toggle.isChecked()
    assert not window.boxes  # never draw original geometry on changed text
    output = tmp_path / 'saved.pdf'
    window.doc.save(output)
    with pymupdf.open(output) as doc:
        assert window.doc.changed[item.id] in doc[0].get_text()
    window.clear()
    assert not window.save_button.isEnabled()
    assert not window.result_toggle.isChecked()
    assert window.boxes


def test_open_worker(window, app, tmp_path):
    window.load_path(window.doc.original)
    deadline = time.monotonic() + 20
    while window.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert not window.busy
    assert window.page == 0
    assert window.page_spin.value() == 1
    assert window.table.rowCount() == 2


def test_start_library_selection_and_resume(window, app):
    original = window.doc
    first = window.library.create('Umowa', text='Numer: AB12CD34')
    window.library.create('Faktura')
    window.show_home()
    assert window.stack.currentWidget() is window.home
    assert window.home.table.rowCount() == 2
    assert window.home.resume_button.isVisible()
    window.home.search.setText('umowa')
    assert window.home.table.rowCount() == 1
    window.resume_document()
    assert window.doc is original
    assert window.stack.currentWidget() is window.editor_page
    window.show_home()
    window.home.table.selectRow(0)
    assert window.home.use_button.isEnabled()
    window.home.open_selected()
    deadline = time.monotonic() + 20
    while window.busy and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert not window.busy
    assert window.doc.original == first
    assert window.stack.currentWidget() is window.editor_page


def test_start_without_document_and_creator(app, tmp_path):
    from app.home import NewPdfDialog
    window = MainWindow(templates_dir=tmp_path / 'templates')
    try:
        window.show()
        app.processEvents()
        assert window.stack.currentWidget() is window.home
        assert window.home.table.rowCount() == 0
        assert not window.save_template_action.isEnabled()
        assert not window.home.resume_button.isVisible()
        dialog = NewPdfDialog(window)
        values = dialog.values()
        assert values['page_size'] == 'A4' and values['pages'] == 1
        dialog.text.setPlainText('Numer: ABC123')
        path = window.library.create(**dialog.values())
        window.home.refresh()
        assert window.home.table.rowCount() == 1
        assert path.exists()
        dialog.close()
    finally:
        window.close()
        app.processEvents()


def test_full_text_category_sort_and_edit_identity(window, app):
    assert window.sort_mode.currentData() == 'type'
    assert [it.type for it in window.visible_items] == ['symbol', 'etykieta']
    ids = {it.id for it in window.visible_items}
    window.sort_mode.setCurrentIndex(window.sort_mode.findData('position'))
    assert window.visible_items[0].value == 'Numer:'
    window.table.item(0, 3).setText('Kod:')
    assert window.doc.changed[window.visible_items[0].id] == 'Kod:'
    window.sort_mode.setCurrentIndex(window.sort_mode.findData('type'))
    assert window.visible_items[1].value == 'Numer:'
    assert window.table.item(1, 3).text() == 'Kod:'
    assert {it.id for it in window.visible_items} == ids
    window.type_filter.setCurrentText('etykieta')
    assert window.table.rowCount() == 1
    assert len(window.boxes) == 1
    window.clear()
    window.randomize(True)
    assert not window.doc.changed  # bulk randomization never corrupts labels
