#!/bin/sh
set -eu
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
version=$(dpkg-parsechangelog -l "$project_dir/debian/changelog" -S Version)
architecture=$(dpkg --print-architecture)
build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM
mkdir -p "$build_dir/evolution-sieve-$version"
tar -C "$project_dir" \
    --exclude='./__pycache__' --exclude='./debian/.debhelper' \
    --exclude='./debian/build' --exclude='./debian/evolution-sieve' \
    -cf - README.md editor.py filter_ui.py sieve.py sieve_filters.py \
    evolution-module.c evolution-sieve.eplug LICENSE test_sieve.py test_sieve_filters.py debian \
    | tar -C "$build_dir/evolution-sieve-$version" -xf -
(
    cd "$build_dir/evolution-sieve-$version"
    dpkg-buildpackage -us -uc -b
)
mkdir -p "$project_dir/dist"
package="$build_dir/evolution-sieve_${version}_${architecture}.deb"
install -m 644 "$package" "$project_dir/dist/"
echo "Paket: $project_dir/dist/$(basename "$package")"
