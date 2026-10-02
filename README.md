# Evolution Sieve plugin

A graphical editor for server-side Sieve filters in Evolution 3.52, designed for Dovecot/Pigeonhole ManageSieve. It appears as **Serverfilter (Sieve)** in Evolution's Plugins list and opens inside Evolution's Preferences window. Connections use STARTTLS on port 4190 with certificate verification.

## Install

On Ubuntu with Evolution 3.52, download the `.deb` file from the [Releases page](https://github.com/tellustheguru/Evolution-plugin-sieve/releases) and install it:

```sh
sudo apt install ./evolution-sieve_0.1.0_amd64.deb
```

Restart Evolution. In the mail view, open **Edit → Serverfilter (Sieve)…** or press **Ctrl+Shift+S**. The editor automatically loads the active script for the selected IMAP account.

To build the package from source instead:

```sh
sudo apt install evolution-dev libedataserver1.2-dev libgtk-3-dev python3-dev python3-gi pkg-config debhelper
./build-deb.sh
sudo apt install ./dist/evolution-sieve_0.1.0_$(dpkg --print-architecture).deb
```

If you previously used `./install.sh`, remove its user-level files before installing the `.deb` package to prevent Evolution from loading the plugin twice:

```sh
rm -f ~/.local/share/evolution/modules/lib/evolution/modules/module-evolution-sieve.so
rm -f ~/.local/share/evolution/modules/lib/evolution/plugins/org-gnome-evolution-sieve-editor.eplug
```

## Use

The editor reads the ManageSieve host and username from the selected Evolution IMAP account and tries its saved password. Use **Anslutning…** (Connection) if your ManageSieve server needs different details. Connection settings are saved per account in `~/.config/evolution-sieve/config.ini`; the plugin does not save your password. **Hämta regler** (Fetch rules) refreshes scripts from the server.

The active script opens automatically. Select a filter under **Grafiska filter** (Graphical filters) and choose **Ändra valt filter** (Edit selected filter). You can edit its name, enabled state, conditions, and actions; add or remove filters; and change their order. **Spara skript** (Save script) uploads your changes. **Spara och aktivera** (Save and activate) also makes that script active.

The plugin can edit common filters created by other Sieve clients, including named and unnamed filters. It supports `header`, `address`, `envelope`, `exists`, `size`, `body`, and `true` conditions, plus `fileinto`, `redirect`, `keep`, `discard`, `stop`, `reject`, `ereject`, simple `vacation` replies, and IMAP flag actions. Unsupported filters are shown as **Kan inte redigeras grafiskt** (Cannot edit graphically) and remain unchanged. Scripts containing `text:` literals are handled as raw Sieve code. The **Sieve-kod** (Sieve code) tab lets you edit syntax outside the graphical editor.

Before changing an existing script, the plugin saves a local backup. It refuses to upload changes if the server copy has changed since you fetched it. The Plugins checkbox enables or disables the menu entry and editor; an already open Preferences page remains in the sidebar until Evolution restarts.

## Compatibility and development

The plugin supports SASL PLAIN over STARTTLS. The ManageSieve server must accept password authentication. If your IMAP account uses another authentication method, Evolution's saved password may not work for ManageSieve.

The graphical editor and parser have been tested locally, and the page has been displayed in Evolution 3.52. The Debian package passes `lintian` and an APT installation simulation; it has not yet been installed and tested in a running Evolution session. Run the 18 rule tests with `python3 -m unittest -v`. For troubleshooting, run `./diagnose.sh` while Evolution is open, or start the editor directly with `python3 editor.py`.

The integration uses an Evolution `EExtension` and `GtkUIManager`. The editor runs as a GTK widget inside Evolution, while account lookup and ManageSieve requests run in background threads.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
