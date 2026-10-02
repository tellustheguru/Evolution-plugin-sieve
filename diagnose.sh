#!/bin/sh
set -eu
module_dir=$(python3 - "$(pkg-config --variable=moduledir evolution-shell-3.0)" "$(pkg-config --variable=prefix evolution-shell-3.0)" <<'PY'
import sys
import gi
gi.require_version('EDataServer', '1.2')
from gi.repository import EDataServer, GLib
paths = EDataServer.util_get_directory_variants(sys.argv[1], sys.argv[2], True)
user_root = GLib.get_user_data_dir() + '/evolution/modules/'
for path in paths:
    if path.startswith(user_root):
        print(path)
        break
else:
    raise SystemExit('Kunde inte hitta Evolutions användarmodulkatalog')
PY
)
module="$module_dir/module-evolution-sieve.so"
if [ -f "$module" ]; then
    echo "Modulfil: $module"
    file "$module"
else
    echo "Modulfil saknas: $module"
fi
found=0
for pid in $(pgrep -u "$(id -u)" -x evolution || true); do
    found=1
    echo "Evolution-process: $pid"
    if [ -r "/proc/$pid/maps" ] && grep -q '/module-evolution-sieve.so' "/proc/$pid/maps"; then
        echo 'Modulen är laddad i processen.'
    else
        echo 'Modulen är INTE laddad i processen.'
    fi
done
if [ "$found" -eq 0 ]; then
    echo 'Ingen Evolution-process hittades.'
fi
