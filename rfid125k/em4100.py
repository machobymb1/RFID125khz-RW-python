"""EM4100 kódolás: 10 hexadecimális karakteres kártya ID (5 bájt),
EM4100 adatkeret és T5577 blokkok előállítása. (Port: Em4100Codec.cs)
"""


def normalize(hex_id: str) -> str:
    return hex_id.strip().upper()


def is_valid_id(hex_id: str) -> bool:
    if len(hex_id) != 10:
        return False
    try:
        int(hex_id, 16)
        return True
    except ValueError:
        return False


def id_to_bytes(hex_id: str) -> bytes:
    raw = bytearray(5)
    for i in range(5):
        raw[i] = int(hex_id[i * 2 : i * 2 + 2], 16)
    return bytes(raw)


def build_frame(id5: bytes) -> int:
    """A 64 bites EM4100 keret: 9 darab '1' fejléc, 10 x (4 adatbit + 1
    oszlopparitás), 1 stop bit (0), majd 4 sorparitás bit."""
    nibbles = []
    for b in id5:
        nibbles.append((b >> 4) & 0x0F)
        nibbles.append(b & 0x0F)

    frame = 0
    bit = 0

    for _ in range(9):
        frame |= 1 << bit
        bit += 1

    for g in range(10):
        for b in range(3, -1, -1):
            if nibbles[g] & (1 << b):
                frame |= 1 << bit
            bit += 1
        column_parity = nibbles[g] ^ (nibbles[g] >> 1) ^ (nibbles[g] >> 2) ^ (nibbles[g] >> 3)
        if column_parity & 1:
            frame |= 1 << bit
        bit += 1

    bit += 1  # stop bit, 0

    for r in range(4):
        row_parity = 0
        for g in range(10):
            row_parity ^= (nibbles[g] >> r) & 1
        if row_parity:
            frame |= 1 << bit
        bit += 1

    return frame


def build_t5577_blocks(hex_id: str):
    """T5577 chipre írandó blokkok EM4100 kompatibilis módban.
    Blokk 0: ismert EM4100 kompatibilis konfiguráció (Manchester, RF/64).
    Blokk 1-2: a 64 bites EM4100 keret. Blokk 3-4: üres."""
    frame = build_frame(id_to_bytes(hex_id))
    return [
        0x00148040,
        frame & 0xFFFFFFFF,
        (frame >> 32) & 0xFFFFFFFF,
        0x00000000,
        0x00000000,
    ]
