#!/usr/bin/env python3
"""Csatlakoztatott HID eszközök azonosítása (hidapi).

Példák:
  python hid_scan.py               # rövid lista (összes HID eszköz)
  python hid_scan.py -d            # részletes lista
  python hid_scan.py -f 1A86:DD01  # csak az adott eszköz, részletesen
  python hid_scan.py -f 0x1A86:0xDD01

A program mappájában lévő hidapi.dll-t is megkeresi (Windows, a
rfid125k/protocol.py mintájára). Az RFID125k projekt olvasója (VID 1A86,
PID DD01, CH341) külön jelölést kap.
"""
import argparse
import os
import re
import sys

# Windows: hidapi.dll a program mappájában lehet - tegyük a DLL-keresési
# útvonalra, mielőtt a hid modul betöltődik.
if os.name == "nt":
    for _d in [
        os.path.dirname(os.path.abspath(sys.argv[0] or ".")),
        os.path.dirname(os.path.abspath(__file__)),
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        os.getcwd(),
    ]:
        try:
            os.add_dll_directory(_d)
        except Exception:
            pass

try:
    import hid
except ImportError:
    sys.exit("Hiba: a 'hid' modul nincs telepítve. Futtasd: pip install hid")

RFID_VID, RFID_PID = 0x1A86, 0xDD01

DETAIL_FIELDS = [
    ("path", "Útvonal"),
    ("vendor_id", "VID (gyártó azonosító)"),
    ("product_id", "PID (termék azonosító)"),
    ("manufacturer_string", "Gyártó"),
    ("product_string", "Termék"),
    ("serial_number", "Sorozatszám"),
    ("release_number", "Release szám (firmware)"),
    ("usage_page", "HID UsagePage"),
    ("usage", "HID Usage"),
    ("interface_number", "Interfész szám (Windows)"),
]

VID_PID_RE = re.compile(r"^0[xX]([0-9a-fA-F]+):0[xX]([0-9a-fA-F]+)$")
SHORT_RE = re.compile(r"^([0-9a-fA-F]{1,4}):([0-9a-fA-F]{1,4})$")


def parse_vid_pid(text):
    """'1A86:DD01' vagy '0x1A86:0xDD01' formátumú pár értelmezése."""
    text = (text or "").strip()
    m = VID_PID_RE.match(text) or SHORT_RE.match(text)
    if not m:
        return None
    return int(m.group(1), 16), int(m.group(2), 16)


def is_rfid(d):
    return d.get("vendor_id") == RFID_VID and d.get("product_id") == RFID_PID


def _s(d, key):
    value = d.get(key)
    if value is None:
        return "n/a"
    return str(value).strip()


def _u(d, key):
    value = d.get(key) or 0
    return f"0x{int(value):04X}"


def _path_str(value):
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", "replace")
        except Exception:
            return repr(value)
    return str(value)

def brief_line(d):
    vid = int(d.get("vendor_id") or 0)
    pid = int(d.get("product_id") or 0)
    manu = _s(d, "manufacturer_string") or "?"
    prod = _s(d, "product_string") or "?"
    up, u = _u(d, "usage_page"), _u(d, "usage")
    mark = "  <== RFID olvasó (az RFID125k eszköze)" if is_rfid(d) else ""
    return f"{vid:04X}:{pid:04X}  {manu} - {prod}  (UsagePage {up}, Usage {u}){mark}"


def detail_block(index, total, d):
    header = f"[{index}/{total}] {int(d.get('vendor_id') or 0):04X}:{int(d.get('product_id') or 0):04X}"
    if is_rfid(d):
        header += "  <== RFID olvasó (az RFID125k eszköze)"
    lines = [header, "-" * len(header)]
    for key, label in DETAIL_FIELDS:
        value = d.get(key)
        if value is None and key == "interface_number":
            value = "(csak Windows)"
        if key == "path" and value is not None:
            text = _path_str(value)
        elif value is None:
            text = "n/a"
        else:
            text = str(value).strip()
        if key in ("vendor_id", "product_id"):
            text = f"{int(value):04X}"
        elif key in ("usage_page", "usage"):
            text = f"0x{int(value):04X}"
        elif key == "release_number":
            text = f"0x{int(value):04X} ({int(value)})"
        lines.append(f"  {label:<28}: {text}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Csatlakoztatott HID eszközök azonosítása (rövid vagy részletes lista).")
    ap.add_argument("-d", "--detail", action="store_true",
                    help="minden eszköz részletes adatai")
    ap.add_argument("-f", "--filter", metavar="VID:PID",
                    help="csak az adott eszköz (pl. 1A86:DD01), részletesen")
    args = ap.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        for _stream in (sys.stdout, sys.stderr):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    try:
        devices = list(hid.enumerate(0, 0) or [])
    except Exception as ex:
        sys.exit(f"Hiba a HID eszközök listázásakor: {ex}")

    if args.filter:
        pair = parse_vid_pid(args.filter)
        if pair is None:
            sys.exit(f"Érvénytelen VID:PID formátum: {args.filter!r} "
                     "(pl. 1A86:DD01 vagy 0x1A86:0xDD01).")
        matched = [d for d in devices
                   if (d.get("vendor_id"), d.get("product_id")) == pair]
        if not matched:
            sys.exit(f"Nincs {args.filter.upper()} (VID:{pair[0]:04X} "
                     f"PID:{pair[1]:04X}) azonosítójú csatlakoztatott HID eszköz.")
        print(f"{args.filter.upper()} azonosítójú eszközök: {len(matched)} db\n")
        for i, d in enumerate(matched, 1):
            print(detail_block(i, len(matched), d))
            print()
        return

    if not devices:
        print("Nincs csatlakoztatott HID eszköz.")
        return

    if args.detail:
        print(f"Csatlakoztatott HID eszközök: {len(devices)} db\n")
        for i, d in enumerate(devices, 1):
            print(detail_block(i, len(devices), d))
            print()
    else:
        print(f"Csatlakoztatott HID eszközök: {len(devices)} db\n")
        for d in devices:
            print(brief_line(d))
        print("\nRészletes adatokhoz: python hid_scan.py -d")


if __name__ == "__main__":
    main()