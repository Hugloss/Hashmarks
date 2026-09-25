#!/bin/sh
set -eu

repository="${HASHMARKS_REPOSITORY:-Hugloss/Hashmarks}"
install_dir="${HASHMARKS_INSTALL_DIR:-$HOME/.local/bin}"
version="${HASHMARKS_VERSION:-latest}"

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
trap 'rm -rf "$tmp_dir"' EXIT HUP INT TERM
binary="$tmp_dir/$asset"
checksum="$tmp_dir/$asset.sha256"

curl -fsSL "$base/$asset" -o "$binary"
curl -fsSL "$base/$asset.sha256" -o "$checksum"

expected="$(awk 'NR == 1 {print $1}' "$checksum")"
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
install -m 0755 "$binary" "$target"
"$target" version >/dev/null

printf 'Hashmarks installed: %s\n' "$target"
if ! command -v hashmarks >/dev/null 2>&1; then
  printf 'Add %s to PATH, then run: hashmarks --version\n' "$install_dir"
fi
