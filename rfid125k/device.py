"""HID-alapú RFID olvasó/író vezérlése a rögzített AA 55 protokollal.
Viselkedésileg a C# VendorDllDevice osztályt tükrözi (olvasási ciklus,
üres kártya felismerés, próbaírásos írhatóság-vizsgálat, írás/törlés/feloldás).
"""
import time
import threading
from dataclasses import dataclass, field
from enum import Enum

from . import card as card_mod
from .i18n import t as L
from .protocol import CMD, VID, PID, DeviceNotFoundError, HidLink, build_report, parse_report

PROBE_ID = bytes([0x12, 0x34, 0x56, 0x78, 0x90])          # 1234567890
ALT_PROBE_ID = bytes([0x00, 0x3A, 0xDE, 0x68, 0xB1])      # tartalék próbaérték
ZERO_ID = bytes(5)


class ReadStatus(Enum):
    NONE = "none"
    CARD = "card"
    BLANK = "blank"


class DeviceError(Exception):
    pass


@dataclass
class CardReadResult:
    status: ReadStatus
    card: card_mod.CardData = None


@dataclass
class CardInfo:
    card_present: bool
    card: card_mod.CardData
    is_blank: bool
    chip_description: str
    is_writable: bool
    message: str = None


class HidReaderDevice:
    """A valódi olvasó (VID 1A86:DD01) platformfüggetlen vezérlője."""

    def __init__(self, path=None, write_method="T4100", lock_after_write=False):
        self._path = path
        self._link = None
        self._io_lock = threading.Lock()
        self.write_method = write_method if write_method in ("T4100", "E4100", "EL4100") else "T4100"
        self.lock_after_write = lock_after_write

    # ---------- állapot ----------

    @property
    def device_name(self):
        suffix = f" | {HidLink.path_str(self._path)}" if self._path else ""
        return f"HID olvasó (VID 1A86:DD01){suffix}"

    @property
    def is_open(self):
        return self._link is not None

    @staticmethod
    def list_usb_devices():
        return [HidLink.path_str(d) for d in HidLink.enumerate_devices()]

    # ---------- nyitás / zárás ----------

    def open(self):
        link = HidLink()
        link.open(self._path)
        self._link = link
        self._path = link.path

    def close(self):
        if self._link is None:
            return
        try:
            self._write(CMD.SET_AUTO_READ, b"\x00")
            time.sleep(0.3)
        finally:
            try:
                self._link.close()
            finally:
                self._link = None

    # ---------- alacsony szintű műveletek ----------

    def _ensure_open(self):
        if self._link is None:
            raise DeviceError("Az eszköz nincs megnyitva!")

    def _write(self, cmd: int, payload: bytes):
        with self._io_lock:
            self._link.write(build_report(cmd, payload))

    def _exchange(self, cmd: int, payload: bytes, timeout_ms: int):
        """Parancs küldése és a hozzá tartozó válasz várása (más parancsok
        válaszait kiszűri). None, ha a timeout alatt nem érkezett válasz."""
        with self._io_lock:
            self._link.write(build_report(cmd, payload))
            deadline = time.monotonic() + timeout_ms / 1000.0
            while True:
                remaining_ms = (deadline - time.monotonic()) * 1000.0
                if remaining_ms <= 0:
                    return None
                data = self._link.read(max(1, int(remaining_ms)))
                if data is None:
                    continue
                parsed = parse_report(data)
                if parsed is None:
                    continue
                rcmd, rpayload = parsed
                if rcmd == cmd:
                    return rcmd, rpayload

    def _set_auto_read(self, enable: bool):
        try:
            self._exchange(CMD.SET_AUTO_READ, bytes([1 if enable else 0]), 2000)
        except DeviceNotFoundError:
            raise

    def _read_id_exchange(self, timeout_ms=2500):
        """Egy ReadIdCard kör. Visszaadja (ReadStatus, CardData|None)-t."""
        resp = self._exchange(CMD.READ_ID_CARD, b"", timeout_ms)
        if resp is None:
            return ReadStatus.NONE, None
        _, payload = resp
        if len(payload) < 6 or payload[0] != 0:
            return ReadStatus.NONE, None
        id5 = payload[1:6]
        if id5 == ZERO_ID:
            return ReadStatus.BLANK, None
        return ReadStatus.CARD, card_mod.CardData.from_bytes(id5)

    # ---------- kártyaolvasás ----------

    def read_card(self, cancel_event=None, overall_timeout=None):
        """Kártya várása (üres kártya = BlankCard). A C# ReadCardAsync
        műveleti sorát tükrözi: SetAutoRead(1), ciklus, SetAutoRead(0)."""
        self._ensure_open()
        self._set_auto_read(True)
        start = time.monotonic()
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise DeviceError(L("err.read.cancelled"))
                if overall_timeout is not None and time.monotonic() - start > overall_timeout:
                    return CardReadResult(ReadStatus.NONE)
                status, card = self._read_id_exchange()
                if status == ReadStatus.CARD:
                    return CardReadResult(status, card)
                if status == ReadStatus.BLANK:
                    return CardReadResult(status, None)
                time.sleep(0.2)
        finally:
            try:
                self._set_auto_read(False)
            except Exception:
                pass

    # ---------- írás ----------

    def write_card(self, target, method=None, mode=None):
        """Kártya írása. T4100/E4100: mode bájt + 5 bájt ID; EL4100: csak 5 bájt.
        Ha a készülék nem válaszol a timeout alatt, visszaolvasással ellenőrizünk
        (a valódi olvasó írása néha ACK nélkül is sikeres)."""
        self._ensure_open()
        method = (method or self.write_method).upper()
        if method == "EL4100":
            cmd = CMD.WRITE_EL4100
            payload = target.raw
        else:
            mode = 1 if self.lock_after_write else 0 if mode is None else mode
            cmd = CMD.WRITE_T4100 if method == "T4100" else CMD.WRITE_E4100
            payload = bytes([mode]) + target.raw

        resp = self._exchange(cmd, payload, 6000)
        if resp is not None:
            _, rpayload = resp
            if len(rpayload) >= 1 and rpayload[0] == 0:
                if self._verify_written(target):
                    return
                raise DeviceError(L("err.write.ineffective", target.hex_id))
            raise DeviceError(L("err.write.device", rpayload.hex().upper()))
        # Nincs ACK: visszaolvasással ellenőrizünk (a valódi olvasó írása néha
        # ACK nélkül is sikeres - pl. késői válasz).
        if self._verify_written(target):
            return
        raise DeviceError(L("err.write.noresponse"))

    def _verify_written(self, target: card_mod.CardData) -> bool:
        """Visszaolvasás-ellenőrzés írás után. Üres kártya a nulla ID-nek felel meg;
        ha a kártya épp nincs az olvasón, nem tudjuk ellenőrizni - elfogadjuk."""
        for _ in range(2):
            time.sleep(0.3)
            status, card = self._read_id_exchange(3000)
            if status == ReadStatus.CARD:
                return card.hex_id == target.hex_id
            if status == ReadStatus.BLANK:
                return target.raw == ZERO_ID
        return True

    # ---------- kártya állapota (írhatóság-vizsgálat próbaírással) ----------

    def get_card_info(self) -> CardInfo:
        self._ensure_open()
        res = self.read_card(overall_timeout=4.0)

        if res.status == ReadStatus.NONE:
            return CardInfo(False, None, False, "", False, L("cardinfo.nocard"))

        if res.status == ReadStatus.BLANK:
            probe = card_mod.CardData.from_bytes(PROBE_ID)
            writable = self._try_probe_write(probe)
            restored = True
            try:
                self.write_card(card_mod.CardData.from_bytes(ZERO_ID), method="T4100", mode=0)
            except DeviceError as ex:
                restored = False
                restore_msg = str(ex)
            message = None
            if not restored:
                message = L("cardinfo.probe.restore.warn", probe.hex_id, restore_msg)
            return CardInfo(
                True, None, True,
                L("cardinfo.t5577.blank") if writable else L("cardinfo.unknown.blank"),
                writable, message)

        current = res.card
        probe_bytes = ALT_PROBE_ID if current.raw == PROBE_ID else PROBE_ID
        is_writable = self._try_probe_write(card_mod.CardData.from_bytes(probe_bytes))

        message = None
        if is_writable:
            restored = self._try_restore(current)
            if not restored:
                message = L("cardinfo.original.restore.warn", current.hex_id, probe_bytes.hex().upper())

        return CardInfo(
            True, current, False,
            L("cardinfo.t5577") if is_writable else L("cardinfo.em4100.readonly"),
            is_writable, message)

    def _try_probe_write(self, probe: card_mod.CardData) -> bool:
        try:
            self.write_card(probe, method="T4100", mode=0)
        except DeviceError:
            return False
        time.sleep(0.3)
        status, card = self._read_id_exchange(3000)
        return status == ReadStatus.CARD and card.hex_id == probe.hex_id

    def _try_restore(self, original: card_mod.CardData) -> bool:
        for _ in range(2):
            try:
                self.write_card(original, method="T4100", mode=0)
            except DeviceError:
                continue
            time.sleep(0.3)
            status, card = self._read_id_exchange(3000)
            if status == ReadStatus.CARD and card.hex_id == original.hex_id:
                return True
        return False

    # ---------- törlés / feloldás ----------

    def erase_card(self):
        self._ensure_open()
        self.write_card(card_mod.CardData.from_bytes(ZERO_ID), method="T4100", mode=0)
        leftover = self.read_card(overall_timeout=3.0)
        if leftover.status == ReadStatus.CARD:
            raise DeviceError(L("err.erase.ineffective", leftover.card.hex_id))

    def unlock_card(self):
        self._ensure_open()
        self.write_card(card_mod.CardData.from_bytes(ZERO_ID), method="T4100", mode=0)
        leftover = self.read_card(overall_timeout=3.0)
        if leftover.status == ReadStatus.CARD:
            raise DeviceError(L("err.unlock.ineffective", leftover.card.hex_id))

    # ---------- diagnosztika ----------

    def get_out_format(self):
        resp = self._exchange(CMD.GET_OUT_FORMAT, b"\x00", 2000)
        if resp is None:
            raise DeviceError(L("err.noformat"))
        _, payload = resp
        return bytes(payload[1:])

    def set_beep(self, enable: bool):
        self._exchange(CMD.SET_BEEP, bytes([1 if enable else 0]), 2000)

    def set_led(self, enable: bool):
        self._exchange(CMD.SET_LED, bytes([1 if enable else 0]), 2000)

    def get_reader_info(self):
        devices = self.list_usb_devices()
        dev = "; ".join(devices) if devices else L("usb.notidentified")
        return L("reader.info.simple", VID, PID, dev)
