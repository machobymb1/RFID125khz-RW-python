# RFID 125 kHz Card Reader/Writer - Python version (cross-platform)

A fully featured, cross-platform port of the C# GUI (`RFID125k.Gui`):
card reading (HEX / DEC / 8H10D / Wiegand 26), card status inspection
(writability verified with a safe test write), writing
(T4100 / E4100 / EL4100), erasing, unlocking, lock-after-write,
diagnostics.

The device is **not** controlled through the vendor `IDReader.dll` but
directly over the HID protocol (hidapi), so it runs on Windows, Linux
and macOS.

## Installation

Requirements: Python 3.10+ (`tkinter` is included in the standard
install). The GUI uses the **CustomTkinter** module (installed via
`requirements.txt`: `pip install customtkinter`).

Windows (`start.bat` does all of this):

```bat
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

Linux (Debian / Ubuntu):

```sh
# 1. System packages (C build of the hid module and the tkinter GUI)
sudo apt update
sudo apt install -y python3 python3-venv python3-tk \
    libusb-1.0-0-dev libudev-dev gcc python3-dev

# 2. USB permissions (the user must be in the plugdev group!)
sudo install -m 0644 99-rfid125k.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
#   Unplug and plug the reader back in.

# 3. Run (creates venv + deps on first run)
./start.sh
```

Other distributions (package name equivalents): Fedora: `dnf install
libusb-devel libudev-devel gcc python3-devel tkinter`; Arch: `pacman -S
libusb systemd-libs gcc python python-tkinter`.

**Important:** on Linux the `hid` module requires a C build (libusb). If that
is unavailable or fails to build, the program does **not** break: it falls
back to the pure-Python hidraw transport (`rfid125k/hidrawlink.py`,
`/dev/hidraw*`, no libraries). The udev rule grants access for both
transports.

macOS:

```sh
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt   # hidapi is part of the OS (IOHIDManager)
./.venv/bin/python main.py
```

On Windows, `hidapi.dll` (x64) is required next to the program for the
`hid` module; the program loads it automatically. If it is missing,
download it from: https://github.com/libusb/hidapi/releases
(hidapi-win.zip, `x64/hidapi.dll`).

## Running

- Windows: `start.bat`
- Linux: `./start.sh` (or directly: `.venv/bin/python main.py`)
- Other: `python main.py`

If the reader is not found, the program starts in simulated mode (for
demo/testing). Use `--simulate` to force simulated mode.

On Linux the GUI needs a working X11/Wayland session; on a headless
server the program cannot open a window.

## Configuration

### `config.json` (the selected language - same as the C# version)

The language selected in the GUI "Language" menu persists across restarts:
the program saves it to `config.json` in the program folder (falling back
to appdata if not writable: Windows `%APPDATA%\RFID125k`, Linux
`~/.config/RFID125k`) - exactly like the .NET application.

```json
{
  "language": "hu"
}
```

### `rfid125k.json` (device settings, in the program folder)

```json
{
  "devicePath": null,
  "writeMethod": "T4100",
  "lockAfterWrite": false,
  "language": "hu"
}
```

- `devicePath`: a specific HID device path (usually not needed; the
  program finds the responsive interface by itself).
- `writeMethod`: `T4100` | `E4100` | `EL4100`
- `lockAfterWrite`: lock the card after writing.
- `language`: only used as a fallback when there is no `config.json`
  (for backward compatibility). It can also be switched at runtime from
  the "Language" menu - the choice is saved to `config.json`.

## Adding / translating languages

The texts live in JSON dictionaries in the program folder (`lang.hu.json`,
`lang.en.json`). To add a language: copy `lang.en.json` to `lang.xx.json`
(two-letter code), translate the values, and put the code into the
configuration. The `{0}`, `{1:X4}` ... format placeholders are identical
in .NET and Python. The keys are shared between the two versions (C# and
Python) - one dictionary works in both (the C# build copies the Python
`lang.*.json` files).

## Structure

| File | C# counterpart | Content |
|---|---|---|
| `rfid125k/protocol.py` | (n/a; reverse-engineered) | AA 55 HID protocol + hidapi transport |
| `rfid125k/hidrawlink.py` | (n/a) | Linux fallback: pure-Python /dev/hidraw driver |
| `rfid125k/i18n.py` | `Localization.cs` | language resources (lang.*.json) |
| `rfid125k/device.py` | `VendorDllDevice.cs` | device control (read, write, test write, erase) |
| `rfid125k/card.py` | `CardData.cs` | card data (HEX/DEC/8H10D/Wiegand26) |
| `rfid125k/em4100.py` | `Em4100Codec.cs` | EM4100 frame / T5577 block encoding |
| `rfid125k/simulated.py` | `SimulatedDevice.cs` | simulation without hardware |
| `rfid125k/gui.py` | `MainForm.cs` | CustomTkinter GUI |
| `main.py` | `Program.cs` + `RfidDeviceFactory.cs` | entry point, configuration |

## The wire protocol (dynamically captured)

The IDReader.dll is 32-bit; the protocol was worked out with an
IAT-hook-based recorder (intercepting WriteFile/ReadFile), and the
command codes were confirmed by disassembling the DLL:

- 64-byte HID report, report ID `0x01` (VID 1A86 / PID DD01, CH341).
- TX: `01 AA 55 00 00 <cmd_hi> <cmd_lo> 00 <len> <payload...> <xor> CC...`
- RX: `01 AA 55 11 12 <cmd_hi> <cmd_lo> 00 <len> <00> <data...> <xor>`
- checksum = XOR of the `param..payload` bytes; `0xAA` bytes appear on
  the wire as `AA 00` (escape), the escape byte is not part of the checksum.
- Commands: SetAutoRead `0x0801`, SetLed `0x0802`, SetBeep `0x0803`,
  SetFrequency `0x0804`, GetOutFormat `0x080B`, ReadIdCard `0x0809`,
  WriteEL4100 `0x0810` (5 bytes), WriteT4100 `0x0811` (mode + 5 bytes),
  WriteE4100 `0x0812` (mode + 5 bytes).
- ReadIdCard reply: `00 <5-byte ID>`; blank card: all-zero ID;
  no card: no reply.
- The write reply is slow (~1.7-4.5 s); if none arrives, the program
  verifies by reading back. For read-only EM4100 cards the device sends
  an ACK, but the content does not change - the read-back check filters
  that out.

## Helper tool: HID device identification (`hid_scan.py`)

Lists the connected HID devices using the `hid` (hidapi) module - e.g. to
check what is on the machine before looking for the reader. The RFID
reader (VID 1A86, PID DD01) is marked specially.

```
python hid_scan.py               # brief list (all HID devices)
python hid_scan.py -d            # detailed list (path, manufacturer, serial, ...)
python hid_scan.py -f 1A86:DD01  # only the given device, in detail
```