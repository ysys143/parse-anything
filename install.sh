#!/bin/sh
# parse-anything installer.
#
# Downloads a self-contained release bundle (frozen Python + a trimmed JRE -- no Python or Java needed
# on the machine) from GitHub Releases, installs it under ~/.local, and puts the `parse-anything`,
# `parse`, and `pa` commands on your PATH.
#
#   curl -fsSL https://raw.githubusercontent.com/ysys143/parse-anything/main/install.sh | sh
#
# Options (pass after `-s --` when piping, e.g. `... | sh -s -- --version v0.1.0`):
#   --version <tag>     install a specific release tag (default: latest)
#   --install-dir <d>   app dir (default: ${XDG_DATA_HOME:-~/.local/share}/parse-anything)
#   --bin-dir <d>       command dir (default: ~/.local/bin)
#   --uninstall         remove the commands, the app dir, and stop there
#   -h | --help         show this help
#
# Re-running the installer updates to the latest (or the pinned) version.
# Env overrides: PARSE_ANYTHING_VERSION, PARSE_ANYTHING_INSTALL_DIR, PARSE_ANYTHING_BIN_DIR.
set -eu

OWNER="ysys143"
REPO="parse-anything"
COMMANDS="parse-anything parse pa"

DATA_DIR="${PARSE_ANYTHING_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/parse-anything}"
BIN_DIR="${PARSE_ANYTHING_BIN_DIR:-$HOME/.local/bin}"
VERSION="${PARSE_ANYTHING_VERSION:-latest}"
ACTION="install"

info() { printf '  %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*" >&2; }
err()  { printf 'error: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
parse-anything installer -- downloads a self-contained bundle (no Python/Java needed) and puts
`parse-anything` / `parse` / `pa` on your PATH.

  curl -fsSL https://raw.githubusercontent.com/ysys143/parse-anything/main/install.sh | sh

Options (after `-s --` when piping):
  --version <tag>     install a specific release tag (default: latest)
  --install-dir <d>   app dir (default: ${XDG_DATA_HOME:-~/.local/share}/parse-anything)
  --bin-dir <d>       command dir (default: ~/.local/bin)
  --uninstall         remove the commands and the app dir
  -h, --help          show this help

Env overrides: PARSE_ANYTHING_VERSION, PARSE_ANYTHING_INSTALL_DIR, PARSE_ANYTHING_BIN_DIR
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:?--version needs a tag}"; shift 2 ;;
    --version=*) VERSION="${1#*=}"; shift ;;
    --install-dir) DATA_DIR="${2:?--install-dir needs a path}"; shift 2 ;;
    --bin-dir) BIN_DIR="${2:?--bin-dir needs a path}"; shift 2 ;;
    --uninstall) ACTION="uninstall"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) err "unknown option: $1 (try --help)" ;;
  esac
done

have() { command -v "$1" >/dev/null 2>&1; }

download() {  # <url> <dest>
  if have curl; then curl -fsSL "$1" -o "$2"
  elif have wget; then wget -qO "$2" "$1"
  else err "need curl or wget"; fi
}
download_stdout() {  # <url>
  if have curl; then curl -fsSL "$1"
  elif have wget; then wget -qO- "$1"
  else err "need curl or wget"; fi
}

detect_platform() {
  os="$(uname -s)"; arch="$(uname -m)"
  case "$os" in
    Linux) os="linux" ;;
    Darwin) os="darwin" ;;
    *) err "unsupported OS: $os (use install.ps1 on Windows)" ;;
  esac
  case "$arch" in
    x86_64|amd64) arch="x86_64" ;;
    arm64|aarch64) arch="arm64" ;;
    *) err "unsupported architecture: $arch" ;;
  esac
  PLATFORM="${os}-${arch}"
}

resolve_version() {
  [ "$VERSION" != "latest" ] && return 0
  VERSION="$(download_stdout "https://api.github.com/repos/$OWNER/$REPO/releases/latest" \
    | grep '"tag_name"' | head -1 | sed -E 's/.*"tag_name": *"([^"]+)".*/\1/')"
  [ -n "$VERSION" ] || err "could not resolve the latest release (set --version explicitly)"
}

verify_sha256() {  # <file> <sha-file>
  expected="$(cut -d' ' -f1 < "$2")"
  if have sha256sum; then actual="$(sha256sum "$1" | cut -d' ' -f1)"
  elif have shasum; then actual="$(shasum -a 256 "$1" | cut -d' ' -f1)"
  else warn "no sha256 tool found; skipping checksum verification"; return 0; fi
  [ "$actual" = "$expected" ] || err "checksum mismatch (expected $expected, got $actual)"
  info "checksum ok"
}

shell_rc_and_line() {  # sets RC and PATH_LINE for the user's shell
  case "$(basename "${SHELL:-sh}")" in
    fish) RC="$HOME/.config/fish/config.fish"; PATH_LINE="fish_add_path $BIN_DIR" ;;
    zsh)  RC="${ZDOTDIR:-$HOME}/.zshrc"; PATH_LINE="export PATH=\"$BIN_DIR:\$PATH\"" ;;
    bash) if [ "$(uname -s)" = "Darwin" ]; then RC="$HOME/.bash_profile"; else RC="$HOME/.bashrc"; fi
          PATH_LINE="export PATH=\"$BIN_DIR:\$PATH\"" ;;
    *)    RC="$HOME/.profile"; PATH_LINE="export PATH=\"$BIN_DIR:\$PATH\"" ;;
  esac
}

ensure_path() {
  case ":$PATH:" in *":$BIN_DIR:"*) return 0 ;; esac   # already on PATH -> nothing to do
  marker="# added by parse-anything installer"
  shell_rc_and_line
  mkdir -p "$(dirname "$RC")"
  if ! { [ -f "$RC" ] && grep -qF "$marker" "$RC"; }; then
    printf '\n%s\n%s\n' "$marker" "$PATH_LINE" >> "$RC"
    info "added $BIN_DIR to PATH in $RC"
  fi
  # shellcheck disable=SC2016  # the literal $PATH is intentional -- it is for the user's shell to expand
  printf '\n  -> restart your shell, or run:  export PATH="%s:$PATH"\n' "$BIN_DIR"
}

do_install() {
  detect_platform
  resolve_version
  asset="parse-anything-${VERSION}-${PLATFORM}.tar.gz"
  base="https://github.com/$OWNER/$REPO/releases/download/$VERSION"
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

  info "downloading $asset"
  download "$base/$asset" "$tmp/pkg.tar.gz" || err "download failed: $base/$asset"
  if download "$base/$asset.sha256" "$tmp/pkg.sha256" 2>/dev/null; then
    verify_sha256 "$tmp/pkg.tar.gz" "$tmp/pkg.sha256"
  else
    warn "no checksum published for $asset; skipping verification"
  fi

  info "installing to $DATA_DIR"
  rm -rf "$DATA_DIR"; mkdir -p "$DATA_DIR"
  tar -xzf "$tmp/pkg.tar.gz" -C "$DATA_DIR" --strip-components=1

  mkdir -p "$BIN_DIR"
  launcher="$DATA_DIR/bin/parse-anything"
  [ -e "$launcher" ] || err "bundle layout unexpected: $launcher not found"
  for cmd in $COMMANDS; do ln -sf "$launcher" "$BIN_DIR/$cmd"; done
  info "linked: $COMMANDS -> $launcher"

  ensure_path
  if "$launcher" --help >/dev/null 2>&1; then
    printf '\nparse-anything %s installed. Try:  parse-anything --pdf doc.pdf --out out/ --mode deterministic\n' "$VERSION"
  else
    warn "installed, but the self-check (parse-anything --help) failed"
  fi
}

do_uninstall() {
  for cmd in $COMMANDS; do
    if [ -L "$BIN_DIR/$cmd" ] || [ -e "$BIN_DIR/$cmd" ]; then rm -f "$BIN_DIR/$cmd"; info "removed $BIN_DIR/$cmd"; fi
  done
  if [ -d "$DATA_DIR" ]; then rm -rf "$DATA_DIR"; info "removed $DATA_DIR"; fi
  info "a PATH line marked '# added by parse-anything installer' in your shell rc can be removed manually"
}

case "$ACTION" in
  install) do_install ;;
  uninstall) do_uninstall ;;
esac
