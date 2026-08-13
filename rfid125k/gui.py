"""CustomTkinter GUI - a C# MainForm portja (azonos felépítés; többnyelvű).

A nyelv a felső "Nyelv" legördülő menüben futás közben is váltható; a
választás a C# változathoz hasonlóan config.json-ba mentődik (program mappa,
appdata visszaeséssel), és abból is jön induláskor.
"""
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from . import card as card_mod
from .device import DeviceError, ReadStatus
from .i18n import LANGUAGES, current as lang_current, load_language as set_language, save_config_language, t as L

ICON_FILE = "rfid125k.ico"
LANG_BY_NAME = {name: code for code, name in LANGUAGES.items()}

WRITE_METHODS = ["T4100", "E4100", "EL4100"]
METHOD_DESC_KEYS = {0: "method.desc.t4100", 1: "method.desc.e4100", 2: "method.desc.el4100"}
METHOD_LABEL_KEYS = ["cmb.method.t4100", "cmb.method.e4100", "cmb.method.el4100"]

ctk.set_appearance_mode("system")


class App(ctk.CTk):
    def __init__(self, device, device_mode="real"):
        super().__init__()
        self._device = device
        self._device_mode = device_mode
        self._queue = queue.Queue()
        self._cancel_event = None
        self._language_var = ctk.StringVar(value=lang_current())
        self._method_var = None
        self._last_card = None
        self._state_text = None
        self._opt_method = None

        self.geometry("580x650")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._set_app_icon()
        self._apply_language()
        self._open_device()
        self.after(100, self._poll_queue)

    # ---------- nyelv ----------

    def _on_language_selected(self, name):
        code = LANG_BY_NAME.get(name)
        if code:
            self._change_language(code)

    def _change_language(self, code):
        set_language(code)
        save_config_language(code)
        self._apply_language()

    def _apply_language(self):
        self.title(L("app.title"))
        self._lang_menu.set(LANGUAGES[lang_current()])
        self._lbl_device.configure(text=L("device.connected", self._device.device_name))
        self._grp_read_title.configure(text=L("grp.read"))
        self._grp_write_title.configure(text=L("grp.write"))
        self._lbl_id.configure(text=L("lbl.id"))
        self._lbl_method.configure(text=L("lbl.method"))
        self._chk_lock_widget.configure(text=L("chk.lock"))
        self._lbl_log.configure(text=L("lbl.log"))
        self._btn_read.configure(text=L("btn.read"))
        self._btn_diag.configure(text=L("btn.diagnostics"))
        self._btn_cardinfo.configure(text=L("btn.cardinfo"))
        self._btn_write.configure(text=L("btn.write"))
        self._btn_erase.configure(text=L("btn.erase"))
        self._btn_unlock.configure(text=L("btn.unlock"))
        self._rebuild_method_menu()
        self._on_method_changed()
        if self._last_card is not None:
            self._show_card(self._last_card)
        else:
            self._clear_card_labels()
            if self._state_text is not None:
                self._set_state(L(self._state_text))
            else:
                self._set_state(L("lbl.chip"))
        self._validate_id_input()

    # ---------- UI felépítés ----------

    def _build_ui(self):
        pad = {"padx": 16, "pady": 4}
        f = ctk.CTkFrame(self)
        f.pack(fill="both", expand=True, **pad)

        top = ctk.CTkFrame(f, fg_color="transparent")
        top.pack(fill="x", pady=(0, 6))
        self._lbl_device = ctk.CTkLabel(top, anchor="w", justify="left")
        self._lbl_device.pack(side="left", fill="x", expand=True)
        self._lang_menu = ctk.CTkOptionMenu(top, width=130, values=list(LANGUAGES.values()),
                                            command=self._on_language_selected)
        self._lang_menu.pack(side="right")

        # --- Kártyaolvasás ---
        self._grp_read = ctk.CTkFrame(f)
        self._grp_read.pack(fill="x", pady=4)
        self._grp_read_title = ctk.CTkLabel(self._grp_read, anchor="w", font=ctk.CTkFont(weight="bold"))
        self._grp_read_title.grid(row=0, column=0, columnspan=3, sticky="we", padx=10, pady=(8, 0))
        self._btn_read = ctk.CTkButton(self._grp_read, width=150, command=self._on_read_click)
        self._btn_read.grid(row=1, column=0, padx=8, pady=(4, 2), sticky="w")
        self._btn_diag = ctk.CTkButton(self._grp_read, width=150, command=self._on_diagnostics_click)
        self._btn_diag.grid(row=1, column=1, padx=8, pady=(4, 2), sticky="w")
        self._btn_cardinfo = ctk.CTkButton(self._grp_read, width=150, command=self._on_cardinfo_click)
        self._btn_cardinfo.grid(row=1, column=2, padx=8, pady=(4, 2), sticky="w")

        self._lbl_hex = ctk.CTkLabel(self._grp_read, anchor="w")
        self._lbl_hex.grid(row=2, column=0, columnspan=3, sticky="we", padx=10)
        self._lbl_dec = ctk.CTkLabel(self._grp_read, anchor="w")
        self._lbl_dec.grid(row=3, column=0, columnspan=3, sticky="we", padx=10)
        self._lbl_8h10d = ctk.CTkLabel(self._grp_read, anchor="w")
        self._lbl_8h10d.grid(row=4, column=0, columnspan=3, sticky="we", padx=10)
        self._lbl_wg = ctk.CTkLabel(self._grp_read, anchor="w")
        self._lbl_wg.grid(row=5, column=0, columnspan=3, sticky="we", padx=10)
        self._lbl_state = ctk.CTkLabel(self._grp_read, anchor="w", text_color="#00a000")
        self._lbl_state.grid(row=6, column=0, columnspan=3, sticky="we", padx=10, pady=(0, 8))

        # --- Kártyaírás ---
        self._grp_write = ctk.CTkFrame(f)
        self._grp_write.pack(fill="x", pady=4)
        self._grp_write_title = ctk.CTkLabel(self._grp_write, anchor="w", font=ctk.CTkFont(weight="bold"))
        self._grp_write_title.grid(row=0, column=0, columnspan=3, sticky="we", padx=10, pady=(8, 0))
        self._lbl_id = ctk.CTkLabel(self._grp_write)
        self._lbl_id.grid(row=1, column=0, padx=8, pady=6, sticky="w")
        self._txt_id = ctk.CTkEntry(self._grp_write, width=180)
        self._txt_id.grid(row=1, column=1, padx=8, pady=6, sticky="w")
        self._txt_id.bind("<KeyRelease>", lambda _e: self._validate_id_input())
        self._btn_write = ctk.CTkButton(self._grp_write, width=150, command=self._on_write_click)
        self._btn_write.grid(row=1, column=2, padx=8, pady=6, sticky="w")

        self._lbl_method = ctk.CTkLabel(self._grp_write)
        self._lbl_method.grid(row=2, column=0, padx=8, pady=4, sticky="w")
        self._rebuild_method_menu()
        self._chk_lock = ctk.BooleanVar(value=False)
        self._chk_lock_widget = ctk.CTkCheckBox(self._grp_write, variable=self._chk_lock)
        self._chk_lock_widget.grid(row=2, column=2, padx=8, pady=4, sticky="w")

        self._btn_erase = ctk.CTkButton(self._grp_write, width=150, command=self._on_erase_click)
        self._btn_erase.grid(row=3, column=0, padx=8, pady=4, sticky="w")
        self._btn_unlock = ctk.CTkButton(self._grp_write, width=150, command=self._on_unlock_click)
        self._btn_unlock.grid(row=3, column=1, padx=8, pady=4, sticky="w")

        self._lbl_method_desc = ctk.CTkLabel(self._grp_write, text_color="#808080", justify="left",
                                             wraplength=520, anchor="w")
        self._lbl_method_desc.grid(row=4, column=0, columnspan=3, sticky="we", padx=10, pady=(0, 8))

        # --- Napló ---
        self._lbl_log = ctk.CTkLabel(f, anchor="w")
        self._lbl_log.pack(fill="x")
        log_frame = ctk.CTkFrame(f, fg_color="transparent")
        log_frame.pack(fill="both", expand=True, pady=(2, 0))
        self._txt_log = ctk.CTkTextbox(log_frame, height=170, font=("Consolas", 9))
        self._txt_log.pack(side="left", fill="both", expand=True)
        scrollbar = ctk.CTkScrollbar(log_frame, command=self._txt_log.yview)
        scrollbar.pack(side="right", fill="y")
        self._txt_log.configure(yscrollcommand=scrollbar.set)

    def _method_labels(self):
        return [L(k) for k in METHOD_LABEL_KEYS]

    def _rebuild_method_menu(self):
        labels = self._method_labels()
        old = self._method_var.get() if self._method_var is not None else None
        idx = labels.index(old) if old in labels else 0
        self._method_var = ctk.StringVar(value=labels[idx])
        opt = ctk.CTkOptionMenu(self._grp_write, values=labels, variable=self._method_var,
                                command=self._on_method_changed, width=200)
        opt.grid(row=2, column=1, padx=8, pady=4, sticky="w")
        if self._opt_method is not None:
            self._opt_method.destroy()
        self._opt_method = opt

    # ---------- ikon ----------

    def _icon_paths(self):
        here = os.path.dirname(os.path.abspath(__file__))
        return [
            os.path.join(os.path.dirname(here), ICON_FILE),               # program mappa (python/)
            os.path.join(os.path.dirname(os.path.dirname(here)), ICON_FILE),  # projekt gyökér
            os.path.join(here, ICON_FILE),                                # csomag mappa
        ]

    def _set_app_icon(self):
        """Alkalmazásikon (rfid125k.ico) a címsorhoz/taskbar-hoz. Windows:
        iconbitmap; egyéb platformokon PhotoImage (ha olvasható), különben
        csendben kihagyjuk (pl. nincs ico a gépén)."""
        path = next((p for p in self._icon_paths() if os.path.isfile(p)), None)
        if path is None:
            return
        try:
            if sys.platform == "win32":
                self.iconbitmap(path)
            else:
                icon = tk.PhotoImage(file=path)
                self.iconphoto(True, icon)
        except Exception:
            pass

    # ---------- eszköz ----------

    def _open_device(self):
        try:
            self._device.open()
            self.log(L("log.device.opened", self._device.device_name))
            if self._device_mode != "simulated":
                self.log(self._device.get_reader_info())
        except Exception as ex:
            self.log(L("log.device.open.error", ex))

    # ---------- háttérszál kezelés ----------

    def _async(self, work, on_done=None, finalize=None):
        def worker():
            try:
                result = work()
                self._queue.put(("ok", on_done, finalize, result))
            except Exception as ex:
                self._queue.put(("err", on_done, finalize, ex))
        threading.Thread(target=worker, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                kind, on_done, finalize, payload = self._queue.get_nowait()
                try:
                    if kind == "ok" and on_done:
                        on_done(payload)
                    elif kind == "err":
                        self.log(L("log.error.generic", payload))
                finally:
                    if finalize:
                        finalize()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    # ---------- eseménykezelők ----------

    def _on_read_click(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
            return
        self._cancel_event = threading.Event()
        self._btn_read.configure(text=L("btn.read.cancel"))
        self.log(L("log.read.start"))

        def work():
            return self._device.read_card(cancel_event=self._cancel_event, overall_timeout=30.0)

        def done(result):
            if result.status == ReadStatus.BLANK:
                self._clear_card_labels()
                self._set_state_key("state.blank")
                self.log(L("log.blank.found"))
                self.log(L("log.blank.hint"))
            elif result.status == ReadStatus.CARD:
                self._show_card(result.card)
                self._last_card = result.card
                self.log(L("log.read.done", result.card.hex_id, result.card.decimal_id,
                           result.card.eight_hex_ten_decimal, result.card.wiegand26.value))
                self._txt_id.delete(0, "end")
                self._txt_id.insert(0, result.card.eight_hex_ten_decimal.lstrip("0") or "0")
                self._set_state_key("state.nochip")
            else:
                self.log(L("log.read.nocard"))
                self._set_state_key(None)

        def finalize():
            self._btn_read.configure(text=L("btn.read"))
            self._cancel_event = None

        self._async(work, done, finalize)

    def _on_write_click(self):
        text = self._txt_id.get().strip()
        if not card_mod.CardData.is_valid_eight_hex_ten_decimal(text):
            self.log(L("log.write.invalid"))
            return
        target = card_mod.CardData.from_eight_hex_ten_decimal(text)
        method = self._selected_method()
        lock = self._chk_lock.get()
        self._set_write_buttons_enabled(False)
        self.log(L("log.write.start", target.eight_hex_ten_decimal, target.hex_id,
                   target.decimal_id.rjust(13, "0"), target.wiegand26.value))
        self.log(L("log.write.place"))

        def work():
            self._device.write_method = method
            self._device.lock_after_write = lock
            self._device.write_card(target)

        def done(_):
            self.log(L("log.write.done", target.hex_id, target.eight_hex_ten_decimal))

        def finalize():
            self._set_write_buttons_enabled(True)

        self._async(work, done, finalize)

    def _on_cardinfo_click(self):
        self._btn_cardinfo.configure(state="disabled")
        self.log(L("log.cardinfo.start"))

        def work():
            return self._device.get_card_info()

        def done(info):
            if not info.card_present:
                self.log(L("log.cardinfo.nocard"))
                self._set_state_key("state.nocard")
                return
            if info.message:
                self.log(info.message)
            content = L("state.content.writable") if info.is_writable else L("state.content.readonly")
            self._set_state(L("state.cardinfo", info.chip_description, content))
            self.log(L("log.cardinfo.chip", info.chip_description))
            self.log(L("log.cardinfo.content", content))
            if info.card is not None:
                self._show_card(info.card)
                self._last_card = info.card

        def finalize():
            self._btn_cardinfo.configure(state="normal")

        self._async(work, done, finalize)

    def _on_erase_click(self):
        if not messagebox.askyesno(L("dlg.erase.title"), L("dlg.erase.text"), icon="warning"):
            return
        self._set_write_buttons_enabled(False)
        self.log(L("log.erase.start"))

        def work():
            self._device.erase_card()

        def done(_):
            self.log(L("log.erase.done"))
            self._clear_card_labels()
            self._last_card = None

        def finalize():
            self._set_write_buttons_enabled(True)

        self._async(work, done, finalize)

    def _on_unlock_click(self):
        if not messagebox.askyesno(L("dlg.unlock.title"), L("dlg.unlock.text"), icon="info"):
            return
        self._set_write_buttons_enabled(False)
        self.log(L("log.unlock.start"))

        def work():
            self._device.unlock_card()

        def done(_):
            self.log(L("log.unlock.done"))
            self._clear_card_labels()
            self._last_card = None

        def finalize():
            self._set_write_buttons_enabled(True)

        self._async(work, done, finalize)

    def _on_diagnostics_click(self):
        self.log(L("log.diag.start"))
        try:
            self.log(L("log.diag.device", self._device.device_name))
            devices = self._device.list_usb_devices()
            if not devices:
                self.log(L("err.usb.notfound", 0x1A86, 0xDD01))
            else:
                for dev in devices:
                    self.log(L("log.diag.found", dev))
            fmt = self._device.get_out_format()
            self.log(L("log.diag.format", " ".join(f"{b:02X}" for b in fmt)))
            self.log(L("log.diag.done"))
        except DeviceError as ex:
            self.log(L("log.diag.error", ex))

    def _on_method_changed(self, _=None):
        idx = self._selected_index()
        self._lbl_method_desc.configure(text=L(METHOD_DESC_KEYS[idx]))
        self._chk_lock_set_enabled(idx != 2)

    # ---------- segédfüggvények ----------

    def _selected_index(self):
        labels = self._method_labels()
        value = self._method_var.get() if self._method_var is not None else labels[0]
        return labels.index(value) if value in labels else 0

    def _selected_method(self):
        return WRITE_METHODS[self._selected_index()]

    def _validate_id_input(self):
        text = self._txt_id.get().strip()
        valid = card_mod.CardData.is_valid_eight_hex_ten_decimal(text)
        self._btn_write.configure(state="normal" if valid else "disabled")

    def _set_write_buttons_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for btn in (self._btn_write, self._btn_erase, self._btn_unlock):
            btn.configure(state=state)

    def _chk_lock_set_enabled(self, enabled):
        self._chk_lock_widget.configure(state="normal" if enabled else "disabled")

    def _set_state_key(self, key):
        self._state_text = key
        self._set_state(L(key) if key else L("lbl.chip"))

    def _set_state(self, text):
        self._lbl_state.configure(text=text)

    def _clear_card_labels(self):
        self._lbl_hex.configure(text=L("lbl.hex"))
        self._lbl_dec.configure(text=L("lbl.decimal"))
        self._lbl_8h10d.configure(text=L("lbl.eighthex"))
        self._lbl_wg.configure(text=L("lbl.wiegand"))

    def _show_card(self, card):
        self._lbl_hex.configure(text=L("lbl.hex.value", card.hex_id))
        self._lbl_dec.configure(text=L("lbl.decimal.value", card.decimal_id.rjust(13, "0")))
        self._lbl_8h10d.configure(text=L("lbl.eighthex.value", card.eight_hex_ten_decimal))
        w = card.wiegand26
        self._lbl_wg.configure(text=L("lbl.wiegand.value", w.value, w.facility_code, w.card_number))

    def log(self, message):
        self._txt_log.configure(state="normal")
        self._txt_log.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self._txt_log.see("end")
        self._txt_log.configure(state="disabled")

    def _on_close(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
        try:
            self._device.close()
        except Exception:
            pass
        self.destroy()
