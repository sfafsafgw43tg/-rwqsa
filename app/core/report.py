# -*- coding: utf-8 -*-
"""PrOximAl edit — raporty (JSON/CSV) oraz mapowania podmian do trybu wsadowego."""
from __future__ import annotations

import csv
import json
import os


def export_report(path: str, items: list, reports: list[dict] | None = None):
    """Eksport listy elementów (i ewentualnych wyników podmian) do JSON lub CSV."""
    rep_map = {r["id"]: r for r in (reports or [])}
    base = os.path.splitext(path)[1].lower()
    rows = []
    for it in items:
        r = rep_map.get(it.id, {})
        rows.append({
            "id": it.id,
            "strona": it.page + 1,
            "typ": it.type,
            "pewnosc_klasyfikacji": round(it.score, 2),
            "edytowalny": it.editable,
            "zrodlo": it.source,
            "pewnosc_ocr": it.ocr_confidence,
            "opis_etykieta": it.label,
            "wartosc_oryginalna": it.value,
            "wartosc_nowa": it.new_value or r.get("new", ""),
            "czcionka": it.font_desc,
            "status": r.get("status", ""),
            "pozycja": ";".join(f"{v:.1f}" for v in it.rect),
        })
    if base == ".json":
        with open(path, "w", encoding="utf-8-sig") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
    else:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["id"], delimiter=";")
            w.writeheader()
            w.writerows(rows)
    return path


def export_mapping(path: str, items: list):
    """Mapowanie: stara wartość + etykieta -> nowa wartość (do batchy)."""
    data = []
    for it in items:
        if it.new_value:
            data.append({"typ": it.type, "opis": it.label, "stara": it.value, "nowa": it.new_value})
    with open(path, "w", encoding="utf-8-sig") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def import_mapping(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Mapowanie JSON musi być listą zmian.")
    out = []
    for d in data:
        if isinstance(d, dict) and "stara" in d and "nowa" in d:
            out.append({"typ": d.get("typ", ""), "opis": d.get("opis", ""),
                        "stara": str(d["stara"]), "nowa": str(d["nowa"])})
    return out
