#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# JCode Universal Installer
# One command. Installs everything.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/ShakenTheCoder/JcodeAgent/main/install.sh | bash
#
# What it does (only if not already installed):
#   1. Installs Python 3.12+
#   2. Installs Ollama
#   3. Pulls AI models (qwen2.5-coder:14b, qwen2.5-coder:7b, deepseek-r1:14b)
#   4. Clones/updates JCode
#   5. Creates venv + installs dependencies
#   6. Adds 'jcode' to your PATH
# ──────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Colors ─────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ── Globals ────────────────────────────────────────────────────────
# Models: coding (qwen2.5-coder) + reasoning (deepseek-r1) for multi-model routing
JCODE_HOME="${JCODE_HOME:-$HOME/JcodeAgent}"
JCODE_REPO="https://github.com/ShakenTheCoder/JcodeAgent.git"
MIN_PYTHON="3.10"
MODELS=("qwen2.5-coder:14b" "qwen2.5-coder:7b" "deepseek-r1:14b")

# ── Spinner ────────────────────────────────────────────────────────
_spinner_pid=""

spin_start() {
    local msg="$1"
    local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
    (
        while true; do
            for f in "${frames[@]}"; do
                printf "\r  ${CYAN}%s${NC} ${DIM}%s${NC}" "$f" "$msg"
                sleep 0.08
            done
        done
    ) &
    _spinner_pid=$!
    disown "$_spinner_pid" 2>/dev/null
}

spin_stop() {
    if [[ -n "$_spinner_pid" ]]; then
        kill "$_spinner_pid" 2>/dev/null
        wait "$_spinner_pid" 2>/dev/null || true
        _spinner_pid=""
        printf "\r\033[2K"
    fi
}

# ── Helpers ────────────────────────────────────────────────────────
ok()      { echo -e "  ${GREEN}✓${NC} $*"; }
info()    { echo -e "  ${DIM}$*${NC}"; }
warn()    { echo -e "  ${YELLOW}!${NC} $*"; }
fail()    { spin_stop; echo -e "  ${RED}✗${NC} $*"; exit 1; }
section() { echo -e "\n  ${BOLD}${CYAN}$*${NC}\n"; }

command_exists() { command -v "$1" &>/dev/null; }

version_gte() {
    printf '%s\n%s' "$2" "$1" | sort -V -C
}

detect_os() {
    case "$(uname -s)" in
        Darwin*)  echo "macos"  ;;
        Linux*)   echo "linux"  ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *)        echo "unknown" ;;
    esac
}

detect_arch() {
    case "$(uname -m)" in
        x86_64|amd64)  echo "amd64" ;;
        arm64|aarch64) echo "arm64" ;;
        *)             echo "$(uname -m)" ;;
    esac
}

# ── Progress bar ───────────────────────────────────────────────────
progress_bar() {
    local current=$1 total=$2 label=$3
    local width=30
    local pct=$((current * 100 / total))
    local filled=$((current * width / total))
    local empty=$((width - filled))
    local bar=""
    for ((i=0; i<filled; i++)); do bar+="█"; done
    for ((i=0; i<empty; i++)); do bar+="░"; done
    printf "\r  ${DIM}%s${NC} ${CYAN}%s${NC} ${DIM}%d%%${NC}" "$label" "$bar" "$pct"
}

# ── Banner ─────────────────────────────────────────────────────────
banner() {
    echo ""
    echo -e "${BOLD}${CYAN}"
    cat << 'EOF'
     ██╗ ██████╗ ██████╗ ██████╗ ███████╗
     ██║██╔════╝██╔═══██╗██╔══██╗██╔════╝
     ██║██║     ██║   ██║██║  ██║█████╗
██   ██║██║     ██║   ██║██║  ██║██╔══╝
╚█████╔╝╚██████╗╚██████╔╝██████╔╝███████╗
 ╚════╝  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝
EOF
    echo -e "${NC}"
    echo -e "  ${DIM}Your local, unlimited & private software engineer${NC}"
    echo -e "  ${DIM}One command. Everything you need.${NC}"
    echo ""
    echo -e "  ${DIM}─────────────────────────────────────────────────${NC}"
    echo ""
}

# ══════════════════════════════════════════════════════════════════
# Step 1: Python
# ══════════════════════════════════════════════════════════════════
install_python() {
    section "Python"

    local python_cmd=""

    for cmd in python3 python python3.12 python3.11 python3.10; do
        if command_exists "$cmd"; then
            local ver
            ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
            local major_minor
            major_minor=$(echo "$ver" | cut -d. -f1-2)
            if version_gte "$major_minor" "$MIN_PYTHON"; then
                python_cmd="$cmd"
                ok "Python $ver"
                break
            fi
        fi
    done

    if [[ -z "$python_cmd" ]]; then
        warn "Python $MIN_PYTHON+ not found. Installing..."

        local os
        os=$(detect_os)

        case "$os" in
            macos)
                if command_exists brew; then
                    spin_start "Installing Python via Homebrew..."
                    brew install python@3.12 &>/dev/null
                    spin_stop
                else
                    spin_start "Installing Homebrew..."
                    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" &>/dev/null
                    spin_stop
                    if [[ -f "/opt/homebrew/bin/brew" ]]; then
                        eval "$(/opt/homebrew/bin/brew shellenv)"
                    elif [[ -f "/usr/local/bin/brew" ]]; then
                        eval "$(/usr/local/bin/brew shellenv)"
                    fi
                    spin_start "Installing Python via Homebrew..."
                    brew install python@3.12 &>/dev/null
                    spin_stop
                fi
                python_cmd="python3"
                ;;
            linux)
                if command_exists apt-get; then
                    spin_start "Installing Python via apt..."
                    sudo apt-get update -qq &>/dev/null
                    sudo apt-get install -y -qq python3 python3-venv python3-pip &>/dev/null
                    spin_stop
                elif command_exists dnf; then
                    spin_start "Installing Python via dnf..."
                    sudo dnf install -y python3 python3-pip &>/dev/null
                    spin_stop
                elif command_exists pacman; then
                    spin_start "Installing Python via pacman..."
                    sudo pacman -Sy --noconfirm python python-pip &>/dev/null
                    spin_stop
                elif command_exists apk; then
                    spin_start "Installing Python via apk..."
                    sudo apk add python3 py3-pip &>/dev/null
                    spin_stop
                else
                    fail "Could not detect package manager. Install Python $MIN_PYTHON+ manually: https://www.python.org/downloads/"
                fi
                python_cmd="python3"
                ;;
            *)
                fail "Unsupported OS. Install Python $MIN_PYTHON+ manually: https://www.python.org/downloads/"
                ;;
        esac

        if ! command_exists "$python_cmd"; then
            fail "Python installation failed. Install manually: https://www.python.org/downloads/"
        fi
        ok "Python installed: $($python_cmd --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')"
    fi

    PYTHON_CMD="$python_cmd"
}

# ══════════════════════════════════════════════════════════════════
# Step 2: Ollama
# ══════════════════════════════════════════════════════════════════
install_ollama() {
    section "Ollama"

    if command_exists ollama; then
        ok "Ollama $(ollama --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo 'installed')"
    else
        warn "Ollama not found. Installing..."

        local os
        os=$(detect_os)

        case "$os" in
            macos)
                if command_exists brew; then
                    spin_start "Installing Ollama via Homebrew..."
                    brew install ollama &>/dev/null
                    spin_stop
                else
                    spin_start "Downloading Ollama..."
                    curl -fsSL https://ollama.ai/install.sh | sh &>/dev/null
                    spin_stop
                fi
                ;;
            linux)
                spin_start "Downloading Ollama..."
                curl -fsSL https://ollama.ai/install.sh | sh &>/dev/null
                spin_stop
                ;;
            *)
                fail "Please install Ollama manually: https://ollama.ai/download"
                ;;
        esac

        if ! command_exists ollama; then
            fail "Ollama installation failed. Install manually: https://ollama.ai/download"
        fi
        ok "Ollama installed"
    fi
}

# ══════════════════════════════════════════════════════════════════
# Step 3: Start Ollama & pull models
# ══════════════════════════════════════════════════════════════════
setup_models() {
    section "AI Models"

    # Make sure Ollama is running
    if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
        spin_start "Starting Ollama server..."
        ollama serve &>/dev/null &
        OLLAMA_PID=$!

        local retries=0
        while ! curl -sf http://localhost:11434/api/tags &>/dev/null; do
            retries=$((retries + 1))
            if [[ $retries -gt 30 ]]; then
                spin_stop
                fail "Ollama failed to start. Try running 'ollama serve' manually."
            fi
            sleep 1
        done
        spin_stop
        ok "Ollama server started"
    else
        ok "Ollama server running"
    fi

    # Pull each model
    local installed_models
    installed_models=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' || echo "")

    local total=${#MODELS[@]}
    local current=0

    for model in "${MODELS[@]}"; do
        current=$((current + 1))
        if echo "$installed_models" | grep -q "^${model}"; then
            ok "$model"
        else
            spin_start "Downloading $model... (this may take 10-15 min)"
            ollama pull "$model" &>/dev/null
            spin_stop
            ok "$model downloaded"
        fi
    done
}

# ══════════════════════════════════════════════════════════════════
# Step 4: JCode
# ══════════════════════════════════════════════════════════════════
install_jcode() {
    section "JCode"

    # Clone or update
    if [[ -d "$JCODE_HOME" ]]; then
        if [[ -d "$JCODE_HOME/.git" ]]; then
            spin_start "Updating JCode..."
            cd "$JCODE_HOME"
            git pull --ff-only &>/dev/null 2>&1 || true
            spin_stop
            ok "Updated to latest"
        else
            ok "JCode directory exists"
        fi
    else
        spin_start "Downloading JCode..."
        if command_exists git; then
            git clone "$JCODE_REPO" "$JCODE_HOME" &>/dev/null 2>&1
        else
            local zip_url="${JCODE_REPO%.git}/archive/refs/heads/main.zip"
            local tmp_zip="/tmp/jcode_download.zip"
            curl -fsSL "$zip_url" -o "$tmp_zip"
            unzip -qo "$tmp_zip" -d /tmp/jcode_extract
            mv /tmp/jcode_extract/JcodeAgent-main "$JCODE_HOME"
            rm -rf "$tmp_zip" /tmp/jcode_extract
        fi
        spin_stop
        ok "Downloaded to $JCODE_HOME"
    fi

    cd "$JCODE_HOME"

    # Virtual environment
    if [[ ! -d "$JCODE_HOME/.venv" ]]; then
        spin_start "Creating Python virtual environment..."
        "$PYTHON_CMD" -m venv .venv
        spin_stop
        ok "Virtual environment created"
    else
        ok "Virtual environment exists"
    fi

    # Install
    # shellcheck disable=SC1091
    source "$JCODE_HOME/.venv/bin/activate"

    spin_start "Installing dependencies..."
    pip install --upgrade pip -q &>/dev/null
    pip install -e . -q &>/dev/null
    spin_stop
    ok "JCode installed"
}

# ══════════════════════════════════════════════════════════════════
# Step 5: Add to PATH
# ══════════════════════════════════════════════════════════════════
setup_path() {
    section "PATH"

    local venv_bin="$JCODE_HOME/.venv/bin"
    local shell_rc=""

    case "$(basename "${SHELL:-/bin/bash}")" in
        zsh)  shell_rc="$HOME/.zshrc" ;;
        bash)
            if [[ -f "$HOME/.bash_profile" ]]; then
                shell_rc="$HOME/.bash_profile"
            else
                shell_rc="$HOME/.bashrc"
            fi
            ;;
        fish) shell_rc="$HOME/.config/fish/config.fish" ;;
        *)    shell_rc="$HOME/.profile" ;;
    esac

    local path_line="export PATH=\"$venv_bin:\$PATH\""

    if [[ -f "$shell_rc" ]] && grep -qF "$venv_bin" "$shell_rc" 2>/dev/null; then
        ok "PATH configured in $shell_rc"
    else
        {
            echo ""
            echo "# JCode — Local AI Coding Agent"
            echo "$path_line"
        } >> "$shell_rc"
        ok "Added to PATH in $shell_rc"
    fi

    export PATH="$venv_bin:$PATH"
}

# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════
print_summary() {
    local py_ver
    py_ver=$(${PYTHON_CMD} --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
    local ollama_ver
    ollama_ver=$(ollama --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo 'installed')

    echo ""
    echo -e "  ${DIM}─────────────────────────────────────────────────${NC}"
    echo ""
    echo -e "  ${BOLD}${GREEN}Installation complete.${NC}"
    echo ""
    echo -e "  ${DIM}Python${NC}    ${CYAN}${py_ver}${NC}"
    echo -e "  ${DIM}Ollama${NC}    ${CYAN}${ollama_ver}${NC}"
    echo -e "  ${DIM}Models${NC}    ${CYAN}${MODELS[*]}${NC}"
    echo -e "  ${DIM}Location${NC}  ${CYAN}${JCODE_HOME}${NC}"
    echo ""
    echo -e "  ${DIM}─────────────────────────────────────────────────${NC}"
    echo ""
    echo -e "  ${BOLD}Get started:${NC}"
    echo ""
    echo -e "    ${CYAN}\$ jcode${NC}"
    echo -e "    ${DIM}jcode>${NC} build a todo list web app"
    echo ""
    echo -e "  ${DIM}If 'jcode' isn't found, open a new terminal or run:${NC}"
    echo -e "  ${DIM}source ~/.zshrc  (or ~/.bashrc)${NC}"
    echo ""
}

# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════
main() {
    banner

    local os arch
    os=$(detect_os)
    arch=$(detect_arch)
    info "System: $os ($arch)"

    install_python
    install_ollama
    setup_models
    install_jcode
    setup_path
    print_summary
}

main "$@"
