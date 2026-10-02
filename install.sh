#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
pkg-config --exists evolution-shell-3.0 libedataserver-1.2 gtk+-3.0 || {
    echo 'Installera evolution-dev, libedataserver1.2-dev och libgtk-3-dev först.' >&2
    exit 1
}
if ! command -v python3-config >/dev/null 2>&1 ||
   ! python3-config --includes >/dev/null 2>&1; then
    echo 'Installera python3-dev först.' >&2
    exit 1
fi
module_dir=$(python3 - "$(pkg-config --variable=moduledir evolution-shell-3.0)" "$(pkg-config --variable=prefix evolution-shell-3.0)" <<'PY'
import sys
import gi
gi.require_version('EDataServer', '1.2')
from gi.repository import EDataServer, GLib
paths = EDataServer.util_get_directory_variants(sys.argv[1], sys.argv[2], True)
user_root = GLib.get_user_data_dir() + '/evolution/modules/'
user_paths = [path for path in paths if path.startswith(user_root)]
if len(user_paths) != 1:
    raise SystemExit('Kunde inte hitta Evolutions användarmodulkatalog')
print(user_paths[0])
PY
)
plugin_dir=$(python3 - "$(dirname "$(pkg-config --variable=moduledir evolution-shell-3.0)")/plugins" "$(pkg-config --variable=prefix evolution-shell-3.0)" <<'PY'
import sys
import gi
gi.require_version('EDataServer', '1.2')
from gi.repository import EDataServer, GLib
paths = EDataServer.util_get_directory_variants(sys.argv[1], sys.argv[2], True)
user_root = GLib.get_user_data_dir() + '/evolution/modules/'
user_paths = [path for path in paths if path.startswith(user_root)]
if len(user_paths) != 1:
    raise SystemExit('Kunde inte hitta Evolutions användarkatalog för insticksmoduler')
print(user_paths[0])
PY
)
# Evolution 3.52 still exposes GtkUIManager; GTK marks that API deprecated.
gcc -fPIC -shared -Wall -Wextra -Wno-deprecated-declarations \
    "-DSIEVE_EDITOR_PATH=\"$project_dir/editor.py\"" \
    $(pkg-config --cflags evolution-shell-3.0 libedataserver-1.2 gtk+-3.0) \
    $(python3-config --cflags) \
    "$project_dir/evolution-module.c" -o "$project_dir/module-evolution-sieve.so" \
    $(pkg-config --libs evolution-shell-3.0 libedataserver-1.2 gtk+-3.0) \
    $(python3-config --embed --ldflags)
mkdir -p "$module_dir"
install -m 755 "$project_dir/module-evolution-sieve.so" "$module_dir/module-evolution-sieve.so"
mkdir -p "$plugin_dir"
python3 - "$project_dir/evolution-sieve.eplug" "$module_dir/module-evolution-sieve.so" "$plugin_dir/org-gnome-evolution-sieve-editor.eplug" <<'PY'
import sys
import xml.etree.ElementTree as ET
tree = ET.parse(sys.argv[1])
tree.getroot().find('e-plugin').set('location', sys.argv[2])
tree.write(sys.argv[3], encoding='utf-8', xml_declaration=True)
PY
echo "Installerad: $module_dir/module-evolution-sieve.so"
echo "Insticksmodul: $plugin_dir/org-gnome-evolution-sieve-editor.eplug"
echo 'Starta om Evolution och öppna Redigera → Serverfilter (Sieve)… i e-postvyn.'
