#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────
# JCode Universal Installer
# One command. Installs everything. You're welcome. 🤖
#
# Usage:
#   curl -fsSL https://jcode.dev/install.sh | bash
#
# What it does (only if not already installed):
#   1. Installs Python 3.12+
#   2. Installs Ollama
#   3. Pulls AI models (deepseek-r1:14b, qwen2.5-coder:14b)
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
NC='\033[0m' # No Color

# ── Globals ────────────────────────────────────────────────────────
JCODE_HOME="${JCODE_HOME:-$HOME/JcodeAgent}"
JCODE_REPO="https://github.com/YOUR_USERNAME/JcodeAgent.git"  # ← Update this
MIN_PYTHON="3.10"
MODELS=("deepseek-r1:14b" "qwen2.5-coder:14b")

# ── Helpers ────────────────────────────────────────────────────────
info()    { echo -e "${BLUE}ℹ${NC}  $*"; }
success() { echo -e "${GREEN}✅${NC} $*"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $*"; }
fail()    { echo -e "${RED}❌${NC} $*"; exit 1; }
step()    { echo -e "\n${BOLD}${CYAN}── $* ──${NC}"; }

command_exists() { command -v "$1" &>/dev/null; }

# Compare semver: returns 0 if $1 >= $2
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

# ── Banner ─────────────────────────────────────────────────────────
banner() {
    echo -e "${BOLD}${CYAN}"
    cat << 'EOF'

     ╦╔═╗╔═╗╔╦╗╔═╗
     ║║  ║ ║ ║║║╣
    ╚╝╚═╝╚═╝═╩╝╚═╝  Installer

    One command. Everything you need. 🤖

EOF
    echo -e "${NC}"
}

# ══════════════════════════════════════════════════════════════════
# Step 1: Python
# ══════════════════════════════════════════════════════════════════
install_python() {
    step "Checking Python"

    local python_cmd=""

    # Find a suitable Python
    for cmd in python3 python python3.12 python3.11 python3.10; do
        if command_exists "$cmd"; then
            local ver
            ver=$("$cmd" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
            local major_minor
            major_minor=$(echo "$ver" | cut -d. -f1-2)
            if version_gte "$major_minor" "$MIN_PYTHON"; then
                python_cmd="$cmd"
                success "Python $ver found ($cmd)"
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
                    info "Installing Python via Homebrew..."
                    brew install python@3.12
                else
                    info "Installing Homebrew first..."
                    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                    # Add Homebrew to PATH for this session
                    if [[ -f "/opt/homebrew/bin/brew" ]]; then
                        eval "$(/opt/homebrew/bin/brew shellenv)"
                    elif [[ -f "/usr/local/bin/brew" ]]; then
                        eval "$(/usr/local/bin/brew shellenv)"
                    fi
                    brew install python@3.12
                fi
                python_cmd="python3"
                ;;
            linux)
                if command_exists apt-get; then
                    info "Installing Python via apt..."
                    sudo apt-get update -qq
                    sudo apt-get install -y -qq python3 python3-venv python3-pip
                elif command_exists dnf; then
                    info "Installing Python via dnf..."
                    sudo dnf install -y python3 python3-pip
                elif command_exists pacman; then
                    info "Installing Python via pacman..."
                    sudo pacman -Sy --noconfirm python python-pip
                elif command_exists apk; then
                    info "Installing Python via apk..."
                    sudo apk add python3 py3-pip
                else
                    fail "Could not detect package manager. Please install Python $MIN_PYTHON+ manually:\n   https://www.python.org/downloads/"
                fi
                python_cmd="python3"
                ;;
            *)
                fail "Unsupported OS. Please install Python $MIN_PYTHON+ manually:\n   https://www.python.org/downloads/"
                ;;
        esac

        # Verify installation
        if ! command_exists "$python_cmd"; then
            fail "Python installation failed. Please install manually:\n   https://www.python.org/downloads/"
        fi
        success "Python installed: $($python_cmd --version)"
    fi

    # Export for later steps
    PYTHON_CMD="$python_cmd"
}

# ══════════════════════════════════════════════════════════════════
# Step 2: Ollama
# ══════════════════════════════════════════════════════════════════
install_ollama() {
    step "Checking Ollama"

    if command_exists ollama; then
        success "Ollama already installed: $(ollama --version 2>/dev/null || echo 'version unknown')"
    else
        warn "Ollama not found. Installing..."

        local os
        os=$(detect_os)

        case "$os" in
            macos)
                if command_exists brew; then
                    brew install ollama
                else
                    info "Downloading Ollama for macOS..."
                    curl -fsSL https://ollama.ai/install.sh | sh
                fi
                ;;
            linux)
                info "Downloading Ollama for Linux..."
                curl -fsSL https://ollama.ai/install.sh | sh
                ;;
            *)
                fail "Please install Ollama manually:\n   https://ollama.ai/download"
                ;;
        esac

        if ! command_exists ollama; then
            fail "Ollama installation failed. Install manually:\n   https://ollama.ai/download"
        fi
        success "Ollama installed"
    fi
}

# ══════════════════════════════════════════════════════════════════
# Step 3: Start Ollama & pull models
# ══════════════════════════════════════════════════════════════════
setup_models() {
    step "Checking AI models"

    # Make sure Ollama is running
    if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
        info "Starting Ollama server..."
        ollama serve &>/dev/null &
        OLLAMA_PID=$!

        # Wait for it to come up
        local retries=0
        while ! curl -sf http://localhost:11434/api/tags &>/dev/null; do
            retries=$((retries + 1))
            if [[ $retries -gt 30 ]]; then
                fail "Ollama failed to start. Try running 'ollama serve' manually."
            fi
            sleep 1
        done
        success "Ollama server started"
    else
        success "Ollama server already running"
    fi

    # Pull each model if not already present
    local installed_models
    installed_models=$(ollama list 2>/dev/null | tail -n +2 | awk '{print $1}' || echo "")

    for model in "${MODELS[@]}"; do
        if echo "$installed_models" | grep -q "^${model}"; then
            success "Model already downloaded: ${model}"
        else
            info "Downloading ${model}... (this may take 10-15 min on first run)"
            ollama pull "$model"
            success "Model ready: ${model}"
        fi
    done
}

# ══════════════════════════════════════════════════════════════════
# Step 4: JCode
# ══════════════════════════════════════════════════════════════════
install_jcode() {
    step "Setting up JCode"

    # Clone or update
    if [[ -d "$JCODE_HOME" ]]; then
        if [[ -d "$JCODE_HOME/.git" ]]; then
            info "Updating JCode..."
            cd "$JCODE_HOME"
            git pull --ff-only 2>/dev/null || warn "Could not auto-update (local changes?). Continuing with existing version."
        else
            success "JCode directory already exists: $JCODE_HOME"
        fi
    else
        info "Downloading JCode..."
        if command_exists git; then
            git clone "$JCODE_REPO" "$JCODE_HOME"
        else
            # Fallback: download as zip
            local zip_url="${JCODE_REPO%.git}/archive/refs/heads/main.zip"
            local tmp_zip="/tmp/jcode_download.zip"
            curl -fsSL "$zip_url" -o "$tmp_zip"
            unzip -qo "$tmp_zip" -d /tmp/jcode_extract
            mv /tmp/jcode_extract/JcodeAgent-main "$JCODE_HOME"
            rm -rf "$tmp_zip" /tmp/jcode_extract
        fi
        success "JCode downloaded to: $JCODE_HOME"
    fi

    cd "$JCODE_HOME"

    # Create virtual environment
    if [[ ! -d "$JCODE_HOME/.venv" ]]; then
        info "Creating Python virtual environment..."
        "$PYTHON_CMD" -m venv .venv
        success "Virtual environment created"
    else
        success "Virtual environment already exists"
    fi

    # Activate and install
    # shellcheck disable=SC1091
    source "$JCODE_HOME/.venv/bin/activate"

    info "Installing JCode and dependencies..."
    pip install --upgrade pip -q
    pip install -e . -q
    success "JCode installed"
}

# ══════════════════════════════════════════════════════════════════
# Step 5: Add to PATH
# ══════════════════════════════════════════════════════════════════
setup_path() {
    step "Configuring PATH"

    local venv_bin="$JCODE_HOME/.venv/bin"
    local shell_rc=""

    # Determine shell config file
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
    local alias_line="alias jcode='$venv_bin/jcode'"

    # Check if already added
    if [[ -f "$shell_rc" ]] && grep -qF "$venv_bin" "$shell_rc" 2>/dev/null; then
        success "PATH already configured in $shell_rc"
    else
        {
            echo ""
            echo "# JCode — Local AI Coding Agent"
            echo "$path_line"
        } >> "$shell_rc"
        success "Added to PATH in $shell_rc"
    fi

    # Also export for current session
    export PATH="$venv_bin:$PATH"
}

# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════
print_summary() {
    echo ""
    echo -e "${BOLD}${GREEN}"
    cat << 'EOF'
  ╔══════════════════════════════════════════╗
  ║                                          ║
  ║   JCode is ready! 🚀                    ║
  ║                                          ║
  ╚══════════════════════════════════════════╝
EOF
    echo -e "${NC}"

    echo -e "  ${BOLD}To start JCode:${NC}"
    echo ""
    echo -e "    ${CYAN}jcode${NC}"
    echo ""
    echo -e "  ${DIM}If 'jcode' isn't found, open a new terminal first,${NC}"
    echo -e "  ${DIM}or run:  source ~/.zshrc  (or ~/.bashrc)${NC}"
    echo ""
    echo -e "  ${BOLD}Quick start:${NC}"
    echo ""
    echo -e "    ${CYAN}jcode${NC}"
    echo -e "    ${DIM}jcode>${NC} build a todo list web app"
    echo ""
    echo -e "  ${BOLD}Installed:${NC}"
    echo -e "    ✅ Python    $(${PYTHON_CMD} --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"
    echo -e "    ✅ Ollama    $(ollama --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' || echo 'installed')"
    echo -e "    ✅ Models    ${MODELS[*]}"
    echo -e "    ✅ JCode     $JCODE_HOME"
    echo ""
}

# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════
main() {
    banner

    local os
    os=$(detect_os)
    local arch
    arch=$(detect_arch)
    info "Detected: ${BOLD}$os ($arch)${NC}"

    install_python
    install_ollama
    setup_models
    install_jcode
    setup_path
    print_summary
}

main "$@"
