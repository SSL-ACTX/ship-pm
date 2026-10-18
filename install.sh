#!/bin/sh
set -eu

# install.sh - Official standalone installer for ship (Agnostic Shell Package Orchestrator)

DEFAULT_REPO_RAW="https://raw.githubusercontent.com/SSL-ACTX/ship-pm/main/bin/ship"
VERSION="0.0.1"

# Target installation directory detection:
# 1. Use user-specified SHIP_BIN_TARGET if provided.
# 2. Check writable directories already in PATH (prefer ~/.local/bin or $PREFIX/bin or /usr/local/bin).
# 3. Fallback to ~/.local/bin (or $PREFIX/bin in Termux).
find_smart_bin_target() {
  if [ -n "${SHIP_BIN_TARGET:-}" ]; then
    echo "$SHIP_BIN_TARGET"
    return 0
  fi

  # In Termux: check ~/.local/bin first (to avoid shadowing by older binaries), then PREFIX/bin
  if [ -n "${TERMUX_VERSION:-}" ] || [ -d "/data/data/com.termux" ]; then
    if [ -d "${HOME}/.local/bin" ] && [ -w "${HOME}/.local/bin" ]; then
      echo "${HOME}/.local/bin"
      return 0
    fi
    _pfx_bin="${PREFIX:-/data/data/com.termux/files/usr}/bin"
    if [ -w "$_pfx_bin" ]; then
      echo "$_pfx_bin"
      return 0
    fi
    echo "${HOME}/.local/bin"
    return 0
  fi

  # Standard Linux / Unix
  if [ -w "/usr/local/bin" ]; then
    echo "/usr/local/bin"
    return 0
  fi

  echo "${HOME}/.local/bin"
}

SHIP_BIN_TARGET="$(find_smart_bin_target)"
mkdir -p "$SHIP_BIN_TARGET"

echo "==> Installing ship to ${SHIP_BIN_TARGET}/ship..."

SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"
if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/bin/ship" ]; then
  cp "$SCRIPT_DIR/bin/ship" "$SHIP_BIN_TARGET/ship"
elif [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/ship" ]; then
  cp "$SCRIPT_DIR/ship" "$SHIP_BIN_TARGET/ship"
else
  # Remote curl / wget installer
  SOURCE_URL="${SHIP_SOURCE_URL:-$DEFAULT_REPO_RAW}"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$SOURCE_URL" -o "$SHIP_BIN_TARGET/ship"
  elif command -v wget >/dev/null 2>&1; then
    wget -q -O "$SHIP_BIN_TARGET/ship" "$SOURCE_URL"
  else
    echo "Error: curl or wget is required to install ship." >&2
    exit 1
  fi
fi

chmod +x "$SHIP_BIN_TARGET/ship"

# Check if SHIP_BIN_TARGET is in PATH; if not, configure shell profile
case ":$PATH:" in
  *":$SHIP_BIN_TARGET:"*)
    # Already in PATH
    ;;
  *)
    _export_line="export PATH=\"$SHIP_BIN_TARGET:\$PATH\""
    _configured=0

    # Auto-detect shell RC files
    for _rc in "${HOME}/.bashrc" "${HOME}/.zshrc" "${HOME}/.profile"; do
      if [ -f "$_rc" ]; then
        if ! grep -qF "$SHIP_BIN_TARGET" "$_rc" 2>/dev/null; then
          printf "\n# Added by ship installer\n%s\n" "$_export_line" >> "$_rc"
          echo "==> Added $SHIP_BIN_TARGET to $_rc"
        fi
        _configured=1
      fi
    done

    if [ "$_configured" -eq 0 ]; then
      printf "\n# Added by ship installer\n%s\n" "$_export_line" >> "${HOME}/.profile"
      echo "==> Added $SHIP_BIN_TARGET to ~/.profile"
    fi
    echo "    (Please restart your shell or run 'export PATH=\"$SHIP_BIN_TARGET:\$PATH\"' for current session)"
    ;;
esac

# Silently prime central registry cache if possible
"$SHIP_BIN_TARGET/ship" registry update >/dev/null 2>&1 || true

echo ""
echo "==> ship successfully installed and primed!"
echo "Run 'ship help' to get started."
