"""PrOximAl edit — native Qt Widgets. No HTTP server, browser or network API."""
from __future__ import annotations

import functools
from pathlib import Path
import sys

import pymupdf
from PySide6.QtCore import Qt, QThread, Signal, QRectF, QTimer, QUrl, QEvent
from PySide6.QtGui import QColor, QIcon, QImage, QPixmap, QPen, QAction, QKeySequence, QTransform, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QSplitter, QGraphicsView,
    QGraphicsScene, QGraphicsRectItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLineEdit, QComboBox, QCheckBox,
    QSpinBox, QDoubleSpinBox, QDialog, QFormLayout, QDialogButtonBox,
    QDateTimeEdit, QProgressBar, QToolBar, QInputDialog, QStyle, QStackedWidget,
)

from .core.document import Document
from .core.templates import TemplateLibrary, DEFAULT_FOLDER
from .home import HomePage, NewPdfDialog
from .core.randomize import randomize_items
from .core.replacer import ReplaceOptions
from .core import report, batch

ROOT = Path(__file__).resolve().parent.parent
STYLE = '''
QWidget { background: #202226; color: #dedfe2; font-size: 12px; }
QMainWindow, QStatusBar { background: #1b1d20; }
QToolBar { border: 0; border-bottom: 1px solid #45484e; spacing: 6px; padding: 7px; }
QPushButton, QToolButton, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit {
 background: #303339; border: 1px solid #535760; border-radius: 2px; padding: 5px 8px; }
QPushButton:hover, QToolButton:hover { background: #40454c; }
QPushButton:disabled, QToolButton:disabled { color: #777b83; border-color: #3b3e43; }
QLineEdit { background: #191b1e; border: 1px solid #535760; padding: 6px; }
QLineEdit:focus { border-color: #92b3d8; }
QTableWidget { background: #232529; alternate-background-color: #292c31;
 gridline-color: #393c42; selection-background-color: #3c5067; selection-color: white; }
QHeaderView::section { background: #303339; padding: 7px; border: 0; border-bottom: 1px solid #535760; }
QGraphicsView { background: #151719; border: 1px solid #45484e; }
QSplitter::handle { background: #45484e; }
QLabel#homeTitle { font-size: 26px; font-weight: 600; }
QLabel#homeSection { font-size: 15px; padding-top: 12px; }
QWidget#homeSidebar { background: #1b1d20; border-right: 1px solid #45484e; }
QLabel#brand { font-size: 20px; font-weight: 600; }
QLabel#edit { color: #a0a6af; font-size: 10px; }
QLabel#muted { color: #a9adb4; }
QPushButton#apply { background: #3d5269; border-color: #7d9cbf; }
QMenu { border: 1px solid #535760; }
QMenu::item:selected { background: #3c5067; }
QProgressBar { border: 1px solid #535760; max-height: 8px; }
QProgressBar::chunk { background: #91afd1; }
'''


def application_icon():
    for folder in (ROOT, ROOT / 'app' / 'assets'):
        for name in ('csssanvas.png', '1.png', 'proximal.ico'):
            path = folder / name
            if path.is_file():
                return QIcon(str(path))
    return QIcon(str(ROOT / 'app/assets/proximal.svg'))


def guarded(function):
    @functools.wraps(function)
    def wrapped(self, *args, **kwargs):
        try:
            return function(self, *args, **kwargs)
        except Exception as exc:
            self.error(str(exc))
    return wrapped


class Worker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.completed.emit(self.function())
        except Exception as exc:
            self.failed.emit(str(exc))


class DataBox(QGraphicsRectItem):
    def __init__(self, rect, item, callback, changed=False):
        super().__init__(rect)
        self.item_id = item.id
        self.callback = callback
        pen = QPen(QColor('#d5b772' if changed else '#568dc5'), 1.2)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QColor(90, 150, 215, 18))
        self.setToolTip(f'{item.type}: {item.value}\n{item.label}\nKliknij, aby edytować')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setZValue(1)

    def mousePressEvent(self, event):
        self.callback(self.item_id)
        event.accept()


class PdfView(QGraphicsView):
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.auto_fit = True
        self.setMinimumWidth(300)

    def fit(self):
        self.auto_fit = True
        if not self.sceneRect().isEmpty():
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def zoom(self, factor):
        self.auto_fit = False
        scale = self.transform().m11() * factor
        if .1 < scale < 8:
            self.scale(factor, factor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.auto_fit:
            self.fit()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.15 if event.angleDelta().y() > 0 else 1 / 1.15)
            event.accept()
        else:
            super().wheelEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, templates_dir=None):
        super().__init__()
        self.doc = None
        self.library = TemplateLibrary(templates_dir if templates_dir is not None else DEFAULT_FOLDER)
        self.worker = None
        self.busy = False
        self.page = 0
        self.visible_items = []
        self.boxes = []
        self.options = ReplaceOptions()
        self.created = self.modified = None
        self.setWindowTitle('PrOximAl edit')
        self.setWindowIcon(application_icon())
        self.resize(1280, 820)
        self.setMinimumSize(960, 600)
        self.setAcceptDrops(True)
        self.build_ui()
        self.refresh()
        self.render_page()
        self.show_home()

    def button(self, text, slot, parent_layout=None):
        button = QPushButton(text)
        button.clicked.connect(slot)
        if parent_layout:
            parent_layout.addWidget(button)
        return button

    def action(self, title, slot, shortcut=None):
        action = QAction(title, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        return action

    def build_ui(self):
        toolbar = QToolBar('Plik')
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        logo = QLabel()
        logo.setPixmap(application_icon().pixmap(28, 28))
        toolbar.addWidget(logo)
        brand = QLabel(' PrOximAl ')
        brand.setObjectName('brand')
        toolbar.addWidget(brand)
        small = QLabel('edit   ')
        small.setObjectName('edit')
        toolbar.addWidget(small)
        toolbar.addAction(self.action('Start / Szablony', self.show_home, 'Alt+Home'))
        toolbar.addAction(self.action('Utwórz PDF…', self.new_pdf, 'Ctrl+N'))
        self.open_action = self.action('Otwórz PDF', self.open_file, 'Ctrl+O')
        self.open_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        toolbar.addAction(self.open_action)
        self.save_action = self.action('Zapisz jako…', self.save_file, 'Ctrl+Shift+S')
        self.save_action.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        self.undo_action = self.action('Cofnij', self.undo, 'Ctrl+Z')
        self.redo_action = self.action('Ponów', self.redo, 'Ctrl+Y')
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)
        spacer = QWidget()
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        local = QLabel('Lokalnie · bez sieci  ')
        local.setObjectName('muted')
        toolbar.addWidget(local)
        tools = self.menuBar().addMenu('Narzędzia')
        self.save_template_action = self.action('Zapisz jako szablon…', self.save_template)
        tools.addAction(self.save_template_action)
        self.tool_actions = []
        for name, slot in [('Opcje podmiany…', self.settings), ('Daty zapisywanego pliku…', self.file_dates),
                           ('Eksport CSV…', lambda: self.export('csv')), ('Eksport JSON…', lambda: self.export('json')),
                           ('Zapisz mapowanie…', lambda: self.export('mapping')),
                           ('Wczytaj mapowanie…', self.import_mapping), ('Tryb wsadowy…', self.run_batch),
                           ('Raport ostatnich podmian…', self.show_report)]:
            a = self.action(name, slot)
            tools.addAction(a)
            self.tool_actions.append(a)
        help_menu = self.menuBar().addMenu('Pomoc')
        help_menu.addAction(self.action('O aplikacji', self.about))
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        root = QWidget()
        self.editor_page = root
        self.stack.addWidget(root)
        self.home = HomePage(self.library)
        self.stack.addWidget(self.home)
        self.home.open_requested.connect(self.open_file)
        self.home.new_requested.connect(self.new_pdf)
        self.home.import_requested.connect(self.import_templates)
        self.home.folder_requested.connect(self.open_templates_folder)
        self.home.template_requested.connect(self.load_path)
        self.home.resume_requested.connect(self.resume_document)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 8, 10, 8)
        self.filename = QLabel('Otwórz lub przeciągnij plik PDF do okna.')
        self.filename.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.filename)
        splitter = QSplitter()
        layout.addWidget(splitter, 1)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 6, 0)
        nav = QHBoxLayout()
        lv.addLayout(nav)
        self.prev = self.button('‹', lambda: self.set_page(self.page - 1), nav)
        self.page_spin = QSpinBox()
        self.page_spin.setPrefix('Strona ')
        self.page_spin.setRange(1, 1)
        self.page_spin.valueChanged.connect(lambda n: self.set_page(n - 1))
        nav.addWidget(self.page_spin)
        self.next = self.button('›', lambda: self.set_page(self.page + 1), nav)
        nav.addStretch()
        self.button('−', lambda: self.viewer.zoom(1 / 1.2), nav)
        self.button('+', lambda: self.viewer.zoom(1.2), nav)
        self.button('Dopasuj', lambda: self.viewer.fit(), nav)
        self.viewer = PdfView()
        lv.addWidget(self.viewer, 1)
        preview_options = QHBoxLayout()
        lv.addLayout(preview_options)
        self.box_toggle = QCheckBox('Ramki wykrytych danych')
        self.box_toggle.setChecked(True)
        self.box_toggle.toggled.connect(self.draw_boxes)
        preview_options.addWidget(self.box_toggle)
        preview_options.addStretch()
        self.result_toggle = QCheckBox('Pokaż wynik')
        self.result_toggle.toggled.connect(self.render_page)
        preview_options.addWidget(self.result_toggle)
        self.preview_note = QLabel('Ramki są wskazówką — sprawdź wykryte dane przed zapisem.')
        self.preview_note.setObjectName('muted')
        lv.addWidget(self.preview_note)
        splitter.addWidget(left)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 0, 0, 0)
        filters = QHBoxLayout()
        rv.addLayout(filters)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Szukaj wartości, typu lub opisu…')
        self.search.textChanged.connect(self.fill_table)
        filters.addWidget(self.search, 1)
        self.type_filter = QComboBox()
        self.type_filter.addItem('Wszystkie typy')
        self.type_filter.currentIndexChanged.connect(self.fill_table)
        filters.addWidget(self.type_filter)
        scope = QHBoxLayout()
        rv.addLayout(scope)
        self.page_only = QCheckBox('Tylko bieżąca strona')
        self.page_only.setChecked(True)
        self.page_only.toggled.connect(self.fill_table)
        scope.addWidget(self.page_only)
        scope.addStretch()
        self.ocr_button = self.button('OCR skanów', self.run_ocr, scope)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Str.', 'Typ / opis', 'Oryginał', 'Nowa wartość'])
        self.table.verticalHeader().hide()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.cellChanged.connect(self.cell_changed)
        self.table.itemSelectionChanged.connect(self.highlight_selection)
        rv.addWidget(self.table, 1)
        random_row = QHBoxLayout()
        rv.addLayout(random_row)
        self.random_selected = self.button('Losuj zaznaczone', lambda: self.randomize(False), random_row)
        self.random_all = self.button('Losuj widoczne', lambda: self.randomize(True), random_row)
        self.clear_button = self.button('Wyczyść zmiany', self.clear, random_row)
        note = QLabel('Dane syntetyczne. Losowanie nie gwarantuje anonimizacji.\nCtrl + klik: kilka wierszy. Dwuklik w „Nowa wartość”: edycja.')
        note.setObjectName('muted')
        rv.addWidget(note)
        splitter.addWidget(right)
        splitter.setSizes([660, 580])
        bottom = QHBoxLayout()
        layout.addLayout(bottom)
        self.stats = QLabel()
        bottom.addWidget(self.stats, 1)
        self.apply_button = self.button('Zastosuj i sprawdź', self.apply, bottom)
        self.apply_button.setObjectName('apply')
        self.save_button = self.button('Zapisz PDF jako…', self.save_file, bottom)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.statusBar().showMessage('Gotowe. Pliki nie opuszczają komputera.')

    def show_home(self):
        if self.busy:
            return
        self.home.resume_button.setVisible(self.doc is not None)
        self.stack.setCurrentWidget(self.home)
        self.home.refresh()
        self.setWindowTitle('Start — PrOximAl edit')

    def resume_document(self):
        if self.doc and not self.busy:
            self.stack.setCurrentWidget(self.editor_page)
            self.setWindowTitle(f'{self.doc.original.name} — PrOximAl edit')

    def changeEvent(self, event):
        super().changeEvent(event)
        # Files dropped into templates via Explorer appear on returning to the app.
        if (event.type() == QEvent.Type.ActivationChange and self.isActiveWindow()
                and hasattr(self, 'home') and not self.busy
                and self.stack.currentWidget() is self.home):
            self.home.refresh()

    @guarded
    def open_templates_folder(self):
        folder = self.library.ensure_folder()
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
            self.error(f'Nie można otworzyć menedżera plików. Folder: {folder}')

    def import_templates(self):
        if self.busy:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, 'Dodaj PDF-y do szablonów', '', 'PDF (*.pdf *.PDF)')
        if not paths:
            return
        def run():
            added, errors = [], []
            for path in paths:
                try:
                    added.append(self.library.import_pdf(path))
                except Exception as exc:
                    errors.append(f'{Path(path).name}: {exc}')
            return added, errors
        def finished(result):
            added, errors = result
            self.home.refresh()
            self.home.message.setText(f'Dodano szablonów: {len(added)}.' +
                                      ('\n' + '\n'.join(errors) if errors else ''))
        self.work('Dodawanie lokalnych szablonów…', run, finished)

    def new_pdf(self):
        if self.busy:
            return
        dialog = NewPdfDialog(self)
        if not dialog.exec() or not self.confirm_discard():
            return
        values = dialog.values()
        def create():
            path = self.library.create(**values)
            return Document(path)
        self.work('Tworzenie PDF i dodawanie szablonu…', create, self.loaded)

    def save_template(self):
        if not self.doc or self.busy:
            return
        if self.doc.changed and not self.doc.current_result:
            self.error('Zastosuj zmiany, zanim zapiszesz wynik jako szablon.')
            return
        name, ok = QInputDialog.getText(self, 'Zapisz jako szablon', 'Nazwa szablonu:',
                                        text=self.doc.original.stem)
        if not ok:
            return
        source = self.doc.result if self.doc.current_result else self.doc.source
        def finished(path):
            self.doc.saved = self.doc.changed.copy()
            self.home.refresh()
            self.home.message.setText(f'Zapisano szablon: {path.name}')
            self.task_message = f'Zapisano szablon: {path.name}. Znajdziesz go na ekranie Start.'
        self.work('Zapisywanie szablonu…', lambda: self.library.import_pdf(source, name), finished)

    def error(self, message):
        box = QMessageBox(QMessageBox.Icon.Warning, 'PrOximAl edit', str(message), parent=self)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.exec()

    def work(self, label, function, callback):
        if self.busy:
            return
        self.busy = True
        self.task_message = 'Gotowe.'
        self.centralWidget().setEnabled(False)
        self.menuBar().setEnabled(False)
        for bar in self.findChildren(QToolBar):
            bar.setEnabled(False)
        self.progress.show()
        self.statusBar().showMessage(label)
        worker = Worker(function, self)
        self.worker = worker
        worker.completed.connect(callback)
        worker.failed.connect(self.error)
        worker.finished.connect(self.work_finished)
        worker.start()

    def work_finished(self):
        self.busy = False
        self.centralWidget().setEnabled(True)
        self.menuBar().setEnabled(True)
        for bar in self.findChildren(QToolBar):
            bar.setEnabled(True)
        self.progress.hide()
        self.worker.deleteLater()
        self.worker = None
        self.refresh()
        self.statusBar().showMessage(self.task_message)

    def confirm_discard(self):
        return not (self.doc and self.doc.dirty) or QMessageBox.question(
            self, 'Niezapisane zmiany', 'Porzucić niezapisane zmiany?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def open_file(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Otwórz PDF', '', 'PDF (*.pdf)')
        if path:
            self.load_path(path)

    def load_path(self, path):
        if self.busy or not self.confirm_discard():
            return
        self.work('Analiza dokumentu…', lambda: Document(path), self.loaded)

    def loaded(self, document):
        if self.doc:
            self.doc.close()
        self.doc = document
        self.stack.setCurrentWidget(self.editor_page)
        self.page = 0
        self.created = self.modified = None
        self.search.clear()
        self.result_toggle.setChecked(False)
        self.page_spin.setRange(1, document.pages)
        self.page_spin.setValue(1)
        self.page_spin.setSuffix(f' / {document.pages}')
        self.rebuild_types()
        self.filename.setText(f'{document.original.name}  ·  {document.pages} str.  ·  {len(document.empty_pages)} str. bez tekstu')
        self.setWindowTitle(f'{document.original.name} — PrOximAl edit')
        self.refresh()
        self.render_page()
        self.viewer.fit()

    def rebuild_types(self):
        self.type_filter.blockSignals(True)
        self.type_filter.clear()
        self.type_filter.addItem('Wszystkie typy')
        if self.doc:
            self.type_filter.addItems(sorted({it.type for it in self.doc.items}))
        self.type_filter.blockSignals(False)

    def set_page(self, page):
        if not self.doc or self.busy:
            return
        self.page = max(0, min(page, self.doc.pages - 1))
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(self.page + 1)
        self.page_spin.blockSignals(False)
        self.refresh()
        self.render_page()

    @guarded
    def render_page(self, *_):
        self.viewer.scene().clear()
        self.boxes = []
        if not self.doc:
            self.viewer.scene().addText('Otwórz PDF  ·  Ctrl+O').setDefaultTextColor(QColor('#a9adb4'))
            return
        path = self.doc.result if self.result_toggle.isChecked() and self.doc.current_result else self.doc.source
        with pymupdf.open(path) as pdf:
            page = pdf[self.page]
            scale = min(1.7, 2400 / max(page.rect.width, page.rect.height))
            pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            picture = self.viewer.scene().addPixmap(QPixmap.fromImage(image))
            # The scene is in PDF points, not screen pixels. PDF rotation is
            # applied to boxes too; view zoom/DPI scales both together.
            picture.setTransform(QTransform.fromScale(
                page.rect.width / pix.width, page.rect.height / pix.height))
            self.rotation_matrix = page.rotation_matrix
            self.viewer.setSceneRect(0, 0, page.rect.width, page.rect.height)
        self.draw_boxes()
        if self.viewer.auto_fit:
            self.viewer.fit()

    def draw_boxes(self, *_):
        for box in self.boxes:
            self.viewer.scene().removeItem(box)
        self.boxes = []
        result = self.result_toggle.isChecked() and self.doc and self.doc.current_result
        self.preview_note.setText('Wynik: ramki ukryte, aby nie sugerować starego położenia tekstu.' if result else
                                  'Oryginał: kliknij ramkę, aby przejść do wartości.')
        if not self.doc or not self.box_toggle.isChecked() or result or not hasattr(self, 'rotation_matrix'):
            return
        for item in self.filtered_items():
            if item.page != self.page:
                continue
            rect = pymupdf.Rect(item.rect) * self.rotation_matrix
            box = DataBox(QRectF(rect.x0, rect.y0, rect.width, rect.height), item,
                          self.select_item, item.id in self.doc.changed)
            self.viewer.scene().addItem(box)
            self.boxes.append(box)

    def filtered_items(self):
        if not self.doc:
            return []
        query = self.search.text().casefold().strip()
        typ = self.type_filter.currentText() if self.type_filter.currentIndex() > 0 else ''
        return [it for it in self.doc.items if
                (not self.page_only.isChecked() or it.page == self.page) and
                (not typ or it.type == typ) and
                (not query or query in f'{it.value} {it.type} {it.label}'.casefold())]

    def fill_table(self, *_):
        self.visible_items = self.filtered_items()
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.visible_items))
        for row, it in enumerate(self.visible_items):
            for col, text in enumerate((str(it.page + 1), it.type, it.value, self.doc.changed.get(it.id, ''))):
                cell = QTableWidgetItem(text)
                if col != 3:
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                cell.setToolTip(f'{it.label}\n{it.font_desc}\nPewność: {it.score:.0%}' +
                                ('\nOCR: zweryfikuj tekst i położenie.' if it.source == 'ocr' else ''))
                if col == 3 and text:
                    cell.setForeground(QColor('#e3c383'))
                self.table.setItem(row, col, cell)
        self.table.blockSignals(False)
        self.draw_boxes()

    def selected_items(self):
        return [self.visible_items[index.row()] for index in self.table.selectionModel().selectedRows()]

    def select_item(self, item_id):
        for row, item in enumerate(self.visible_items):
            if item.id == item_id:
                self.table.setCurrentCell(row, 3)
                self.table.scrollToItem(self.table.item(row, 3))
                self.table.editItem(self.table.item(row, 3))
                break

    def highlight_selection(self):
        ids = {it.id for it in self.selected_items()}
        for box in self.boxes:
            box.setBrush(QColor(90, 150, 215, 65 if box.item_id in ids else 18))

    def cell_changed(self, row, col):
        if col != 3 or not self.doc:
            return
        values = self.doc.changed.copy()
        values[self.visible_items[row].id] = self.table.item(row, col).text()
        self.doc.change(values)
        self.refresh(refill=False)

    def refresh(self, refill=True):
        doc = self.doc
        self.prev.setEnabled(bool(doc and self.page > 0))
        self.next.setEnabled(bool(doc and self.page < doc.pages - 1))
        self.page_spin.setEnabled(bool(doc))
        self.apply_button.setEnabled(bool(doc))
        self.save_template_action.setEnabled(bool(doc and (not doc.changed or doc.current_result)))
        can_save = bool(doc and doc.current_result)
        self.save_action.setEnabled(can_save)
        self.save_button.setEnabled(can_save)
        self.result_toggle.setEnabled(can_save)
        if not can_save and self.result_toggle.isChecked():
            self.result_toggle.setChecked(False)
        self.undo_action.setEnabled(bool(doc and doc.history))
        self.redo_action.setEnabled(bool(doc and doc.redo_history))
        self.ocr_button.setEnabled(bool(doc and doc.empty_pages))
        for button in (self.random_selected, self.random_all, self.clear_button):
            button.setEnabled(bool(doc and doc.items))
        self.stats.setText(f'{len(doc.items)} wykrytych  ·  {len(doc.changed)} zmian' +
                           ('  ·  zastosuj ponownie, aby zapisać' if doc.changed and not can_save else '')
                           if doc else 'Brak dokumentu')
        if refill:
            self.fill_table()
        else:
            self.draw_boxes()

    @guarded
    def randomize(self, all_visible):
        if not self.doc:
            return
        items = self.visible_items if all_visible else self.selected_items()
        if not items:
            self.statusBar().showMessage('Zaznacz wiersze do losowania.')
            return
        values = self.doc.changed.copy()
        values.update(randomize_items(items))
        self.doc.change(values)
        self.refresh()

    def undo(self):
        if self.doc and not self.busy:
            self.doc.undo()
            self.refresh()

    def redo(self):
        if self.doc and not self.busy:
            self.doc.redo()
            self.refresh()

    def clear(self):
        if self.doc:
            self.doc.change({})
            self.refresh()

    def apply(self):
        if self.doc:
            self.work('Podmiana danych…', lambda: self.doc.apply(self.options), self.applied)

    def applied(self, reports):
        self.refresh()
        self.result_toggle.setChecked(True)
        self.render_page()
        failed = [r for r in reports if not r['status'].startswith('ok')]
        if failed:
            self.error(f'{len(failed)} zmian nie zostało wykonanych. Oryginalne wartości pozostawiono.\n'
                       'Sprawdź Narzędzia → Raport ostatnich podmian. Skróć tekst lub zmień opcje.')

    @guarded
    def save_file(self):
        if not self.doc or not self.doc.current_result or self.busy:
            return
        default = self.doc.original.with_name(self.doc.original.stem + '_PrOximAl.pdf')
        path, _ = QFileDialog.getSaveFileName(self, 'Zapisz wynik PDF', str(default), 'PDF (*.pdf)')
        if path:
            if not path.lower().endswith('.pdf'):
                path += '.pdf'
            self.doc.save(path, self.created, self.modified)
            self.statusBar().showMessage(f'Zapisano: {path}')

    def run_ocr(self):
        if not self.doc:
            return
        lang, ok = QInputDialog.getItem(self, 'OCR lokalnie', 'Język (wymaga Tesseract):', ['pol', 'eng'], 0, False)
        if ok:
            self.work('OCR — rozpoznawanie skanów…', lambda: self.doc.run_ocr(lang), self.ocr_finished)

    def ocr_finished(self, count):
        self.rebuild_types()
        self.refresh()
        self.error(f'OCR wykrył {count} elementów. Sprawdź rozpoznany tekst i podgląd przed zapisem.')

    def settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Opcje podmiany')
        form = QFormLayout(dialog)
        minimum = QDoubleSpinBox()
        minimum.setRange(2, 24)
        minimum.setValue(self.options.min_font_size)
        form.addRow('Minimalna czcionka (pt)', minimum)
        expand = QCheckBox('Pozwól wykorzystać wolne miejsce po prawej')
        expand.setChecked(self.options.allow_expand)
        form.addRow(expand)
        embedded = QCheckBox('Używaj osadzonej czcionki, jeśli zawiera nowe znaki')
        embedded.setChecked(self.options.use_embedded_fonts)
        form.addRow(embedded)
        fill = QComboBox()
        fill.addItems(['auto', 'white', 'none'])
        fill.setCurrentText(self.options.fill_mode)
        form.addRow('Tło: auto / białe / bez wypełnienia', fill)
        note = QLabel('Za długi tekst zostanie pominięty, a nie nałożony na sąsiadów.')
        form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            self.options = ReplaceOptions(minimum.value(), expand.isChecked(), fill.currentText(),
                                          use_embedded_fonts=embedded.isChecked())
            if self.doc:
                self.doc.applied = None
                self.refresh()

    def file_dates(self):
        from PySide6.QtCore import QDateTime
        dialog = QDialog(self)
        dialog.setWindowTitle('Daty zapisywanego pliku')
        form = QFormLayout(dialog)
        controls = []
        for title, date in [('Utworzenie', self.created), ('Modyfikacja', self.modified)]:
            check = QCheckBox(title)
            check.setChecked(date is not None)
            editor = QDateTimeEdit(QDateTime(date) if date else QDateTime.currentDateTime())
            editor.setCalendarPopup(True)
            editor.setDisplayFormat('yyyy-MM-dd HH:mm:ss')
            editor.setEnabled(check.isChecked())
            check.toggled.connect(editor.setEnabled)
            form.addRow(check, editor)
            controls.append((check, editor))
        form.addRow(QLabel('Dotyczy eksportu, nigdy oryginału.\nData utworzenia pliku systemowego: tylko Windows.'))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            self.created, self.modified = [e.dateTime().toPython() if c.isChecked() else None for c, e in controls]

    @guarded
    def export(self, kind):
        if not self.doc:
            return
        ext = 'json' if kind == 'mapping' else kind
        path, _ = QFileDialog.getSaveFileName(self, 'Eksport danych', f'PrOximAl_{kind}.{ext}', f'{ext.upper()} (*.{ext})')
        if path:
            if not path.lower().endswith('.' + ext):
                path += '.' + ext
            if kind == 'mapping':
                report.export_mapping(path, self.doc.items)
            else:
                report.export_report(path, self.doc.items, self.doc.reports)
            self.statusBar().showMessage(f'Zapisano: {path}')

    @guarded
    def import_mapping(self):
        if not self.doc:
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Wczytaj mapowanie', '', 'JSON (*.json)')
        if path:
            jobs = batch._match_items(self.doc.items, report.import_mapping(path))
            self.doc.change({**self.doc.changed, **{it.id: value for it, value in jobs}})
            self.refresh()

    def run_batch(self):
        mapping, _ = QFileDialog.getOpenFileName(self, 'Wybierz mapowanie', '', 'JSON (*.json)')
        if not mapping:
            return
        files, _ = QFileDialog.getOpenFileNames(self, 'Wybierz PDF-y', '', 'PDF (*.pdf)')
        if not files:
            return
        output = QFileDialog.getExistingDirectory(self, 'Folder wyników')
        if not output:
            return
        def run():
            changes = report.import_mapping(mapping)
            results = []
            for file in files:
                document = None
                try:
                    document = Document(file)
                    jobs = batch._match_items(document.items, changes)
                    document.change({it.id: value for it, value in jobs})
                    reps = document.apply(self.options)
                    target = Path(output) / (Path(file).stem + '_PrOximAl.pdf')
                    index = 2
                    while target.exists():
                        target = Path(output) / (Path(file).stem + f'_PrOximAl_{index}.pdf')
                        index += 1
                    document.save(target, self.created, self.modified)
                    ok = sum(r['status'].startswith('ok') for r in reps)
                    results.append(f'{Path(file).name}: {ok}/{len(jobs)} zmian → {target.name}')
                except Exception as exc:
                    results.append(f'{Path(file).name}: BŁĄD: {exc}')
                finally:
                    if document:
                        document.close()
            return '\n'.join(results)
        self.work('Przetwarzanie plików…', run, self.error)

    def show_report(self):
        if not self.doc or not self.doc.reports:
            self.error('Brak raportu. Najpierw zastosuj zmiany.')
            return
        from PySide6.QtWidgets import QPlainTextEdit
        dialog = QDialog(self)
        dialog.setWindowTitle('Raport podmian')
        dialog.resize(720, 480)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText('\n\n'.join(f'Strona {r["page"] + 1}: {r["old"]} → {r["new"]}\n{r["status"]}' for r in self.doc.reports))
        layout.addWidget(text)
        dialog.exec()

    def about(self):
        self.error('PrOximAl edit\nLokalny edytor danych PDF. Bez przeglądarki i bez serwera.\n\n'
                   'Otwórz PDF, edytuj lub losuj wartości, zastosuj i zapisz kopię.\n'
                   'OCR jest przybliżony. Losowanie nie jest pełną anonimizacją dokumentu.\n'
                   'Zmiany mogą unieważnić podpisy cyfrowe PDF.\n\n'
                   'Skróty: Ctrl+O, Ctrl+Shift+S, Ctrl+Z, Ctrl+Y, Ctrl+kółko myszy.')

    def dragEnterEvent(self, event):
        if not self.busy and event.mimeData().hasUrls() and any(
                u.isLocalFile() and u.toLocalFile().lower().endswith('.pdf') for u in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith('.pdf'):
                self.load_path(url.toLocalFile())
                break

    def closeEvent(self, event):
        if self.busy:
            self.statusBar().showMessage('Poczekaj na zakończenie operacji przed zamknięciem.')
            event.ignore()
        elif self.confirm_discard():
            if self.doc:
                self.doc.close()
            event.accept()
        else:
            event.ignore()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('PrOximAl')
    app.setOrganizationName('PrOximAl')
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    app.setWindowIcon(application_icon())
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith('.pdf'):
        QTimer.singleShot(0, lambda: window.load_path(sys.argv[1]))
    sys.exit(app.exec())
