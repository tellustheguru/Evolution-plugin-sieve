#!/usr/bin/env python3
"""GTK editor for scripts stored by a ManageSieve server."""

import configparser
import os
import re
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("EDataServer", "1.2")
from gi.repository import EDataServer, Gio, GLib, Gtk

from filter_ui import FilterPanel
from sieve_filters import parse_document
from sieve import AuthenticationError, Client, SieveError


CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "evolution-sieve" / "config.ini"
DEFAULT_SCRIPT_NAME = "evolution-sieve-rules"
BACKUPS = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "evolution-sieve" / "backups"


class Editor(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.script_name = None
        self.script_original = None
        self.script_active = False
        self.scripts = {}
        self.loading_script = False
        self.busy = False
        self.closed = False
        self.connect("destroy", self._on_destroy)
        self.config = configparser.ConfigParser()
        self.config.read(CONFIG)
        self.sources = {}
        self.registry = None
        self.account_uid = None
        self.reverting_account = False
        root = self
        root.set_border_width(12)
        account_row = Gtk.Box(spacing=8)
        root.pack_start(account_row, False, False, 0)
        account_row.pack_start(Gtk.Label(label="IMAP-konto"), False, False, 0)
        self.account = Gtk.ComboBoxText()
        self.account.set_hexpand(True)
        account_row.pack_start(self.account, True, True, 0)
        self.host = ""
        self.port = "4190"
        self.user = ""
        self.password = ""
        self.settings_button = Gtk.Button(label="Anslutning…")
        self.settings_button.set_tooltip_text("Inställningar för ManageSieve-servern")
        self.settings_button.connect("clicked", self.on_connection_settings)
        account_row.pack_start(self.settings_button, False, False, 0)
        self.connect_button = Gtk.Button(label="Hämta regler")
        self.connect_button.connect("clicked", self.on_connect)
        account_row.pack_start(self.connect_button, False, False, 0)
        self.status = Gtk.Label(label="STARTTLS med verifierat certifikat")
        self.status.set_xalign(0)
        root.pack_start(self.status, False, False, 0)
        script_row = Gtk.Box(spacing=8)
        root.pack_start(script_row, False, False, 0)
        script_row.pack_start(Gtk.Label(label="Skript på servern"), False, False, 0)
        self.script_combo = Gtk.ComboBoxText()
        self.script_combo.set_hexpand(True)
        script_row.pack_start(self.script_combo, True, True, 0)
        self.new_button = Gtk.Button(label="Nytt skript")
        self.new_button.connect("clicked", self.on_new_script)
        script_row.pack_start(self.new_button, False, False, 0)
        self.script_combo.connect("changed", self.on_script_changed)
        self.account.connect("changed", self.on_account_changed)
        self.notebook = Gtk.Notebook()
        root.pack_start(self.notebook, True, True, 0)
        self.filter_panel = FilterPanel(self)
        self.notebook.append_page(self.filter_panel, Gtk.Label(label="Grafiska filter"))
        raw_scroller = Gtk.ScrolledWindow()
        self.raw_view = Gtk.TextView()
        self.raw_view.set_monospace(True)
        self.raw_view.set_wrap_mode(Gtk.WrapMode.NONE)
        raw_scroller.add(self.raw_view)
        self.notebook.append_page(raw_scroller, Gtk.Label(label="Sieve-kod"))
        self.notebook.connect("switch-page", self.on_page_switched)
        save_row = Gtk.Box(spacing=8)
        root.pack_start(save_row, False, False, 0)
        self.save_button = Gtk.Button(label="Spara skript")
        self.save_button.connect("clicked", self.on_save)
        save_row.pack_start(self.save_button, False, False, 0)
        self.activate_button = Gtk.Button(label="Spara och aktivera")
        self.activate_button.connect("clicked", self.on_save_and_activate)
        save_row.pack_start(self.activate_button, False, False, 0)
        self.save_button.set_sensitive(False)
        self.activate_button.set_sensitive(False)
        GLib.idle_add(self._initialize)

    def _initialize(self):
        self.load_accounts()
        return GLib.SOURCE_REMOVE

    def _dialog_parent(self):
        toplevel = self.get_toplevel()
        return toplevel if isinstance(toplevel, Gtk.Window) else None

    def _on_destroy(self, *_):
        self.closed = True

    def _setting(self, grid, row, label, value):
        entry = Gtk.Entry()
        entry.set_text(value)
        entry.set_hexpand(True)
        caption = Gtk.Label(label=label)
        caption.set_xalign(0)
        grid.attach(caption, 0, row, 1, 1)
        grid.attach(entry, 1, row, 1, 1)
        return entry

    def on_connection_settings(self, *_):
        dialog = Gtk.Dialog(title="ManageSieve-anslutning", transient_for=self._dialog_parent(), flags=0)
        dialog.add_buttons("Avbryt", Gtk.ResponseType.CANCEL, "Spara", Gtk.ResponseType.OK)
        dialog.set_default_size(460, -1)
        grid = Gtk.Grid(column_spacing=12, row_spacing=10)
        grid.set_border_width(16)
        dialog.get_content_area().add(grid)
        host = self._setting(grid, 0, "Server", self.host)
        port = self._setting(grid, 1, "Port", self.port)
        user = self._setting(grid, 2, "Användarnamn", self.user)
        password = self._setting(grid, 3, "Eget lösenord", self.password)
        password.set_visibility(False)
        password.set_placeholder_text("Tomt = Evolutions sparade lösenord")
        tls = Gtk.Label(label="Anslutningen använder STARTTLS med verifierat certifikat.")
        tls.set_xalign(0)
        grid.attach(tls, 0, 4, 2, 1)
        dialog.show_all()
        accepted = dialog.run() == Gtk.ResponseType.OK
        if accepted:
            values = (host.get_text().strip(), port.get_text().strip(),
                      user.get_text().strip(), password.get_text())
        dialog.destroy()
        if accepted:
            self.host, self.port, self.user, self.password = values
            self._save_config()
            self.on_connect()

    def load_accounts(self):
        def task():
            registry = EDataServer.SourceRegistry.new_sync(None)
            sources = []
            for source in registry.list_sources(EDataServer.SOURCE_EXTENSION_MAIL_ACCOUNT):
                account = source.get_extension(EDataServer.SOURCE_EXTENSION_MAIL_ACCOUNT)
                if account.get_backend_name() != "imapx" or not source.get_enabled():
                    continue
                sources.append(source)
            return registry, sources

        def finished(result):
            self.registry, sources = result
            for source in sources:
                self.sources[source.get_uid()] = source
                self.account.append(source.get_uid(), source.get_display_name())
            if self.sources:
                self.account.set_active(0)
                self.load_initial_rules()
            else:
                self.status.set_text("Inget IMAP-konto hittades i Evolution")

        self._run_worker(task, finished, "Läser Evolution-konton…")

    def on_account_changed(self, *_):
        if self.reverting_account:
            return
        uid = self.account.get_active_id()
        source = self.sources.get(uid)
        if source is None:
            return
        if self.account_uid and uid != self.account_uid and not self._confirm_discard():
            self.reverting_account = True
            self.account.set_active_id(self.account_uid)
            self.reverting_account = False
            return
        self.account_uid = uid
        auth = source.get_extension(EDataServer.SOURCE_EXTENSION_AUTHENTICATION)
        section = "account " + uid
        self.host = self.config.get(section, "host", fallback=auth.get_host() or "")
        self.port = self.config.get(section, "port", fallback="4190")
        self.user = self.config.get(section, "username", fallback=auth.get_user() or "")
        self.password = ""
        self.script_name = None
        self.script_original = None
        self.scripts = {}
        self.loading_script = True
        self.script_combo.remove_all()
        self.loading_script = False
        if hasattr(self, "raw_view"):
            self._set_raw_text("")
        if hasattr(self, "filter_panel"):
            self.filter_panel.set_document(None)
        if hasattr(self, "save_button"):
            self.save_button.set_sensitive(False)
            self.activate_button.set_sensitive(False)
        self.status.set_text("Konto valt: " + source.get_display_name())

    def _connection_settings(self):
        source = self.sources.get(self.account.get_active_id())
        return (self.host, self.port, self.user, self.password, source)

    @staticmethod
    def _open_client(settings):
        host, port, username, password, source = settings
        if not password:
            if source is None:
                raise SieveError("Välj ett IMAP-konto eller ange ett eget lösenord under Anslutning")
            found, password = source.lookup_password_sync(None)
            if not found or not password:
                raise SieveError("Evolution har inget sparat lösenord för kontot. Ange det under Anslutning.")
        return Client(host, port, username, password)

    def _run_worker(self, task, finished, status, failed=None):
        if self.busy:
            return
        self.busy = True
        self.status.set_text(status)
        for widget in (self.account, self.settings_button, self.connect_button, self.script_combo,
                       self.new_button, self.save_button, self.activate_button):
            widget.set_sensitive(False)

        def run():
            try:
                result, error = task(), None
            except Exception as exc:
                result, error = None, exc

            def complete():
                if self.closed:
                    return GLib.SOURCE_REMOVE
                self.busy = False
                for widget in (self.account, self.settings_button, self.connect_button, self.script_combo, self.new_button):
                    widget.set_sensitive(True)
                self.save_button.set_sensitive(self.script_name is not None)
                self.activate_button.set_sensitive(self.script_name is not None)
                if error is None:
                    finished(result)
                else:
                    if failed is not None:
                        failed(error)
                    self.status.set_text("Sieve-fel: " + str(error))
                    if isinstance(error, AuthenticationError):
                        self._error("ManageSieve-servern nekade inloggningen. "
                                    "Kontrollera att servern tillåter SASL PLAIN över STARTTLS "
                                    "och att kontots uppgifter stämmer. " + str(error))
                    else:
                        self._error(error)
                return GLib.SOURCE_REMOVE

            GLib.idle_add(complete)

        threading.Thread(target=run, daemon=True).start()

    def _error(self, message):
        dialog = Gtk.MessageDialog(transient_for=self._dialog_parent(), flags=0, message_type=Gtk.MessageType.ERROR,
                                   buttons=Gtk.ButtonsType.CLOSE, text="Sieve-fel")
        dialog.format_secondary_text(str(message))
        dialog.run()
        dialog.destroy()

    def _save_config(self):
        uid = self.account.get_active_id()
        if not uid:
            return
        self.config["account " + uid] = {"host": self.host, "port": self.port,
                                          "username": self.user}
        CONFIG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=CONFIG.parent,
                                             prefix=".config-", delete=False) as stream:
                temporary = Path(stream.name)
                self.config.write(stream)
            os.replace(temporary, CONFIG)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def on_connect(self, *_):
        if self.busy:
            return
        try:
            if not self._confirm_discard():
                return
            self._save_config()
            settings = self._connection_settings()

            def task():
                with self._open_client(settings) as client:
                    scripts = dict(client.list_scripts())
                    preferred = next((name for name, active in scripts.items() if active), None)
                    preferred = preferred or next(iter(scripts), None)
                    return scripts, preferred, client.get_script(preferred) if preferred else ""

            def finished(result):
                self.scripts, preferred, text = result
                name = preferred or DEFAULT_SCRIPT_NAME
                self._refresh_script_choices(name)
                self._open_script(name, text, bool(preferred and self.scripts[preferred]))
                if not preferred:
                    self.status.set_text("Ansluten. Inga skript på servern ännu.")

            self._run_worker(task, finished, "Hämtar regler från servern…")
        except (OSError, ValueError, UnicodeError, SieveError) as error:
            self._error(error)

    def load_initial_rules(self):
        if self.account.get_active_id():
            self.status.set_text("Hämtar regler från servern…")
            self.on_connect()
        return GLib.SOURCE_REMOVE

    def _refresh_script_choices(self, selected):
        self.loading_script = True
        self.script_combo.remove_all()
        for name, active in self.scripts.items():
            self.script_combo.append(name, name + (" (aktivt)" if active else ""))
        if selected and selected not in self.scripts:
            self.script_combo.append(selected, selected + " (nytt)")
        if selected:
            self.script_combo.set_active_id(selected)
        self.loading_script = False

    def _set_raw_text(self, text):
        self.raw_view.get_buffer().set_text(text)

    def _raw_text(self):
        buffer = self.raw_view.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)

    def _open_script(self, name, text, active):
        self.script_name = name
        self.script_original = text if name in self.scripts else None
        self.script_active = active
        self._set_raw_text(text)
        document = parse_document(text)
        self.filter_panel.set_document(document)
        self.notebook.set_current_page(0)
        self.status.set_text(f"{name}: {len(document.filters)} grafiska filter, " +
                             ("aktivt" if active else "inte aktivt"))
        self.save_button.set_sensitive(True)
        self.activate_button.set_sensitive(True)

    def _changed(self):
        if self.notebook.get_current_page() == 0:
            return self.filter_panel.document is not None and self.filter_panel.document.render() != (self.script_original or "")
        return self._raw_text() != (self.script_original or "")

    def _confirm_discard(self):
        if not self.script_name or not self._changed():
            return True
        dialog = Gtk.MessageDialog(transient_for=self._dialog_parent(), flags=0, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.OK_CANCEL, text="Kasta ändringar som inte sparats?")
        result = dialog.run() == Gtk.ResponseType.OK
        dialog.destroy()
        return result

    def on_script_changed(self, *_):
        if self.loading_script or self.busy:
            return
        name = self.script_combo.get_active_id()
        if not name or name == self.script_name:
            return
        if not self._confirm_discard():
            self.loading_script = True
            self.script_combo.set_active_id(self.script_name)
            self.loading_script = False
            return
        if name not in self.scripts:
            self._open_script(name, "", False)
            return
        settings = self._connection_settings()

        def task():
            with self._open_client(settings) as client:
                return client.get_script(name)

        def failed(_error):
            self.loading_script = True
            self.script_combo.set_active_id(self.script_name)
            self.loading_script = False

        self._run_worker(task, lambda text: self._open_script(name, text, self.scripts[name]),
                         f"Hämtar skriptet {name}…", failed)

    def on_new_script(self, *_):
        if not self.scripts and self.script_name is None:
            self._error("Anslut till servern först")
            return
        dialog = Gtk.Dialog(title="Nytt Sieve-skript", transient_for=self._dialog_parent(), flags=0)
        dialog.add_buttons("Avbryt", Gtk.ResponseType.CANCEL, "Skapa", Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        entry.set_text(DEFAULT_SCRIPT_NAME)
        entry.set_margin_top(10)
        entry.set_margin_bottom(10)
        dialog.get_content_area().add(entry)
        dialog.show_all()
        accepted = dialog.run() == Gtk.ResponseType.OK
        name = entry.get_text().strip()
        dialog.destroy()
        if not accepted:
            return
        if not name or name in self.scripts:
            self._error("Ange ett nytt, unikt skriptnamn")
            return
        if not self._confirm_discard():
            return
        self._refresh_script_choices(name)
        self._open_script(name, "", False)

    def on_page_switched(self, notebook, page, page_num):
        if self.script_name is None:
            return
        if page_num == 1 and self.filter_panel.document is not None:
            self._set_raw_text(self.filter_panel.document.render())
        elif page_num == 0:
            self.filter_panel.set_document(parse_document(self._raw_text()))

    def _backup(self, name, script):
        BACKUPS.mkdir(mode=0o700, parents=True, exist_ok=True)
        BACKUPS.chmod(0o700)
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:40]
        path = BACKUPS / f"{safe_name}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.sieve"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(script)
        return path

    def on_save_and_activate(self, *_):
        self._save(activate=True)

    def on_save(self, *_):
        self._save(activate=False)

    def _save(self, activate):
        if self.busy:
            return
        try:
            if not self.script_name:
                raise SieveError("Välj ett skript först")
            script = self.filter_panel.document.render() if self.notebook.get_current_page() == 0 else self._raw_text()
            if not script.strip():
                raise SieveError("Skriptet är tomt")
            name = self.script_name
            original = self.script_original
            if script == original and (not activate or self.script_active):
                self.status.set_text("Inga ändringar att spara")
                return
            active = next((item for item, enabled in self.scripts.items() if enabled), None)
            if activate and active and active != name:
                dialog = Gtk.MessageDialog(transient_for=self._dialog_parent(), flags=0,
                                           message_type=Gtk.MessageType.QUESTION,
                                           buttons=Gtk.ButtonsType.OK_CANCEL,
                                           text=f"Aktivera reglerna i stället för {active}?")
                dialog.format_secondary_text("Servern kan bara ha ett aktivt personligt Sieve-skript åt gången.")
                answer = dialog.run()
                dialog.destroy()
                if answer != Gtk.ResponseType.OK:
                    return
            settings = self._connection_settings()

            def task():
                with self._open_client(settings) as client:
                    scripts = dict(client.list_scripts())
                    current = client.get_script(name) if name in scripts else None
                    if current != original:
                        raise SieveError("Skriptet har ändrats på servern sedan det hämtades. Hämta det igen innan du sparar.")
                    current_active = next((item for item, enabled in scripts.items() if enabled), None)
                    if activate and current_active != active:
                        raise SieveError("Aktivt skript har ändrats på servern. Hämta reglerna igen.")
                    if current is not None:
                        self._backup(name, current)
                    client.put_script(name, script)
                    if activate:
                        client.set_active(name)
                    return dict(client.list_scripts())

            def finished(scripts):
                self.script_original = script
                self.scripts = scripts
                self.script_active = scripts.get(name, False)
                self._refresh_script_choices(name)
                self.status.set_text(f"{name}: " + ("sparat och aktivt" if self.script_active else "sparat"))

            self._run_worker(task, finished, f"Sparar skriptet {name}…")
        except (OSError, ValueError, UnicodeError, SieveError) as error:
            self._error(error)


if __name__ == "__main__":
    if "--help" in sys.argv:
        print("Startar grafisk Sieve-redigerare för Evolution")
        sys.exit(0)
    application = Gtk.Application(application_id="org.evolution.SieveEditor",
                                  flags=Gio.ApplicationFlags.FLAGS_NONE)

    def activate(app):
        windows = app.get_windows()
        if windows:
            windows[0].present()
            return
        window = Gtk.ApplicationWindow(application=app, title="Serverfilter (Sieve) — Evolution")
        window.set_default_size(900, 560)
        window.set_icon_name("evolution")
        window.add(Editor())
        app.add_window(window)
        window.show_all()

    application.connect("activate", activate)
    sys.exit(application.run(sys.argv))
