#!/bin/sh
# RFID 125 kHz kártyaolvasó/író - Linux indító.
# Első futtatáskor létrehozza a virtuális környezetet és telepíti a függőségeket.
# Használat: ./start.sh  (vagy: ./start.sh --simulate)
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    echo "Virtuális környezet létrehozása..."
    python3 -m venv .venv
    ./.venv/bin/pip install -r requirements.txt \
        || echo "FIGYELEM: a hid modul nem települt (C-fordítás szükséges hozzá)." \
           "A program a tiszta Python hidraw háttérrel is működik."
fi

exec ./.venv/bin/python main.py "$@"
