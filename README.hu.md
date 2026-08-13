# RFID 125 kHz kártyaolvasó/író - Python változat (platformfüggetlen)

A C# GUI (`RFID125k.Gui`) teljes funkcionalitású, platformfüggetlen portja:
kártyaolvasás (HEX / DEC / 8H10D / Wiegand 26), kártya állapot vizsgálat
(írhatóság biztonságos próbaírással), írás (T4100 / E4100 / EL4100),
törlés, feloldás, lezárás-írás után, diagnosztika.

Az eszközt **nem a gyártói IDReader.dll-en** keresztül vezérli, hanem közvetlenül
a HID protokollon (hidapi), ezért Windows, Linux és macOS rendszereken is fut.

## Telepítés

Követelmény: Python 3.10+ (a `tkinter` a szabványos telepítésben van).
A GUI a **CustomTkinter** modult használja (a `requirements.txt` telepíti:
`pip install customtkinter`).

Windows (a `start.bat` mindezt elvégzi):

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

Linux (Debian / Ubuntu):

```sh
# 1. Rendszercsomagok (a hid modul C-fordítása és a tkinter GUI)
sudo apt update
sudo apt install -y python3 python3-venv python3-tk \
    libusb-1.0-0-dev libudev-dev gcc python3-dev

# 2. USB-engedélyek (a felhasználónak a plugdev csoportban kell lennie!)
sudo install -m 0644 99-rfid125k.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
#   Húzd ki és dugd vissza az olvasót USB-ből.

# 3. Indítás (első futtatáskor venv + függőségek)
./start.sh
```

Egyéb disztribúciók (a csomagnevek megfelelői): Fedora: `dnf install
libusb-devel libudev-devel gcc python3-devel tkinter`; Arch: `pacman -S libusb
systemd-libs gcc python python-tkinter`.

**Fontos:** a `hid` modul Linuxon C-fordítást igényel (libusb). Ha az nem
érhető el vagy nem fordul le, a program **nem hibásodik meg**: a tiszta Python
hidraw háttérrel működik tovább (`rfid125k/hidrawlink.py`, `/dev/hidraw*`,
könyvtár nélkül). A udev-szabály mindkét háttérhez jogosultságot ad.

macOS:

```sh
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt   # a hidapi a rendszer része (IOHIDManager)
./.venv/bin/python main.py
```

Windows-on a program mappájában lévő `hidapi.dll` (x64) szükséges a `hid` modulhoz;
a program automatikusan betölti. Ha nincs ott, töltsd le:
https://github.com/libusb/hidapi/releases (hidapi-win.zip, `x64/hidapi.dll`).

## Futtatás

- Windows: `start.bat`
- Linux: `./start.sh` (vagy közvetlenül: `.venv/bin/python main.py`)
- Egyéb: `python main.py`

Ha az olvasó nem található, a program szimulált módban indul (bemutató / teszt
céljára). A `--simulate` kapcsolóval kényszeríthető a szimulált mód.

Linux alatt a GUI-hoz működő X11/Wayland munkamenet kell; fej nélküli
szerveren a program nem tud ablakot nyitni.

## Konfiguráció

### `config.json` (a választott nyelv - a C# változattal azonos módon)

A GUI "Nyelv" menüjében választott nyelv indulás után is megmarad: a program
a `config.json`-ba menti a program mappájában (ha oda nem írható, appdata-ra
esik vissza: Windows `%APPDATA%\RFID125k`, Linux `~/.config/RFID125k`) -
pontosan úgy, ahogy a .NET alkalmazás teszi.

```json
{
  "language": "hu"
}
```

### `rfid125k.json` (eszközbeállítások, a program mappájában)

```json
{
  "devicePath": null,
  "writeMethod": "T4100",
  "lockAfterWrite": false,
  "language": "hu"
}
```

- `devicePath`: konkrét HID eszközútvonal (általában nem szükséges, a program
  magától megtalálja a válaszoló interfészt).
- `writeMethod`: `T4100` | `E4100` | `EL4100`
- `lockAfterWrite`: írás után kártyalezárás.
- `language`: csak visszaesésként számít, ha nincs `config.json` (a
  korábbi viselkedés megőrzésére). A GUI "Nyelv" menüjében futás közben is
  váltható - a választás a `config.json`-ba mentődik.

## Nyelvek hozzáadása / fordítása

A szövegek JSON-szótárakban vannak a program mappájában (`lang.hu.json`,
`lang.en.json`). Új nyelv: másold a `lang.en.json`-t `lang.xx.json`-re
(kétjegyű nyelvkód), fordítsd le a kulcsok értékeit, és a kódot írd be a
konfigurációba. A `{0}`, `{1:X4}` ... formátumhelyettesítők a .NET és a
Python esetén is azonosak. A kulcsok a két változat (C# és Python) között
közösek - egy szótár mindkettőben működik (a C# fordítás a Python
`lang.*.json` fájlait másolja a buildben).

## Szerkezet

| Fájl | C# megfelelője | Tartalom |
|---|---|---|
| `rfid125k/protocol.py` | (nincs; RE alapján) | AA 55 HID protokoll + hidapi réteg |
| `rfid125k/hidrawlink.py` | (nincs) | Linux fallback: tiszta Python /dev/hidraw illesztő |
| `rfid125k/i18n.py` | `Localization.cs` | nyelvi erőforrások (lang.*.json) |
| `rfid125k/device.py` | `VendorDllDevice.cs` | eszközvezérlés (olvasás, írás, próbaírás, törlés) |
| `rfid125k/card.py` | `CardData.cs` | kártyaadatok (HEX/DEC/8H10D/Wiegand26) |
| `rfid125k/em4100.py` | `Em4100Codec.cs` | EM4100 keret / T5577 blokk kódolás |
| `rfid125k/simulated.py` | `SimulatedDevice.cs` | hardver nélküli szimuláció |
| `rfid125k/gui.py` | `MainForm.cs` | CustomTkinter GUI |
| `main.py` | `Program.cs` + `RfidDeviceFactory.cs` | belépési pont, konfiguráció |

## A vezetéki protokoll (dinamikusan rögzítve)

Az IDReader.dll 32 bites, a protokollt egy IAT-hook-alapú rögzítővel
(szereplő: WriteFile/ReadFile) fejtettük meg, a parancskódokat a DLL
disassembly-je igazolta:

- 64 bájtos HID report, report ID `0x01` (VID 1A86 / PID DD01, CH341).
- TX: `01 AA 55 00 00 <cmd_hi> <cmd_lo> 00 <len> <payload...> <xor> CC...`
- RX: `01 AA 55 11 12 <cmd_hi> <cmd_lo> 00 <len> <00> <data...> <xor>`
- checksum = a `param..payload` bájtok XOR-ja; `0xAA` bájtok a vezetéken
  `AA 00`-ként (escape), az escape bájt nincs a checksumban.
- Parancsok: SetAutoRead `0x0801`, SetLed `0x0802`, SetBeep `0x0803`,
  SetFrequency `0x0804`, GetOutFormat `0x080B`, ReadIdCard `0x0809`,
  WriteEL4100 `0x0810` (5 bájt), WriteT4100 `0x0811` (mode + 5 bájt),
  WriteE4100 `0x0812` (mode + 5 bájt).
- ReadIdCard válasz: `00 <5 bájt ID>`; üres kártya: csupa nulla ID;
  nincs kártya: nincs válasz.
- Az írási válasz lassú (~1,7-4,5 s); ha nem érkezik, a program
visszaolvasással ellenőriz. A csak olvasásra való EM4100 kártyára az
  eszköz ACK-ot ad, de a tartalom nem változik - ezt a visszaolvasás kiszűri.

## Segédprogram: HID eszközök azonosítása (`hid_scan.py`)

A csatlakoztatott HID eszközök listázása a `hid` (hidapi) modullal - pl.
annak ellenőrzésére, mi van a gépen, mielőtt az olvasót keressük. Az RFID
olvasó (VID 1A86, PID DD01) külön jelölést kap.

```
python hid_scan.py               # rövid lista (összes HID eszköz)
python hid_scan.py -d            # részletes lista (útvonal, gyártó, sorozatszám, ...)
python hid_scan.py -f 1A86:DD01  # csak az adott eszköz, részletesen
```
