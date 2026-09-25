#!/bin/sh
set -eu

repository="${HASHMARKS_REPOSITORY:-Hugloss/Hashmarks}"
install_dir="${HASHMARKS_INSTALL_DIR:-$HOME/.local/bin}"
version="${HASHMARKS_VERSION:-latest}"

is_release_version() {
  printf '%s\n' "$1" | awk '
    NR == 1 && $0 ~ /^[0-9]+\.[0-9]+\.[0-9]+$/ { valid = 1 }
    END { exit !(NR == 1 && valid) }
  '
}

if [ "$version" = "latest" ]; then
  requested_version=""
else
  requested_version="${version#v}"
  if ! is_release_version "$requested_version"; then
    printf '%s\n' "hashmarks installer: invalid release version: $version" >&2
    exit 2
  fi
fi

case "$(uname -s)" in
  Linux) platform="linux" ;;
  *)
    printf '%s\n' "hashmarks installer: unsupported operating system: $(uname -s)" >&2
    exit 2
    ;;
esac

case "$(uname -m)" in
  x86_64|amd64) arch="x86_64" ;;
  *)
    printf '%s\n' "hashmarks installer: unsupported architecture: $(uname -m)" >&2
    exit 2
    ;;
esac

asset="hashmarks-${platform}-${arch}"
if [ -n "${HASHMARKS_DOWNLOAD_BASE_URL:-}" ]; then
  base="${HASHMARKS_DOWNLOAD_BASE_URL%/}"
elif [ "$version" = "latest" ]; then
  base="https://github.com/${repository}/releases/latest/download"
else
  case "$version" in
    v*) tag="$version" ;;
    *) tag="v$version" ;;
  esac
  base="https://github.com/${repository}/releases/download/${tag}"
fi

command -v curl >/dev/null 2>&1 || {
  printf '%s\n' 'hashmarks installer: curl is required' >&2
  exit 2
}

tmp_dir="$(mktemp -d)"
candidate=""
cleanup() {
  rm -rf "$tmp_dir"
  if [ -n "$candidate" ]; then
    rm -f "$candidate"
  fi
}
trap cleanup EXIT HUP INT TERM
binary="$tmp_dir/$asset"
checksum="$tmp_dir/$asset.sha256"

curl -fsSL "$base/$asset" -o "$binary"
curl -fsSL "$base/$asset.sha256" -o "$checksum"

checksum_lines="$(awk 'END {print NR}' "$checksum")"
[ "$checksum_lines" -eq 1 ] || {
  printf '%s\n' 'hashmarks installer: checksum asset must contain exactly one entry' >&2
  exit 1
}
expected="$(awk 'NR == 1 {print $1}' "$checksum")"
checksum_asset="$(awk 'NR == 1 {print $2}' "$checksum")"
checksum_asset="${checksum_asset#\*}"
case "$expected" in
  ''|*[!0-9a-fA-F]*)
    printf '%s\n' 'hashmarks installer: invalid SHA-256 checksum asset' >&2
    exit 1
    ;;
esac
[ "${#expected}" -eq 64 ] || {
  printf '%s\n' 'hashmarks installer: invalid SHA-256 checksum length' >&2
  exit 1
}
[ "$checksum_asset" = "$asset" ] || {
  printf '%s\n' "hashmarks installer: checksum entry names $checksum_asset, expected $asset" >&2
  exit 1
}

if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$binary" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  actual="$(shasum -a 256 "$binary" | awk '{print $1}')"
else
  printf '%s\n' 'hashmarks installer: sha256sum or shasum is required' >&2
  exit 2
fi

[ "$actual" = "$expected" ] || {
  printf '%s\n' 'hashmarks installer: SHA-256 verification failed' >&2
  exit 1
}

mkdir -p "$install_dir"
target="$install_dir/hashmarks"
if [ -e "$target" ] && [ ! -f "$target" ]; then
  printf '%s\n' "hashmarks installer: install target exists but is not a file: $target" >&2
  exit 1
fi
candidate="$(mktemp "$install_dir/.hashmarks-install.XXXXXX")"
install -m 0755 "$binary" "$candidate"
if ! reported="$("$candidate" --version 2>/dev/null)"; then
  printf '%s\n' 'hashmarks installer: downloaded binary failed version smoke test' >&2
  exit 1
fi
case "$reported" in
  "hashmarks version "*) reported_version="${reported#hashmarks version }" ;;
  *)
    printf '%s\n' 'hashmarks installer: downloaded binary returned unexpected version output' >&2
    exit 1
    ;;
esac
if ! is_release_version "$reported_version"; then
  printf '%s\n' 'hashmarks installer: downloaded binary returned an invalid release version' >&2
  exit 1
fi
if [ -n "$requested_version" ]; then
  [ "$reported_version" = "$requested_version" ] || {
    printf '%s\n' "hashmarks installer: requested version $requested_version but downloaded binary reports $reported_version" >&2
    exit 1
  }
fi
mv -f "$candidate" "$target"
candidate=""

printf 'Hashmarks installed: %s\n' "$target"
resolved="$(command -v hashmarks 2>/dev/null || true)"
if [ -z "$resolved" ]; then
  printf 'Add %s to PATH, then run: hashmarks --version\n' "$install_dir"
elif [ "$resolved" != "$target" ]; then
  printf 'Warning: hashmarks on PATH resolves to %s; installed target is %s\n' \
    "$resolved" "$target"
fi
if command -v opencode >/dev/null 2>&1; then
  printf 'OpenCode detected. From the target repository run: %s install --opencode\n' "$target"
fi
