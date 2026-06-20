#!/usr/bin/env zsh
# ─── macOS MCP Installer ─────────────────────────────────────────────────
# Installs the FDTD MCP server in a local .venv and configures MCP clients
# (Codex, Claude Code, Hermes).
#
# Usage:
#   ./scripts/macos/install_mcp.sh
#   ./scripts/macos/install_mcp.sh --rpc-url http://localhost:5000
#   ./scripts/macos/install_mcp.sh --rpc-url http://localhost:5000 --connection-mode stdio
#
# Options:
#   --rpc-url URL          FDTD RPC server URL (default: http://localhost:5000)
#   --connection-mode MODE MCP connection mode (default: stdio)
#   --help                 Print this help message

set -euo pipefail

# ─── Defaults ────────────────────────────────────────────────────────────

RPC_URL="${FDTD_RPC_URL:-http://localhost:5000}"
CONNECTION_MODE="stdio"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ─── Parse arguments ─────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rpc-url)
            RPC_URL="$2"
            shift 2
            ;;
        --connection-mode)
            CONNECTION_MODE="$2"
            shift 2
            ;;
        --help)
            cat <<'HELP'
macOS FDTD MCP Installer

Installs the FDTD MCP server and configures MCP clients.

Usage:
  install_mcp.sh [--rpc-url URL] [--connection-mode MODE]

Options:
  --rpc-url URL           FDTD RPC server URL (default: http://localhost:5000)
  --connection-mode MODE  Connection mode (default: stdio)
  --help                  Print this help message

Environment variables:
  FDTD_RPC_URL            Override the default RPC URL
HELP
            exit 0
            ;;
        *)
            echo "Error: unknown argument '$1'. Use --help for usage." >&2
            exit 1
            ;;
    esac
done

# ─── Step 1: Check Python version ────────────────────────────────────────

echo "==> Checking Python version..."

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
        major="${ver%.*}"
        if [[ "$major" -ge 3 ]] && [[ "${ver#*.}" -ge 10 || "$major" -gt 3 ]]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    echo "Error: Python 3.10+ is required but was not found." >&2
    echo "  Install it from https://www.python.org/downloads/" >&2
    exit 1
fi

echo "  Found $("$PYTHON" --version) at $(command -v "$PYTHON")"

# ─── Step 2: Create / activate virtual environment ───────────────────────

VENV_DIR="$PROJECT_ROOT/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
    echo "==> Creating virtual environment at $VENV_DIR..."
    "$PYTHON" -m venv "$VENV_DIR"
else
    echo "==> Virtual environment already exists at $VENV_DIR"
fi

echo "  Activating venv..."
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# ─── Step 3: Install runtime dependencies ────────────────────────────────

echo "==> Installing runtime dependencies from requirements-runtime.txt..."
"$PYTHON" -m pip install --quiet --upgrade pip
"$PYTHON" -m pip install --quiet -r "$PROJECT_ROOT/requirements-runtime.txt"
echo "  Done."

# ─── Step 4: Health check ────────────────────────────────────────────────

echo "==> Running health check against $RPC_URL ..."

HEALTH_URL="${RPC_URL%/}/health"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "$HEALTH_URL" 2>/dev/null || echo "000")

if [[ "$HTTP_CODE" = "200" ]]; then
    echo "  Health check OK (HTTP 200)"
else
    echo "  Warning: health check returned HTTP $HTTP_CODE (not 200)." >&2
    echo "  The RPC server may not be running yet. You can start it later with:" >&2
    echo "    $VENV_DIR/bin/python -m src.server" >&2
fi

# ─── Step 5: Configure MCP clients ───────────────────────────────────────

echo "==> Configuring MCP clients..."

CONFIGURE_SCRIPT="$SCRIPT_DIR/configure_mcp_clients.py"

if [[ -f "$CONFIGURE_SCRIPT" ]]; then
    "$PYTHON" "$CONFIGURE_SCRIPT" \
        --target all \
        --rpc-url "$RPC_URL" \
        --connection-mode "$CONNECTION_MODE"
    echo "  MCP clients configured."
else
    echo "  Warning: configure_mcp_clients.py not found at $CONFIGURE_SCRIPT" >&2
fi

# ─── Step 6: Print next steps ────────────────────────────────────────────

echo ""
echo "============================================"
echo "  Installation complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo ""
echo "  Codex:"
echo "    Restart Codex. The fdtd MCP server has been added to:"
echo "      ~/.codex/config.toml"
echo ""
echo "  Claude Code:"
echo "    Restart Claude Code. The fdtd MCP server has been added to:"
echo "      <project-root>/.mcp.json"
echo ""
echo "  Hermes:"
echo "    Restart Hermes. The fdtd MCP server has been added to:"
echo "      ~/.hermes/config.yaml"
echo ""
echo "  Start the FDTD RPC server (if not running):"
echo "    $VENV_DIR/bin/python -m src.server"
echo ""
echo "  Verify the server is healthy:"
echo "    curl $RPC_URL/health"
echo ""
