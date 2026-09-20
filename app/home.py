"""Native start screen and new-PDF dialog; no web content or online templates."""
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QFormLayout, QComboBox, QSpinBox, QPlainTextEdit, QDialogButtonBox,
)
from .core.templates import PAGE_SIZES


class HomePage(QWidget):
    open_requested = Signal()
    new_requested = Signal()
    import_requested = Signal()
    folder_requested = Signal()
    resume_requested = Signal()
    template_requested = Signal(str)

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library
        self.entries = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        sidebar = QWidget()
        sidebar.setObjectName('homeSidebar')
        sidebar.setFixedWidth(220)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(18, 24, 18, 24)
        label = QLabel('OBSZAR ROBOCZY')
        label.setObjectName('muted')
        left.addWidget(label)
        heading = QLabel('Start / Szablony')
        heading.setObjectName('homeSection')
        left.addWidget(heading)
        left.addSpacing(24)
        self.new_button = self.button('Utwórz PDF…', self.new_requested.emit, left)
        self.new_button.setObjectName('apply')
        self.button('Otwórz plik…', self.open_requested.emit, left)
        self.resume_button = self.button('Wróć do dokumentu', self.resume_requested.emit, left)
        self.resume_button.hide()
        left.addSpacing(24)
        self.button('Dodaj szablony…', self.import_requested.emit, left)
        self.button('Otwórz folder', self.folder_requested.emit, left)
        left.addStretch()
        note = QLabel('Tylko na tym komputerze.\nBez konta. Bez chmury.')
        note.setObjectName('muted')
        left.addWidget(note)
        layout.addWidget(sidebar)
        content = QWidget()
        right = QVBoxLayout(content)
        right.setContentsMargins(32, 28, 32, 24)
        title = QLabel('Od czego zaczynamy?')
        title.setObjectName('homeTitle')
        right.addWidget(title)
        subtitle = QLabel('Wybierz szablon, otwórz własny plik lub utwórz nowy PDF.')
        subtitle.setObjectName('muted')
        right.addWidget(subtitle)
        right.addSpacing(24)
        row = QHBoxLayout()
        row.addWidget(QLabel('Twoje szablony'), 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Szukaj szablonu…')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.fill_table)
        row.addWidget(self.search)
        self.button('Odśwież', self.refresh, row)
        right.addLayout(row)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['Nazwa PDF', 'Zmodyfikowano', 'Rozmiar'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.cellDoubleClicked.connect(lambda *_: self.open_selected())
        right.addWidget(self.table, 1)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        right.addWidget(self.message)
        bottom = QHBoxLayout()
        self.count = QLabel()
        self.count.setObjectName('muted')
        bottom.addWidget(self.count, 1)
        self.use_button = self.button('Użyj szablonu', self.open_selected, bottom)
        self.use_button.setEnabled(False)
        right.addLayout(bottom)
        hint = QLabel('Włóż PDF-y do folderu templates — pojawią się tutaj.\n'
                      'Pracujesz na kopii; plik szablonu pozostaje bez zmian.')
        hint.setObjectName('muted')
        right.addWidget(hint)
        self.folder_label = QLabel(str(library.folder))
        self.folder_label.setTextFormat(Qt.TextFormat.PlainText)
        self.folder_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.folder_label.setWordWrap(True)
        self.folder_label.setObjectName('muted')
        right.addWidget(self.folder_label)
        layout.addWidget(content, 1)

    @staticmethod
    def button(text, callback, layout):
        button = QPushButton(text)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def refresh(self):
        try:
            self.entries = self.library.list()
            self.message.setText('' if self.entries else
                                 'Brak szablonów. Dodaj PDF do folderu lub wybierz „Utwórz PDF…”.')
        except OSError as exc:
            self.entries = []
            self.message.setText(f'Nie można odczytać folderu szablonów: {exc}')
        self.fill_table()

    def fill_table(self, *_):
        current = self.table.currentRow()
        previous = self.table.item(current, 0) if current >= 0 else None
        selected = previous.data(Qt.ItemDataRole.UserRole) if previous else None
        query = self.search.text().strip().casefold()
        entries = [entry for entry in self.entries if query in entry.name.casefold()]
        self.table.setRowCount(0)
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            for col, text in enumerate((entry.name, datetime.fromtimestamp(entry.modified).strftime('%d.%m.%Y %H:%M'),
                                        f'{max(1, round(entry.size / 1024))} KB')):
                item = QTableWidgetItem(text)
                item.setToolTip(str(entry.path))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, str(entry.path))
                self.table.setItem(row, col, item)
            if selected == str(entry.path):
                self.table.selectRow(row)
        self.count.setText(f'{len(entries)} / {len(self.entries)} szablonów')
        self.selection_changed()

    def selection_changed(self):
        self.use_button.setEnabled(bool(self.table.selectionModel().selectedRows()))

    def open_selected(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            item = self.table.item(rows[0].row(), 0)
            self.template_requested.emit(item.data(Qt.ItemDataRole.UserRole))

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()


class NewPdfDialog(QDialog):
    """A deliberately small creator, not a full page-layout editor."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Utwórz PDF / nowy szablon')
        self.resize(560, 560)
        form = QFormLayout(self)
        self.name = QLineEdit('Nowy szablon')
        self.size = QComboBox()
        self.size.addItems(list(PAGE_SIZES))
        self.orientation = QComboBox()
        self.orientation.addItems(['Pionowa', 'Pozioma'])
        self.pages = QSpinBox()
        self.pages.setRange(1, 100)
        self.title = QLineEdit()
        self.title.setPlaceholderText('Opcjonalny nagłówek pierwszej strony')
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText('Opcjonalna treść, np.\nImię i nazwisko: Jan Kowalski\nNumer: AB12CD34\nData: 15.01.2024')
        self.text.setMinimumHeight(160)
        for label, widget in [('Nazwa pliku', self.name), ('Format', self.size), ('Orientacja', self.orientation),
                              ('Liczba stron', self.pages), ('Nagłówek', self.title), ('Treść', self.text)]:
            form.addRow(label, widget)
        note = QLabel('PDF zostanie zapisany w templates i otwarty jako kopia do pracy.\n'
                      'Treść trafia na pierwszą stronę; pozostałe strony są puste.\n'
                      'Puste pola tworzą pusty PDF. To prosty kreator, nie edytor układu.')
        note.setWordWrap(True)
        note.setObjectName('muted')
        form.addRow(note)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Utwórz i otwórz')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.name.textChanged.connect(lambda value: self.buttons.button(
            QDialogButtonBox.StandardButton.Ok).setEnabled(bool(value.strip())))
        form.addRow(self.buttons)

    def values(self):
        return dict(name=self.name.text(), page_size=self.size.currentText(),
                    landscape=self.orientation.currentIndex() == 1, pages=self.pages.value(),
                    title=self.title.text(), text=self.text.toPlainText())
