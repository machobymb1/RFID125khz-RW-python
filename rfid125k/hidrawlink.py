"""Tiszta Python hidraw illesztő Linuxhoz (fallback a hidapi nélkül).

A hidapi (`hid` pip modul) Linuxon C-fordítást igényel (libusb). Ha az nem
érhető el, a program a kernel hidraw felületét közvetlenül használja:
a /dev/hidraw* csomópontokra írva/olvasva a rendszer a készülék HID reportjait
továbbítja - azonos bájtformátumban, mint Windows-on a ReadFile/WriteFile
(a 64 bájtos report az 0x01 report ID-val együtt).

Csak Linuxon működik (/dev/hidraw*, ioctl HIDIOCGRAWINFO).
"""
import fcntl
import glob
import os
import select
import struct

HIDIOCGRAWINFO = 0x80084803  # _IOWR('H', 0x03, struct hidraw_devinfo)
_HIDRAW_DEVINFO = struct.Struct("<IHH")  # bustype, vendor, product


class HidRawError(Exception):
    pass


def _devinfo(path):
    """(bustype, vendor, product) az adott /dev/hidraw* csomópontról."""
    try:
        with open(path, "rb") as fh:
            buf = fcntl.ioctl(fh, HIDIOCGRAWINFO, _HIDRAW_DEVINFO.pack(0, 0, 0))
        return _HIDRAW_DEVINFO.unpack(buf)
    except OSError:
        return None


def enumerate_hidraw(vendor, product):
    """Az adott VID/PID-hez tartozó hidraw csomópontok (rendezve)."""
    for path in sorted(glob.glob("/dev/hidraw*")):
        info = _devinfo(path)
        if info is not None and info[1] == vendor and info[2] == product:
            yield path


class HidRawLink:
    """Egy /dev/hidraw* csomópont (a protocol.HidLink szállítási felületével)."""

    def __init__(self, path=None):
        self.path = path
        self._fd = None

    def open(self, path=None):
        path = path or self.path
        if not path:
            raise HidRawError("Nincs hidraw eszközútvonal.")
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError as ex:
            raise HidRawError(f"A {path} nem nyitható: {ex}") from ex
        try:
            os.set_blocking(fd, False)
        except OSError:
            pass
        self._fd = fd
        self.path = path

    def write(self, data):
        if self._fd is None:
            raise HidRawError("Az eszköz nincs megnyitva.")
        return os.write(self._fd, bytes(data))

    def read(self, timeout_ms=0):
        """Egy report beolvasása; None, ha a timeout alatt nem érkezett adat."""
        if self._fd is None:
            raise HidRawError("Az eszköz nincs megnyitva.")
        r, _, _ = select.select([self._fd], [], [], timeout_ms / 1000.0)
        if not r:
            return None
        return os.read(self._fd, 64)

    def close(self):
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
