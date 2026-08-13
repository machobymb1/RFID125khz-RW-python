"""Hardver nélküli szimuláció: bemutató és tesztelés céljára. (Port: SimulatedDevice.cs)"""
import random
import threading
import time

from . import card as card_mod
from .device import CardInfo, CardReadResult, ReadStatus
from .i18n import t as L
from .protocol import VID, PID

class SimulatedDevice:
    def __init__(self):
        self._rng = random.Random()
        self.is_open = False
        self._timer = None
        self._card_presented = []
        self.write_method = "T4100"
        self.lock_after_write = False

    @property
    def device_name(self):
        return L("sim.name")

    def on_card_presented(self, handler):
        self._card_presented.append(handler)

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def read_card(self, cancel_event=None, overall_timeout=None):
        time.sleep(1.0)
        card = self._random_card()
        for handler in self._card_presented:
            try:
                handler(card)
            except Exception:
                pass
        return CardReadResult(ReadStatus.CARD, card)

    def write_card(self, target, method=None, mode=None):
        for handler in self._card_presented:
            try:
                handler(target)
            except Exception:
                pass

    def erase_card(self):
        pass

    def unlock_card(self):
        pass

    def get_card_info(self) -> CardInfo:
        return CardInfo(True, None, False, L("sim.cardinfo"), True, None)

    def get_out_format(self):
        return bytes([0xFF] * 13)

    def set_beep(self, enable: bool):
        pass

    def set_led(self, enable: bool):
        pass

    def list_usb_devices(self):
        return []

    def get_reader_info(self):
        return L("sim.readerinfo", VID, PID)

    def _random_card(self):
        raw = bytearray(self._rng.randbytes(5))
        raw[0] &= 0x0F
        return card_mod.CardData.from_bytes(bytes(raw))
