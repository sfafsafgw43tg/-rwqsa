"""Desktop document state: private working copy, undo and safe local export."""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import tempfile

import pymupdf
from . import analyzer, replacer, ocr, filedates


class Document:
    def __init__(self, path):
        self.original = Path(path).resolve()
        self._temp = tempfile.TemporaryDirectory(prefix='proximal-')
        self.source = Path(self._temp.name) / 'source.pdf'
        self.result = Path(self._temp.name) / 'result.pdf'
        try:
            shutil.copyfile(self.original, self.source)
            self.items, self.empty_pages = analyzer.analyze_document(str(self.source))
            with pymupdf.open(self.source) as pdf:
                self.pages = len(pdf)
        except Exception:
            self.close()
            raise
        self.changed = {}
        self.history = []
        self.redo_history = []
        self.applied = None
        self.saved = {}
        self.reports = []

    @property
    def current_result(self):
        return self.applied == self.changed and self.result.exists()

    @property
    def dirty(self):
        return self.changed != self.saved

    def change(self, values):
        items = {it.id: it for it in self.items}
        clean = {k: v for k, v in values.items() if k in items and v and v != items[k].value}
        if clean == self.changed:
            return
        self.history.append(self.changed.copy())
        self.redo_history.clear()
        self.changed = clean
        self.sync_items()

    def sync_items(self):
        for item in self.items:
            item.new_value = self.changed.get(item.id, '')

    def undo(self):
        if self.history:
            self.redo_history.append(self.changed.copy())
            self.changed = self.history.pop()
            self.sync_items()

    def redo(self):
        if self.redo_history:
            self.history.append(self.changed.copy())
            self.changed = self.redo_history.pop()
            self.sync_items()

    def apply(self, options=None):
        jobs = [(it, self.changed[it.id]) for it in self.items if it.id in self.changed]
        self.reports = replacer.apply_replacements(str(self.source), str(self.result), jobs, options)
        self.applied = self.changed.copy()
        return self.reports

    def run_ocr(self, lang='pol'):
        additions = []
        with pymupdf.open(self.source) as pdf:
            for page in self.empty_pages:
                additions.extend(analyzer.analyze_lines(ocr.ocr_page_lines(pdf[page], lang),
                                                        page_no=page, ocr=True))
        # Keep IDs for unchanged detections, so re-running OCR is idempotent.
        def key(item):
            return (item.page, item.type, item.value, tuple(round(x, 2) for x in item.rect))
        old_ids = {key(it): it.id for it in self.items if it.source == 'ocr'}
        for item in additions:
            item.id = old_ids.get(key(item), item.id)
        # Replace previously detected OCR data, never mix positions from pages.
        self.items = [it for it in self.items if it.source != 'ocr'] + additions
        self.items.sort(key=lambda it: (it.page, it.rect[1], it.rect[0]))
        valid = {it.id for it in self.items}
        self.changed = {k: v for k, v in self.changed.items() if k in valid}
        self.history = [{k: v for k, v in snapshot.items() if k in valid} for snapshot in self.history]
        self.redo_history = [{k: v for k, v in snapshot.items() if k in valid} for snapshot in self.redo_history]
        self.sync_items()
        return len(additions)

    def save(self, path, created=None, modified=None):
        path = Path(path).resolve()
        if path == self.original or (path.exists() and os.path.samefile(path, self.original)):
            raise ValueError('Nie nadpisuj oryginału. Wybierz inną nazwę pliku.')
        if not self.current_result:
            raise ValueError('Najpierw zastosuj aktualne zmiany i sprawdź podgląd.')
        fd, name = tempfile.mkstemp(suffix='.pdf', dir=path.parent)
        os.close(fd)
        try:
            shutil.copyfile(self.result, name)
            if created or modified:
                filedates.set_pdf_dates(name, creation=created, modification=modified)
                filedates.set_file_times(name, created=created, modified=modified, accessed=modified)
            os.replace(name, path)
            self.saved = self.changed.copy()
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def close(self):
        self._temp.cleanup()
