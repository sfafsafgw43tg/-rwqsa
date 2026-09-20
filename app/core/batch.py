# -*- coding: utf-8 -*-
"""
KAMELEON PDF — tryb wsadowy.
Stosuje to samo mapowanie podmian do wielu podobnych plików PDF
(np. faktur z tego samego szablonu) — dopasowanie po etykiecie lub wartości.
"""
from __future__ import annotations

import os

import pymupdf

from . import analyzer, replacer, report as report_mod


def _match_items(items: list, mapping: list[dict]) -> list[tuple]:
    jobs = []
    for it in items:
        for m in mapping:
            label = (m.get("opis") or "").strip().lower()
            old = str(m.get("stara", "")).strip()
            new = str(m.get("nowa", "")).strip()
            if not new:
                continue
            by_label = bool(label) and label == (it.label or "").strip().lower()
            by_value = bool(old) and old == it.value.strip()
            if by_label or by_value:
                jobs.append((it, new))
                break
    return jobs


def run_batch(files: list[str], mapping_path: str, suffix: str = "_ZMIENIONY",
              opts: replacer.ReplaceOptions | None = None, progress=None) -> list[dict]:
    mapping = report_mod.import_mapping(mapping_path)
    results = []
    for i, path in enumerate(files):
        try:
            items, no_text = analyzer.analyze_document(path)
            jobs = _match_items(items, mapping)
            root, ext = os.path.splitext(path)
            out = f"{root}{suffix}{ext}"
            reps = replacer.apply_replacements(path, out, jobs, opts)
            results.append({"plik": path, "wyjscie": out, "status": "ok",
                            "podmieniono": len([r for r in reps if r["status"].startswith("ok")]),
                            "szczegoly": reps})
        except Exception as e:
            results.append({"plik": path, "wyjscie": None, "status": f"błąd: {e}", "podmieniono": 0})
        if progress:
            progress(i + 1, len(files))
    return results
