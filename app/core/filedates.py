"""Local file/PDF timestamps. Preserve unrelated XMP metadata."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import datetime as dt
import os
import sys
import xml.etree.ElementTree as ET
import pymupdf


def get_file_times(path):
    st = os.stat(path)
    birth = getattr(st, 'st_birthtime', st.st_ctime if sys.platform == 'win32' else None)
    return {'modified': dt.datetime.fromtimestamp(st.st_mtime),
            'accessed': dt.datetime.fromtimestamp(st.st_atime),
            'created': dt.datetime.fromtimestamp(birth) if birth is not None else None}


def _set_win_times(path, created=None, modified=None, accessed=None):
    if sys.platform != 'win32':
        raise OSError('Data utworzenia pliku: dostępna tylko na Windows.')
    class FILETIME(ctypes.Structure):
        _fields_ = [('low', wintypes.DWORD), ('high', wintypes.DWORD)]
    # Explicit pointer-sized HANDLE signatures are essential on 64-bit Windows.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.SetFileTime.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(FILETIME)] * 3
    kernel.SetFileTime.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(path), 0x100, 7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    def ft(value):
        if value is None:
            return None
        timestamp = int(value.timestamp() * 10_000_000) + 116444736000000000
        return FILETIME(timestamp & 0xffffffff, timestamp >> 32)
    c, a, m = ft(created), ft(accessed), ft(modified)
    try:
        if not kernel.SetFileTime(handle, ctypes.byref(c) if c else None,
                                  ctypes.byref(a) if a else None, ctypes.byref(m) if m else None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def set_file_times(path, created=None, modified=None, accessed=None):
    st = os.stat(path)
    if modified or accessed:
        os.utime(path, (accessed.timestamp() if accessed else st.st_atime,
                        modified.timestamp() if modified else st.st_mtime))
    if sys.platform == 'win32':
        _set_win_times(path, created, modified, accessed)
    return {'ok': True, 'created': bool(created and sys.platform == 'win32')}


def get_pdf_metadata(path):
    with pymupdf.open(path) as doc:
        return dict(doc.metadata or {})


def set_pdf_dates(path, out_path=None, creation=None, modification=None):
    def utc(value):
        return value.astimezone(dt.timezone.utc)
    with pymupdf.open(path) as doc:
        metadata = dict(doc.metadata or {})
        for key, value in [('creationDate', creation), ('modDate', modification)]:
            if value:
                metadata[key] = utc(value).strftime("D:%Y%m%d%H%M%S+00'00'")
        doc.set_metadata(metadata)
        xml = doc.get_xml_metadata()
        rdf = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
        xmp = 'http://ns.adobe.com/xap/1.0/'
        try:
            root = ET.fromstring(xml) if xml else ET.Element('{adobe:ns:meta/}xmpmeta')
            node = root.find('.//{' + rdf + '}Description')
            if node is None:
                container = ET.SubElement(root, '{' + rdf + '}RDF')
                node = ET.SubElement(container, '{' + rdf + '}Description')
            for key, value in [('CreateDate', creation), ('ModifyDate', modification)]:
                if value:
                    tag = '{' + xmp + '}' + key
                    timestamp = utc(value).strftime('%Y-%m-%dT%H:%M:%SZ')
                    # Existing properties may be attributes or elements, in any description.
                    for description in root.iter('{' + rdf + '}Description'):
                        if tag in description.attrib:
                            description.set(tag, timestamp)
                    elements = list(root.iter(tag))
                    if not elements:
                        elements = [ET.SubElement(node, tag)]
                    for element in elements:
                        element.text = timestamp
            doc.set_xml_metadata(ET.tostring(root, encoding='unicode'))
        except ET.ParseError:
            # Preserve malformed vendor XMP instead of replacing unrelated metadata.
            pass
        if out_path and os.path.abspath(out_path) != os.path.abspath(path):
            doc.save(out_path, garbage=3, deflate=True)
        else:
            doc.saveIncr()
    return {'ok': True, 'creation': bool(creation), 'modification': bool(modification)}
