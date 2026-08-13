"""Egy 125 kHz-es EM4100 kompatibilis kártya adatai. (Port: CardData.cs)"""
from dataclasses import dataclass

from . import em4100

MAX_ID_VALUE = (1 << 40) - 1
DEFAULT_UPPER_BYTE = 0x45  # a gyári kártyákkal egyező fix felső bájt írásnál


def _count_bits(v: int) -> int:
    c = 0
    while v:
        c += v & 1
        v >>= 1
    return c


@dataclass(frozen=True)
class Wiegand26:
    """Wiegand 26 kód a demo program konvenciója szerint:
    facility kód + kártyaszám, ahol az érték = facility * 100000 + kártyaszám."""

    value: int
    facility_code: int
    card_number: int

    @staticmethod
    def from_em4100(raw: bytes) -> "Wiegand26":
        """EM4100 5 bájtos ID -> Wiegand 26 (a demo program kimenetét követve).
        A live teszt alapján (kártya 45 00 71 84 05 -> WG26: 11333797):
        facility = raw[2], kártyaszám = (raw[3] << 8) | raw[4]."""
        facility = raw[2]
        card_number = (raw[3] << 8) | raw[4]
        demo_value = facility * 100000 + card_number
        return Wiegand26(demo_value, facility, card_number)

    def to_binary_string(self) -> str:
        """A valódi 26 bites Wiegand bittérkép (páros/páratlan paritásbitekkel)."""
        data = (self.facility_code << 16) | self.card_number
        even_parity = _count_bits((data >> 12) & 0xFFF) % 2
        odd_parity = 1 if _count_bits(data & 0xFFF) % 2 == 0 else 0
        w = (even_parity << 25) | (data << 1) | odd_parity
        return format(w, "026b")

    def __str__(self) -> str:
        return f"{self.value} (facility: {self.facility_code}, kártyaszám: {self.card_number})"


class CardData:
    def __init__(self, hex_id: str, raw: bytes):
        self.hex_id = hex_id
        self.raw = bytes(raw)

    # --- konstruktorok ---

    @classmethod
    def from_hex_id(cls, hex_id: str) -> "CardData":
        normalized = em4100.normalize(hex_id)
        if not em4100.is_valid_id(normalized):
            raise ValueError("A kártya ID-nak pontosan 10 hexadecimális karakternek kell lennie.")
        return cls(normalized, em4100.id_to_bytes(normalized))

    @classmethod
    def from_bytes(cls, raw) -> "CardData":
        raw = bytes(raw)
        if len(raw) != 5:
            raise ValueError("A nyers kártyaadatnak pontosan 5 bájtnak kell lennie.")
        return cls(raw.hex().upper(), raw)

    @classmethod
    def from_decimal_id(cls, decimal_id: str) -> "CardData":
        if not cls.is_valid_decimal_id(decimal_id):
            raise ValueError("Érvénytelen kártya ID! Egész szám 0 és 1099511627775 (5 bájt) között.")
        value = int(decimal_id.strip())
        raw = value.to_bytes(5, "big")
        return cls(raw.hex().upper(), raw)

    @classmethod
    def from_eight_hex_ten_decimal(cls, value_8h10d: str) -> "CardData":
        """8H10D értékből (0..4294967295). A felső bájt (raw[0]) fix 0x45,
        az alsó 4 bájt a megadott 32 bites érték."""
        if not cls.is_valid_eight_hex_ten_decimal(value_8h10d):
            raise ValueError("Érvénytelen 8H10D érték! Csak számjegyek, legfeljebb 10 jegy, 0 és 4294967295 között.")
        v = int(value_8h10d.strip())
        raw = bytes([DEFAULT_UPPER_BYTE, (v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])
        return cls(raw.hex().upper(), raw)

    # --- érvényesség ---

    @staticmethod
    def is_valid_decimal_id(decimal_id: str) -> bool:
        s = (decimal_id or "").strip()
        if not s or len(s) > 13 or not s.isdigit():
            return False
        return int(s) <= MAX_ID_VALUE

    @staticmethod
    def is_valid_eight_hex_ten_decimal(value: str) -> bool:
        s = (value or "").strip()
        if not s or len(s) > 10 or not s.isdigit():
            return False
        return int(s) <= 0xFFFFFFFF

    # --- számított értékek ---

    @property
    def decimal_id(self) -> str:
        return str(int.from_bytes(self.raw, "big"))

    @property
    def eight_hex_ten_decimal(self) -> str:
        """A demo program '8H10D' formátuma: az alsó 32 bit (raw[1..4])
        decimális értéke, 10 számjeggyel kiegészítve."""
        value = int.from_bytes(self.raw[1:5], "big")
        return str(value).rjust(10, "0")

    @property
    def wiegand26(self) -> Wiegand26:
        return Wiegand26.from_em4100(self.raw)

    def __str__(self) -> str:
        return self.hex_id
