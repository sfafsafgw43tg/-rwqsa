# -*- coding: utf-8 -*-
"""
KAMELEON PDF — serwer aplikacji (100% offline, działa lokalnie).
Uruchamiany przez uruchom.bat / start_app.bat albo bezpośrednio:
    python app/webapp.py
"""
from __future__ import annotations

import os
import io
import json
import base64
import secrets
import shutil
import threading
import zipfile
import datetime as dt

from flask import Flask, request, jsonify, send_file, render_template, abort

import pymupdf

from .core import analyzer, replacer, report as report_mod, filedates, fonts as fontmod
from .core.replacer import ReplaceOptions
from .core import ocr as ocrmod

APP_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(APP_DIR)
WORK = os.path.join(ROOT, "praca")
os.makedirs(WORK, exist_ok=True)

app = Flask(__name__, static_folder=os.path.join(APP_DIR, "static"), template_folder=os.path.join(APP_DIR, "templates"))
app.config["MAX_CONTENT_LENGTH"] = 300 * 1024 * 1024  # 300 MB

SESSIONS: dict[str, dict] = {}
LOCK = threading.Lock()

TYPE_ORDER = ["data", "imię i nazwisko", "nazwisko", "nazwa", "kwota", "kwota?",
              "PESEL", "NIP", "REGON", "nr konta", "telefon", "telefon?",
              "kod pocztowy", "procent", "numer", "symbol", "ulica nr", "tekst"]


# ----------------------------------------------------------------- pomocniki -
def _sess(sid: str) -> dict:
    s = SESSIONS.get(sid)
    if not s:
        abort(404, "Sesja nie istnieje (odśwież stronę i wgraj plik ponownie).")
    return s


def _item_to_json(it: analyzer.Item) -> dict:
    return {
        "id": it.id, "page": it.page, "type": it.type, "value": it.value,
        "label": it.label, "score": round(it.score, 2), "enabled": it.enabled,
        "font": it.font_desc, "rect": [round(v, 2) for v in it.rect],
        "new": it.new_value, "source": it.source,
    }


def _render_page_b64(path: str, page_no: int, target_w: int = 940) -> str:
    doc = pymupdf.open(path)
    if page_no >= doc.page_count:
        page_no = doc.page_count - 1
    page = doc[page_no]
    zoom = target_w / max(1.0, page.rect.width)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    b = pix.tobytes("png")
    doc.close()
    return "data:image/png;base64," + base64.b64encode(b).decode()


# -------------------------------------------------------------------- OCR ----
def ocr_page_lines(page, lang="pol", dpi=260) -> list[dict]:
    """Buduje pseudo-linie (struktura jak extract_lines) ze słów OCR."""
    words = ocrmod.ocr_words_with_geometry(page, lang=lang, dpi=dpi)
    lines: dict[tuple, list[dict]] = {}
    for w in words:
        key = w["line"]
        lines.setdefault(key, []).append(w)
    out = []
    for key, ws in sorted(lines.items()):
        ws.sort(key=lambda w: w["bbox"][0])
        spans = []
        for w in ws:
            x0, y0, x1, y1 = w["bbox"]
            h = max(4.0, y1 - y0)
            spans.append(analyzer.SpanInfo(
                text=w["text"] + " ", bbox=(x0, y0, x1, y1),
                origin=(x0, y1 - 0.22 * h), font="Helvetica", size=0.78 * h,
                color=0, flags=0, xref=None))
        text = "".join(s.text for s in spans)
        bbox = (min(s.bbox[0] for s in spans), min(s.bbox[1] for s in spans),
                max(s.bbox[2] for s in spans), max(s.bbox[3] for s in spans))
        out.append({"text": text, "bbox": bbox, "spans": spans, "dir": (1, 0), "ocr": True})
    return out


# --------------------------------------------------------------------- API ---
@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/upload")
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Wgraj plik PDF."}), 400
    sid = secrets.token_hex(8)
    dst = os.path.join(WORK, f"{sid}__zrodlo.pdf")
    f.save(dst)
    try:
        items, empty_pages = analyzer.analyze_document(dst)
    except Exception as e:
        return jsonify({"error": f"Nie udało się odczytać PDF: {e}"}), 400
    doc = pymupdf.open(dst)
    info = {"sid": sid, "name": f.filename, "pages": doc.page_count, "empty_pages": empty_pages}
    doc.close()
    SESSIONS[sid] = {"sid": sid, "src": dst, "name": f.filename, "items": items,
                     "empty_pages": empty_pages, "result": None, "reports": None}
    return jsonify({"session": info, "items": [_item_to_json(i) for i in items]})


@app.post("/api/ocr")
def api_ocr():
    s = _sess(request.form.get("sid", ""))
    lang = request.form.get("lang", "pol")
    if not ocrmod.tesseract_available():
        return jsonify({"error": "Tesseract OCR nie jest zainstalowany. Uruchom ponownie instalator i zaznacz 'Tesseract OCR'."}), 400
    added = 0
    try:
        doc = pymupdf.open(s["src"])
        for pno in s.get("empty_pages", []):
            page = doc[pno]
            lines = ocr_page_lines(page, lang=lang)
            new_items = analyzer.analyze_lines(lines, page_no=pno, ocr=True)
            new_items = ocrmod.refine_item_rects(page, new_items)
            have = {(round(i.rect[0]), round(i.rect[1])) for i in s["items"]}
            for it in new_items:
                key = (round(it.rect[0]), round(it.rect[1]))
                if key not in have:
                    s["items"].append(it)
                    added += 1
        doc.close()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Błąd OCR: {e}"}), 500
    return jsonify({"added": added, "items": [_item_to_json(i) for i in s["items"]]})


@app.get("/api/preview/<sid>/<int:page_no>")
def api_preview(sid, page_no):
    s = _sess(sid)
    which = request.args.get("co", "zrodlo")
    path = s["result"] if (which == "wynik" and s["result"]) else s["src"]
    return jsonify({"img": _render_page_b64(path, page_no)})


@app.post("/api/apply")
def api_apply():
    s = _sess(request.form.get("sid", ""))
    values = json.loads(request.form.get("values", "{}"))
    opts = ReplaceOptions(
        min_font_size=float(request.form.get("min_size", 4.0)),
        allow_expand=request.form.get("expand") == "1",
        fill_mode=request.form.get("fill", "auto"),
        preserve_center=request.form.get("center") == "1",
        use_embedded_fonts=request.form.get("embedded", "1") == "1",
    )
    apply_file_dates = request.form.get("file_dates") == "1"
    try:
        fd_created = request.form.get("fd_created", "").strip()
        fd_modified = request.form.get("fd_modified", "").strip()
    except Exception:
        fd_created = fd_modified = ""

    jobs = []
    for it in s["items"]:
        nv = values.get(it.id, it.new_value or "")
        if nv and nv != it.value:
            it.new_value = nv
            jobs.append((it, nv))
    if not jobs:
        return jsonify({"error": "Brak zmian do zastosowania."}), 400

    out = os.path.join(WORK, f"{s['sid']}__wynik.pdf")
    reports = replacer.apply_replacements(s["src"], out, jobs, opts)
    s["result"] = out
    s["reports"] = reports

    # daty pliku / metadane PDF
    if apply_file_dates:
        try:
            c = dt.datetime.fromisoformat(fd_created) if fd_created else None
            m = dt.datetime.fromisoformat(fd_modified) if fd_modified else None
            if c or m:
                filedates.set_file_times(out, created=c, modified=m, accessed=m)
            if request.form.get("pdf_meta") == "1":
                filedates.set_pdf_dates(out, creation=c, modification=m or dt.datetime.now())
        except Exception as e:
            return jsonify({"reports": reports, "warning": f"Podmiana OK, ale daty nie zostały ustawione: {e}",
                            "out": os.path.basename(out)})

    return jsonify({"reports": reports, "out": os.path.basename(out)})


@app.get("/api/download/<sid>")
def api_download(sid):
    s = _sess(sid)
    if not s["result"]:
        abort(404, "Najpierw zastosuj zmiany.")
    root, ext = os.path.splitext(s["name"])
    return send_file(s["result"], as_attachment=True, download_name=f"{root}_ZMIENIONY.pdf")


@app.post("/api/filedates")
def api_filedates():
    """Zmiana dat pliku (i metadanych PDF) dla wgranego lub wynikowego pliku."""
    s = _sess(request.form.get("sid", ""))
    target = request.form.get("target", "wynik")
    path = s["result"] if (target == "wynik" and s["result"]) else s["src"]
    c = dt.datetime.fromisoformat(request.form["created"]) if request.form.get("created") else None
    m = dt.datetime.fromisoformat(request.form["modified"]) if request.form.get("modified") else None
    info = {}
    if c or m:
        info = filedates.set_file_times(path, created=c, modified=m, accessed=m)
    if request.form.get("pdf_meta") == "1":
        info.update(filedates.set_pdf_dates(path, creation=c, modification=m or dt.datetime.now()))
    cur = filedates.get_file_times(path)
    meta = filedates.get_pdf_metadata(path)
    return jsonify({"ok": True, "current": {
        "created": cur["created"].isoformat(timespec="seconds") if cur["created"] else None,
        "modified": cur["modified"].isoformat(timespec="seconds"),
        "pdf_creation": (meta.get("creationDate") or "")[:16],
        "pdf_modification": (meta.get("modDate") or "")[:16],
    }, "windows_created_set": info.get("created", False)})


@app.get("/api/filedates/<sid>")
def api_filedates_get(sid):
    s = _sess(sid)
    path = s["result"] or s["src"]
    cur = filedates.get_file_times(path)
    meta = filedates.get_pdf_metadata(path)
    return jsonify({"current": {
        "created": cur["created"].isoformat(timespec="seconds") if cur["created"] else None,
        "modified": cur["modified"].isoformat(timespec="seconds"),
        "pdf_creation": (meta.get("creationDate") or "")[:16],
        "pdf_modification": (meta.get("modDate") or "")[:16],
    }})


@app.post("/api/export")
def api_export():
    s = _sess(request.form.get("sid", ""))
    kind = request.form.get("kind", "csv")
    ext = {"csv": ".csv", "json": ".json", "mapping": ".mapping.json"}.get(kind, ".csv")
    path = os.path.join(WORK, f"{s['sid']}{ext}")
    if kind == "mapping":
        report_mod.export_mapping(path, s["items"])
    else:
        report_mod.export_report(path, s["items"], s.get("reports"))
    return send_file(path, as_attachment=True)


# ----------------------------------------------------------------- batch -----
BATCH_DIRS: dict[str, str] = {}


@app.post("/api/batch/upload")
def api_batch_upload():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "Nie wybrano plików."}), 400
    bid = secrets.token_hex(6)
    bdir = os.path.join(WORK, f"batch_{bid}")
    os.makedirs(bdir, exist_ok=True)
    names = []
    for f in files:
        if f.filename.lower().endswith(".pdf"):
            f.save(os.path.join(bdir, f.filename))
            names.append(f.filename)
    BATCH_DIRS[bid] = bdir
    return jsonify({"bid": bid, "files": names})


@app.post("/api/batch/run")
def api_batch_run():
    bid = request.form.get("bid", "")
    bdir = BATCH_DIRS.get(bid)
    if not bdir:
        return jsonify({"error": "Sesja wsadowa wygasła — wgraj pliki ponownie."}), 400
    mapping = request.form.get("mapping", "[]")
    mpath = os.path.join(bdir, "_mapowanie.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        fh.write(mapping)
    files = [os.path.join(bdir, n) for n in os.listdir(bdir) if n.lower().endswith(".pdf")]
    opts = ReplaceOptions(allow_expand=True)
    mapping_data = json.load(open(mpath, encoding="utf-8-sig"))
    from .core.batch import _match_items
    results = []
    for path in files:
        try:
            items, _ = analyzer.analyze_document(path)
            jobs = _match_items(items, mapping_data)
            root, ext = os.path.splitext(path)
            out = f"{root}_ZMIENIONY{ext}"
            reps = replacer.apply_replacements(path, out, jobs, opts)
            results.append({"plik": os.path.basename(path), "status": "ok",
                            "podmieniono": len([r for r in reps if r["status"].startswith("ok")]),
                            "wyjscie": os.path.basename(out)})
        except Exception as e:
            results.append({"plik": os.path.basename(path), "status": f"błąd: {e}", "podmieniono": 0})
    return jsonify({"results": results})


@app.get("/api/batch/download/<bid>")
def api_batch_download(bid):
    bdir = BATCH_DIRS.get(bid)
    if not bdir:
        abort(404)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in os.listdir(bdir):
            if n.lower().endswith(".pdf") and n.endswith("_ZMIENIONY.pdf"):
                z.write(os.path.join(bdir, n), n)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="kameleon_wsad_wyniki.zip", mimetype="application/zip")


# ------------------------------------------------------------------- start ---
def _find_free_port(start: int, tries: int = 20) -> int:
    import socket
    port = start
    for _ in range(tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                port += 1
    return start


def main():
    import webbrowser, threading
    port = _find_free_port(8770)
    url = f"http://127.0.0.1:{port}"
    print("=" * 56)
    print("  KAMELEON PDF — serwer uruchomiony")
    print(f"  ADRES:{url}")
    print("  Nie zamykaj tego okna — aplikacja działa w tle.")
    print("=" * 56, flush=True)
    if os.environ.get("KAMELEON_NO_BROWSER") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host="0.0.0.0", port=port, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
