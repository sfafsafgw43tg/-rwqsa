# -*- coding: utf-8 -*-
"""
KAMELEON PDF — zmiana dat plików.
• znaczniki czasu systemu plików (utworzony / zmodyfikowany / dostęp),
• daty w metadanych PDF (CreationDate / ModDate) i w polach XMP.
Windows: ustawia również datę UTWORZENIA (SetFileTime przez ctypes — bez dodatkowych zależności).
"""
from __future__ import annotations

import os
import sys
import ctypes
import datetime as dt

import pymupdf


def get_file_times(path: str) -> dict:
    st = os.stat(path)
    out = {
        "modified": dt.datetime.fromtimestamp(st.st_mtime),
        "accessed": dt.datetime.fromtimestamp(st.st_atime),
        "created": None,
    }
    if sys.platform == "win32":
        try:
            import win32file  # type: ignore
            ctime = st.st_ctime
            out["created"] = dt.datetime.fromtimestamp(ctime)
        except Exception:
            out["created"] = dt.datetime.fromtimestamp(st.st_ctime)
    else:
        out["created"] = dt.datetime.fromtimestamp(st.st_ctime)
    return out


if sys.platform == "win32":
    def _set_win_times(path: str, created=None, modified=None, accessed=None):
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3
        FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
        k32 = ctypes.windll.kernel32
        h = k32.CreateFileW(path, GENERIC_WRITE, 0, None, OPEN_EXISTING,
                            FILE_FLAG_BACKUP_SEMANTICS, None)
        if h == -1 or h == 0xFFFFFFFFFFFFFFFF:
            raise OSError(f"CreateFileW failed: {ctypes.GetLastError()}")
        try:
            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", ctypes.c_uint), ("dwHighDateTime", ctypes.c_uint)]
            def ft(d):
                if d is None:
                    return None
                if isinstance(d, dt.datetime) and d.tzinfo is None:
                    d = d.replace(tzinfo=dt.timezone.utc)
                elif isinstance(d, dt.datetime):
                    pass
                ts = int(d.timestamp() * 10_000_000) + 116444736000000000
                return FILETIME(ts & 0xFFFFFFFF, ts >> 32)
            c, m, a = ft(created), ft(modified), ft(accessed)
            if not k32.SetFileTime(h, ctypes.byref(c) if c else None,
                                   ctypes.byref(a) if a else None,
                                   ctypes.byref(m) if m else None):
                raise OSError(f"SetFileTime failed: {ctypes.GetLastError()}")
        finally:
            k32.CloseHandle(h)
else:
    def _set_win_times(path, created=None, modified=None, accessed=None):
        raise OSError("Dostępne tylko na Windows")


def set_file_times(path: str, created: dt.datetime | None = None,
                   modified: dt.datetime | None = None,
                   accessed: dt.datetime | None = None) -> dict:
    """Ustawia daty pliku. Na nie-Windows data utworzenia = zmodyfikowania."""
    report = {}
    base = modified or created
    acc = accessed or base
    if base and acc:
        os.utime(path, times=(acc.timestamp(), base.timestamp()))
    if sys.platform == "win32":
        _set_win_times(path, created=created, modified=modified, accessed=accessed)
        report["created"] = True
    else:
        report["created"] = False
    report["ok"] = True
    return report


def get_pdf_metadata(path: str) -> dict:
    doc = pymupdf.open(path)
    meta = dict(doc.metadata or {})
    doc.close()
    return meta


def set_pdf_dates(path: str, out_path: str | None = None,
                  creation: dt.datetime | None = None,
                  modification: dt.datetime | None = None) -> dict:
    """Ustawia daty w metadanych PDF (Info + XMP)."""
    doc = pymupdf.open(path)
    def fmt(d: dt.datetime) -> str:
        return d.strftime("D:%Y%m%d%H%M%S+00'00'")
    meta = dict(doc.metadata or {})
    if creation:
        meta["creationDate"] = fmt(creation)
    if modification:
        meta["modDate"] = fmt(modification)
    doc.set_metadata(meta)
    try:
        xref = doc.pdf_catalog()
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/">
{'<xmp:CreateDate>' + creation.strftime('%Y-%m-%dT%H:%M:%SZ') + '</xmp:CreateDate>' if creation else ''}
{'<xmp:ModifyDate>' + modification.strftime('%Y-%m-%dT%H:%M:%SZ') + '</xmp:ModifyDate>' if modification else ''}
</rdf:Description></rdf:RDF></x:xmpmeta>"""
        doc.set_xml_metadata(xml)
    except Exception:
        pass
    target = out_path or path
    if target != path:
        doc.save(target, garbage=3, deflate=True)
        doc.close()
    else:
        doc.saveIncr()
        doc.close()
    return {"ok": True, "creation": bool(creation), "modification": bool(modification)}
