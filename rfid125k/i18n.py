"""Nyelvi erőforrások.

A fordítások JSON-szótárakban vannak a program mappájában (lang.hu.json,
lang.en.json ...). A kulcsok a C# változattal közösek; a formátum-
helyettesítők ({0}, {1:X4} ...) Python (str.format) és .NET (string.Format)
formátumban is működnek.

Ismeretlen/fordítatlan kulcsra az angoltól eltérő nyelveken a magyar szöveg
esik vissza; ha az sincs, a kulcs neve jelenik meg.
A felületen választott nyelv a program mappájában lévő config.json-ba
mentődik (appdata-ba esik vissza, ha oda nem írható) - a C# változattal
azonos módon.
"""
import json
import os
import sys

LANGUAGES = {"hu": "Magyar", "en": "English"}

_current = "hu"
_strings: dict = {}
_fallback: dict = {}


def _program_dir():
    """A program mappája: ahol az rfid125k csomag mellett a konfigurációk
    (rfid125k.json, config.json) és a lang.*.json erőforrások vannak."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    if os.path.isdir(os.path.join(root, "rfid125k")):
        return root
    script = os.path.abspath(sys.argv[0] or ".")
    return os.path.dirname(script) if os.path.isfile(script) else here


def _config_paths():
    """A config.json keresési/írási helyei: program mappa, majd appdata
    (a C# Localization.ConfigPaths párja: Windows APPDATA, egyébként
    XDG_CONFIG_HOME / ~/.config)."""
    paths = [os.path.join(_program_dir(), "config.json")]
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            paths.append(os.path.join(base, "RFID125k", "config.json"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        if base:
            paths.append(os.path.join(base, "RFID125k", "config.json"))
    return paths


def load_config_language():
    """A config.json-ból a mentett nyelv. Ha egyik helyen sincs ilyen fájl,
    a régi rfid125k.json "language" mezője következik (visszafelé kompatibilitás),
    végül "hu"."""
    for path in _config_paths():
        try:
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                continue
            value = data.get("language")
            if isinstance(value, str):
                return value
        except Exception:
            continue
    try:
        with open(os.path.join(_program_dir(), "rfid125k.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("language"), str):
            return data["language"]
    except Exception:
        pass
    return "hu"


def save_config_language(language):
    """A nyelv mentése config.json-ba: program mappa, ha oda nem írható,
    akkor appdata (a C# Localization.SaveConfigLanguage párja)."""
    text = json.dumps({"language": language}, indent=2, ensure_ascii=False) + "\n"
    for path in _config_paths():
        try:
            directory = os.path.dirname(path)
            if directory and not os.path.isdir(directory):
                os.makedirs(directory, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)
            return
        except Exception:
            continue


def _resource_paths(code):
    here = os.path.dirname(os.path.abspath(__file__))                     # rfid125k/
    root = os.path.dirname(here)                                          # python/
    script = os.path.dirname(os.path.abspath(sys.argv[0] or "."))
    return [
        os.path.join(root, f"lang.{code}.json"),
        os.path.join(root, "lang", f"lang.{code}.json"),
        os.path.join(here, f"lang.{code}.json"),
        os.path.join(script, f"lang.{code}.json"),
    ]


def _load(code, target):
    for path in _resource_paths(code):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                target.update({str(k): str(v) for k, v in data.items()})
                return True
        except Exception:
            continue
    return False


def load_language(code="hu"):
    """A nyelv beállítása ("hu", "en"...). Ellenőrzött kéttagú kód; ismeretlen
    nyelvnél magyarra esik vissza. Visszaadja az aktív nyelvet."""
    global _current
    code = (code or "hu").strip().lower()
    if len(code) != 2:
        code = "hu"
    _strings.clear()
    _fallback.clear()
    if code != "hu":
        _load("hu", _fallback)
    if not _load(code, _strings):
        code = "hu"
        _load("hu", _strings)
    _current = code
    return code


def current():
    return _current


def t(key, *args):
    """A kulcshoz tartozó szöveg az aktuális nyelven (esetleg {0} ... helyettesítőkkel)."""
    text = _strings.get(key) or _fallback.get(key) or key
    if not args:
        return text
    try:
        return text.format(*args)
    except Exception:
        return text