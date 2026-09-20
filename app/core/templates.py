"""Local PDF template library. Originals are never edited or overwritten."""
from __future__ import annotations

from dataclasses import dataclass
import html
from pathlib import Path
import re

import pymupdf

DEFAULT_FOLDER = Path(__file__).resolve().parents[2] / 'templates'
PAGE_SIZES = {'A4': (595.276, 841.89), 'A5': (419.528, 595.276), 'Letter': (612, 792)}


@dataclass(frozen=True)
class Template:
    path: Path
    name: str
    size: int
    modified: float


class TemplateLibrary:
    def __init__(self, folder=DEFAULT_FOLDER):
        self.folder = Path(folder).resolve()

    def ensure_folder(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        return self.folder

    def list(self):
        self.ensure_folder()
        entries = []
        for path in self.folder.rglob('*'):
            if path.suffix.lower() != '.pdf' or path.is_symlink():
                continue
            try:
                if not path.is_file() or not path.resolve().is_relative_to(self.folder):
                    continue
                stat = path.stat()
                entries.append(Template(path, path.relative_to(self.folder).as_posix(),
                                        stat.st_size, stat.st_mtime))
            except OSError:
                continue  # A file may have been removed while the folder was scanned.
        return sorted(entries, key=lambda entry: entry.name.casefold())

    @staticmethod
    def filename(name):
        name = name.strip()
        if name.lower().endswith('.pdf'):
            name = name[:-4]
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')
        if not name:
            raise ValueError('Podaj nazwę szablonu.')
        if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                                          *(f'COM{i}' for i in range(1, 10)),
                                          *(f'LPT{i}' for i in range(1, 10))}:
            name = '_' + name
        return name[:120] + '.pdf'

    def _publish(self, data, name):
        self.ensure_folder()
        filename = self.filename(name)
        stem = Path(filename).stem
        # Exclusive creation works on NTFS and removable volumes too.
        # Never truncate an existing template, including case-only collisions.
        number = 1
        while True:
            target = self.folder / (filename if number == 1 else f'{stem} ({number}).pdf')
            existing = {p.name.casefold() for p in self.folder.iterdir()}
            if target.name.casefold() not in existing:
                try:
                    with target.open('xb') as stream:
                        try:
                            stream.write(data)
                        except Exception:
                            stream.close()
                            target.unlink(missing_ok=True)
                            raise
                    return target
                except FileExistsError:
                    pass
            number += 1

    def import_pdf(self, source, name=None):
        source = Path(source)
        if source.suffix.lower() != '.pdf':
            raise ValueError('Szablon musi być plikiem PDF.')
        data = source.read_bytes()
        with pymupdf.open(stream=data, filetype='pdf') as document:
            if document.needs_pass:
                raise ValueError('Szablon jest chroniony hasłem. Wybierz niezabezpieczony PDF.')
            if not document.is_pdf or not len(document):
                raise ValueError('Nieprawidłowy lub pusty PDF.')
        return self._publish(data, source.name if name is None else name)

    def create(self, name, page_size='A4', landscape=False, pages=1, title='', text=''):
        if page_size not in PAGE_SIZES:
            raise ValueError('Nieobsługiwany format strony.')
        if not isinstance(pages, int) or not 1 <= pages <= 100:
            raise ValueError('Wybierz od 1 do 100 stron.')
        self.filename(name)  # Validate before rendering.
        width, height = PAGE_SIZES[page_size]
        if landscape:
            width, height = height, width
        with pymupdf.open() as document:
            for _ in range(pages):
                document.new_page(width=width, height=height)
            if title.strip() or text.strip():
                # Escape user text: no external resources, scripts or HTML input.
                content = (f'<h1>{html.escape(title)}</h1>' if title.strip() else '')
                content += '<div>' + html.escape(text).replace('\n', '<br>') + '</div>'
                remaining, _ = document[0].insert_htmlbox(
                    pymupdf.Rect(40, 40, width - 40, height - 40), content,
                    css='* {font-family: sans-serif;} body {font-size: 11pt;} '
                        'h1 {font-size: 20pt; margin: 0 0 18pt 0;}', scale_low=1)
                if remaining < 0:
                    raise ValueError('Tekst nie mieści się na pierwszej stronie. Skróć treść lub wybierz większy format.')
            document.set_metadata({'title': title or Path(name).stem, 'creator': 'PrOximAl edit'})
            return self._publish(document.tobytes(garbage=3, deflate=True), name)
