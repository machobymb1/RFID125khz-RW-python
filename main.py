"""RFID 125 kHz kártyaolvasó/író - platformfüggetlen Python változat.

Konfiguráció:
- config.json: a felületen választott nyelv ("language": "hu" | "en"),
  a C# változathoz hasonlóan a program mappájába mentve (appdata-ra esik
  vissza, ha oda nem írható).
- rfid125k.json (a program mappájában): eszközbeállítások; a "language"
  mező csak akkor számít, ha nincs config.json.

rfid125k.json példa:
{
  "devicePath": null,          // opcionális: konkrét HID eszközútvonal
  "writeMethod": "T4100",      // T4100 | E4100 | EL4100
  "lockAfterWrite": false,
  "language": "hu"             // hu | en (csak visszaesés, ha nincs config.json)
}

Függőség: hid (hidapi). Telepítés: pip install -r requirements.txt
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__ or sys.argv[0]))
sys.path.insert(0, BASE_DIR)

from rfid125k.device import DeviceNotFoundError, HidReaderDevice  # noqa: E402
from rfid125k.gui import App  # noqa: E402
from rfid125k.i18n import load_config_language  # noqa: E402
from rfid125k.i18n import load_language  # noqa: E402
from rfid125k.i18n import t as L  # noqa: E402
from rfid125k.simulated import SimulatedDevice  # noqa: E402


def load_config():
    path = os.path.join(BASE_DIR, "rfid125k.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except Exception:
        return {}


def create_device(cfg, force_simulated=False):
    """A C# RfidDeviceFactory viselkedését tükrözi: ha az eszköz nyitható,
    a valódi olvasót használjuk, különben szimulált mód (hardver nélkül)."""
    write_method = str(cfg.get("writeMethod", "T4100")).upper()
    if write_method not in ("T4100", "E4100", "EL4100"):
        write_method = "T4100"
    lock = bool(cfg.get("lockAfterWrite", False))
    if force_simulated:
        return SimulatedDevice(), "simulated"
    try:
        device = HidReaderDevice(
            path=cfg.get("devicePath"),
            write_method=write_method,
            lock_after_write=lock,
        )
        device.open()
        return device, "real"
    except DeviceNotFoundError:
        return SimulatedDevice(), "simulated"
    except Exception:
        return SimulatedDevice(), "simulated"


def main():
    cfg = load_config()
    load_language(load_config_language())
    device, mode = create_device(cfg, force_simulated="--simulate" in sys.argv)
    app = App(device, device_mode=mode)
    if mode != "real":
        app.log(L("main.simulated.warn"))
    app.mainloop()


if __name__ == "__main__":
    main()
