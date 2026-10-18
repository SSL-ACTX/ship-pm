#!/bin/sh
set -eu

# install.sh - Standalone installer for ship (Agnostic Shell Package Orchestrator)

REPO_GIT="${SHIP_REPO_GIT:-https://github.com/SSL-ACTX/ship-pm.git}"
VERSION="0.0.4"

# Target installation directory detection:
find_smart_bin_target() {
  if [ -n "${SHIP_BIN_TARGET:-}" ]; then
    echo "$SHIP_BIN_TARGET"
    return 0
  fi

  if [ -n "${TERMUX_VERSION:-}" ] || [ -d "/data/data/com.termux" ]; then
    _pfx_bin="${PREFIX:-/data/data/com.termux/files/usr}/bin"
    if [ -w "$_pfx_bin" ]; then
      echo "$_pfx_bin"
      return 0
    fi
    echo "${HOME}/.local/bin"
    return 0
  fi

  if [ -w "/usr/local/bin" ]; then
    echo "/usr/local/bin"
    return 0
  fi

  echo "${HOME}/.local/bin"
}

# UI Styling
if { [ -t 1 ] || [ -t 2 ]; } && [ -z "${NO_COLOR:-}" ] && [ "${TERM:-dumb}" != "dumb" ]; then
  _esc="$(printf '\033')"
  C_RESET="${_esc}[0m"
  C_BOLD="${_esc}[1m"
  C_GREEN="${_esc}[1;32m"
  C_YELLOW="${_esc}[1;33m"
  C_RED="${_esc}[1;31m"
else
  C_RESET=""
  C_BOLD=""
  C_GREEN=""
  C_YELLOW=""
  C_RED=""
fi

ui_status() {
  printf "%b%12s%b %s\n" "$C_GREEN" "$1" "$C_RESET" "$2" >&2
}

ui_warn() {
  printf "%b%12s%b %s\n" "$C_YELLOW" "warning:" "$C_RESET" "$*" >&2
}

ui_err() {
  printf "%b%12s%b %s\n" "$C_RED" "error:" "$C_RESET" "$*" >&2
}

# Determine SHIP_ROOT
if [ -n "${SHIP_ROOT:-}" ]; then
  SHIP_DIR="$SHIP_ROOT"
elif [ -n "${TERMUX_VERSION:-}" ] || [ -d "/data/data/com.termux" ]; then
  SHIP_DIR="${PREFIX:-/data/data/com.termux/files/usr}/share/ship"
else
  SHIP_DIR="${HOME}/.local/share/ship"
fi

SHIP_LIB_DIR="${SHIP_DIR}/lib"
SHIP_BIN_TARGET="$(find_smart_bin_target)"
mkdir -p "$SHIP_BIN_TARGET" "$SHIP_LIB_DIR"

ui_status "Installing" "ship to ${SHIP_BIN_TARGET}/ship"

SCRIPT_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo "")"

if [ -n "$SCRIPT_DIR" ] && [ -d "$SCRIPT_DIR/ship" ] && [ -f "$SCRIPT_DIR/bin/ship" ]; then
  # Local install from cloned git checkout
  ui_status "Copying" "core modules to $SHIP_LIB_DIR/ship"
  rm -rf "${SHIP_LIB_DIR}/ship"
  cp -r "$SCRIPT_DIR/ship" "${SHIP_LIB_DIR}/ship"
  cp "$SCRIPT_DIR/bin/ship" "$SHIP_BIN_TARGET/ship"
else
  # Remote curl / wget installer: clone or update repo directly into SHIP_DIR/registry
  ui_status "Cloning" "ship core repository..."
  if command -v git >/dev/null 2>&1; then
    rm -rf "${SHIP_DIR}/registry"
    git clone --depth 1 "$REPO_GIT" "${SHIP_DIR}/registry"
    rm -rf "${SHIP_LIB_DIR}/ship"
    cp -r "${SHIP_DIR}/registry/ship" "${SHIP_LIB_DIR}/ship"
    cp "${SHIP_DIR}/registry/bin/ship" "$SHIP_BIN_TARGET/ship"
  else
    ui_err "git is required to install ship."
    exit 1
  fi
fi

chmod +x "$SHIP_BIN_TARGET/ship"

# Check if SHIP_BIN_TARGET is in PATH; if not, configure shell profile
case ":$PATH:" in
  *":$SHIP_BIN_TARGET:"*)
    ;;
  *)
    _export_line="export PATH=\"$SHIP_BIN_TARGET:\$PATH\""
    _configured=0

    for _rc in "${HOME}/.bashrc" "${HOME}/.zshrc" "${HOME}/.profile"; do
      if [ -f "$_rc" ]; then
        if ! grep -qF "$SHIP_BIN_TARGET" "$_rc" 2>/dev/null; then
          printf "\n# Added by ship installer\n%s\n" "$_export_line" >> "$_rc"
          ui_status "Configured" "$_rc (added $SHIP_BIN_TARGET)"
        fi
        _configured=1
      fi
    done

    if [ "$_configured" -eq 0 ]; then
      printf "\n# Added by ship installer\n%s\n" "$_export_line" >> "${HOME}/.profile"
      ui_status "Configured" "${HOME}/.profile (added $SHIP_BIN_TARGET)"
    fi
    ui_warn "Restart your shell or run: export PATH=\"$SHIP_BIN_TARGET:\$PATH\""
    ;;
esac

# Test that the installed CLI runs cleanly
"$SHIP_BIN_TARGET/ship" --version >/dev/null 2>&1 || true

ui_status "Finished" "ship v$VERSION installed successfully"
printf "\nRun '%bship --help%b' to get started.\n" "$C_BOLD" "$C_RESET"
