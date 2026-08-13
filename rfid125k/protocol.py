"""Vezetéki protokoll az RFID olvasóval (dinamikusan rögzített, IDReader.dll
IAT-hook alapján ellenőrzött):

- 64 bájtos HID report, report ID 0x01 (VID 1A86 / PID DD01, CH341).
- TX: 01 AA 55 <param=00> <cmd0=00> <cmd_hi> <cmd_lo> <len_hi> <len_lo>
       <payload...> <checksum> <CC padding>
- RX: 01 AA 55 <param=11> <cmd0=12> <cmd_hi> <cmd_lo> <len_hi> <len_lo>
       <payload...> <checksum> (+ maradék régi bájtok)
- Checksum = a param..payload bájtok XOR-ja (az AA 55 és a report ID nélkül).
- A 0xAA bájtok a vezetéken AA 00-ként jönnek (escape), az escape bájt
  nem része a checksumnak.
"""
import os
import sys

from .i18n import t as L

# Windows: a hidapi.dll a program mappájában van - tegyük a DLL-keresési útvonalra,
# mielőtt a hid modul betölti.
if os.name == "nt":
    try:
        _candidates = [
            os.path.dirname(os.path.abspath(sys.argv[0] or ".")),
            os.path.dirname(os.path.abspath(__file__)),          # rfid125k/
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # python/
            os.getcwd(),
        ]
        for _d in _candidates:
            try:
                os.add_dll_directory(_d)
            except Exception:
                pass
    except Exception:
        pass

# Elsődleges szállítás: a hidapi (hid modul). Linuxon, ha nem érhető el
# (fordítás nélkül), a program a tiszta Python hidraw háttérrel dolgozik
# (rfid125k/hidrawlink.py) - az import ezért opcionális.
try:
    import hid
except Exception:
    hid = None

if sys.platform.startswith("linux"):
    from .hidrawlink import HidRawError, HidRawLink, enumerate_hidraw
else:
    HidRawError = HidRawLink = enumerate_hidraw = None


class CMD:
    SET_AUTO_READ = 0x0801
    SET_LED = 0x0802
    SET_BEEP = 0x0803
    SET_FREQUENCY = 0x0804
    GET_FREQUENCY = 0x0805
    GET_MODEL = 0x0806
    GET_NUMBER = 0x0808
    READ_ID_CARD = 0x0809
    SET_OUT_FORMAT = 0x080A
    GET_OUT_FORMAT = 0x080B
    WRITE_EL4100 = 0x0810
    WRITE_T4100 = 0x0811
    WRITE_E4100 = 0x0812


REPORT_LEN = 64
VID = 0x1A86
PID = 0xDD01


class ProtocolError(Exception):
    pass


class DeviceNotFoundError(Exception):
    pass


def build_report(cmd: int, payload: bytes) -> bytes:
    """64 bájtos HID report összeállítása a TX-formátum szerint."""
    payload = bytes(payload)
    if len(payload) > 0xFFFF:
        raise ProtocolError("Túl hosszú payload.")
    body = bytearray([0x00, 0x00, (cmd >> 8) & 0xFF, cmd & 0xFF, 0x00, len(payload) & 0xFF])
    body += payload
    x = 0
    for b in body:
        x ^= b
    body.append(x)

    escaped = bytearray()
    for b in body:
        escaped.append(b)
        if b == 0xAA:
            escaped.append(0x00)

    wire = bytearray([0x01, 0xAA, 0x55]) + escaped
    wire += bytes([0xCC]) * (REPORT_LEN - len(wire))
    return bytes(wire)


def parse_report(data: bytes):
    """Résztvevő report elemzése. Visszaadja (cmd, payload)-t, vagy None-t,
    ha a report nem érvényes AA 55 csomag (hibás checksum, hiányzó szinkron)."""
    idx = data.find(b"\xaa\x55")
    if idx < 0 or idx + 2 >= len(data):
        return None
    body = data[idx + 2 :]

    param = body[0]
    logical = bytearray()
    i = 1
    while i < len(body):
        b = body[i]
        logical.append(b)
        i += 1
        if b == 0xAA and i < len(body) and body[i] == 0x00:
            i += 1  # escape bájt kihagyása

    if len(logical) < 5:
        return None
    cmd = (logical[1] << 8) | logical[2]
    length = (logical[3] << 8) | logical[4]
    if len(logical) < 5 + length + 1:
        return None
    payload = bytes(logical[5 : 5 + length])
    checksum = logical[5 + length]

    x = param
    for b in logical[: 5 + length]:
        x ^= b
    if x != checksum:
        return None
    return cmd, payload


class _HidapiLink:
    """A hidapi (hid modul) köré épült szállítás (Windows / Linux / macOS)."""

    def __init__(self):
        self._dev = None
        self.path = None

    @staticmethod
    def list_paths():
        try:
            return [d.get("path") for d in hid.enumerate(VID, PID) or []]
        except Exception:
            return []

    def open(self, path):
        self._dev = hid.Device(path=path)
        self.path = path

    def write(self, report):
        self._dev.write(report)

    def read(self, timeout_ms):
        data = self._dev.read(REPORT_LEN, timeout_ms)
        return bytes(data) if data else None

    def close(self):
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
            self._dev = None


class HidLink:
    """hidapi réteg: az eszköz megkeresése, nyitás, reportok küldése/fogadása.

    Szállítás kiválasztása: hidapi, ha elérhető; Linuxon emellett a tiszta
    Python hidraw (rfid125k/hidrawlink.py) is próbálkozhat - a nyitásnál
    protokollpróbával (SetAutoRead + válasz) dől el, melyik csomópont valódi."""
    def __init__(self):
        self._link = None
        self.path = None

    @staticmethod
    def _factories():
        factories = []
        if hid is not None:
            factories.append(_HidapiLink)
        if HidRawLink is not None:
            factories.append(HidRawLink)
        return factories

    @staticmethod
    def enumerate_devices():
        paths = []
        if hid is not None:
            paths += [p for p in _HidapiLink.list_paths() if p]
        if enumerate_hidraw is not None:
            try:
                paths += list(enumerate_hidraw(VID, PID))
            except Exception:
                pass
        return paths

    @staticmethod
    def path_str(path):
        """Az eszközútvonal megjeleníthető alakja (Windows bájtok -> szöveg)."""
        if isinstance(path, bytes):
            try:
                return path.decode("utf-8", "replace")
            except Exception:
                return repr(path)
        return str(path)

    def open(self, path=None):
        candidates = [path] if path else self.enumerate_devices()
        if not candidates:
            raise DeviceNotFoundError(L("err.usb.notfound", VID, PID))
        for p in candidates:
            for factory in self._factories():
                link = factory()
                try:
                    link.open(p)
                    link.write(build_report(CMD.SET_AUTO_READ, b"\x00"))
                    data = link.read(800)
                    if data:
                        self._link = link
                        self.path = self.path_str(p)
                        return self.path
                    link.close()
                except Exception:
                    try:
                        link.close()
                    except Exception:
                        pass
        raise DeviceNotFoundError(L("err.iface.notfound", VID, PID))

    def write(self, report: bytes):
        if self._link is None:
            raise DeviceNotFoundError("Az eszköz nincs megnyitva.")
        self._link.write(report)

    def read(self, timeout_ms: int):
        """Egy report beolvasása; None, ha a timeout alatt nem érkezett adat."""
        if self._link is None:
            raise DeviceNotFoundError("Az eszköz nincs megnyitva.")
        return self._link.read(timeout_ms)

    def close(self):
        if self._link is not None:
            try:
                self._link.close()
            except Exception:
                pass
            self._link = None
