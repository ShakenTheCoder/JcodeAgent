# ──────────────────────────────────────────────────────────────────
# JCode Universal Installer for Windows
# One command. Installs everything. You're welcome. 🤖
#
# Usage:
#   iwr -useb https://jcode.dev/install.ps1 | iex
#
# What it does (only if not already installed):
#   1. Installs Python 3.12+
#   2. Installs Ollama
#   3. Pulls AI models (deepseek-r1:14b, qwen2.5-coder:14b)
#   4. Clones/updates JCode
#   5. Creates venv + installs dependencies
#   6. Adds 'jcode' to your PATH
# ──────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

# ── Config ─────────────────────────────────────────────────────────
$JCODE_HOME  = if ($env:JCODE_HOME) { $env:JCODE_HOME } else { Join-Path $env:USERPROFILE "JcodeAgent" }
$JCODE_REPO  = "https://github.com/YOUR_USERNAME/JcodeAgent.git"  # ← Update this
$MIN_PYTHON  = [version]"3.10"
$MODELS      = @("deepseek-r1:14b", "qwen2.5-coder:14b")
$PYTHON_CMD  = ""

# ── Helpers ────────────────────────────────────────────────────────
function Write-Info    { param($msg) Write-Host "i  $msg" -ForegroundColor Blue }
function Write-Success { param($msg) Write-Host "✅ $msg" -ForegroundColor Green }
function Write-Warn    { param($msg) Write-Host "⚠  $msg" -ForegroundColor Yellow }
function Write-Fail    { param($msg) Write-Host "❌ $msg" -ForegroundColor Red; exit 1 }
function Write-Step    { param($msg) Write-Host "`n── $msg ──" -ForegroundColor Cyan }

function Test-Command { param($cmd) return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# ── Banner ─────────────────────────────────────────────────────────
function Show-Banner {
    Write-Host ""
    Write-Host "     ╦╔═╗╔═╗╔╦╗╔═╗" -ForegroundColor Cyan
    Write-Host "     ║║  ║ ║ ║║║╣"   -ForegroundColor Cyan
    Write-Host "    ╚╝╚═╝╚═╝═╩╝╚═╝  Installer" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "    One command. Everything you need. 🤖" -ForegroundColor White
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════
# Step 1: Python
# ══════════════════════════════════════════════════════════════════
function Install-Python {
    Write-Step "Checking Python"

    # Search for existing Python
    foreach ($cmd in @("python", "python3", "py")) {
        if (Test-Command $cmd) {
            try {
                $verOutput = & $cmd --version 2>&1
                if ($verOutput -match "(\d+\.\d+\.\d+)") {
                    $ver = [version]$Matches[1]
                    if ($ver -ge $MIN_PYTHON) {
                        $script:PYTHON_CMD = $cmd
                        Write-Success "Python $ver found ($cmd)"
                        return
                    }
                }
            } catch { }
        }
    }

    # Also check py launcher with version flag
    if (Test-Command "py") {
        try {
            $verOutput = & py -3 --version 2>&1
            if ($verOutput -match "(\d+\.\d+\.\d+)") {
                $ver = [version]$Matches[1]
                if ($ver -ge $MIN_PYTHON) {
                    $script:PYTHON_CMD = "py -3"
                    Write-Success "Python $ver found (py -3)"
                    return
                }
            }
        } catch { }
    }

    Write-Warn "Python $MIN_PYTHON+ not found. Installing..."

    # Try winget first (built into Windows 10/11)
    if (Test-Command "winget") {
        Write-Info "Installing Python via winget..."
        winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
    } else {
        # Download installer directly
        Write-Info "Downloading Python installer..."
        $pyUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
        $pyInstaller = Join-Path $env:TEMP "python-installer.exe"
        Invoke-WebRequest -Uri $pyUrl -OutFile $pyInstaller -UseBasicParsing

        Write-Info "Running Python installer (this may take a minute)..."
        Start-Process -FilePath $pyInstaller -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0" -Wait
        Remove-Item $pyInstaller -ErrorAction SilentlyContinue
    }

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

    # Verify
    foreach ($cmd in @("python", "python3", "py")) {
        if (Test-Command $cmd) {
            try {
                $verOutput = & $cmd --version 2>&1
                if ($verOutput -match "(\d+\.\d+\.\d+)") {
                    $script:PYTHON_CMD = $cmd
                    Write-Success "Python installed: $($Matches[1])"
                    return
                }
            } catch { }
        }
    }

    Write-Fail "Python installation failed. Please install manually: https://www.python.org/downloads/"
}

# ══════════════════════════════════════════════════════════════════
# Step 2: Ollama
# ══════════════════════════════════════════════════════════════════
function Install-Ollama {
    Write-Step "Checking Ollama"

    if (Test-Command "ollama") {
        Write-Success "Ollama already installed"
        return
    }

    Write-Warn "Ollama not found. Installing..."

    if (Test-Command "winget") {
        Write-Info "Installing Ollama via winget..."
        winget install Ollama.Ollama --accept-package-agreements --accept-source-agreements --silent
    } else {
        Write-Info "Downloading Ollama installer..."
        $ollamaUrl = "https://ollama.ai/download/OllamaSetup.exe"
        $ollamaInstaller = Join-Path $env:TEMP "OllamaSetup.exe"
        Invoke-WebRequest -Uri $ollamaUrl -OutFile $ollamaInstaller -UseBasicParsing

        Write-Info "Running Ollama installer..."
        Start-Process -FilePath $ollamaInstaller -ArgumentList "/SILENT" -Wait
        Remove-Item $ollamaInstaller -ErrorAction SilentlyContinue
    }

    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

    if (-not (Test-Command "ollama")) {
        Write-Fail "Ollama installation failed. Install manually: https://ollama.ai/download"
    }

    Write-Success "Ollama installed"
}

# ══════════════════════════════════════════════════════════════════
# Step 3: Start Ollama & pull models
# ══════════════════════════════════════════════════════════════════
function Setup-Models {
    Write-Step "Checking AI models"

    # Check if Ollama server is running
    $running = $false
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) { $running = $true }
    } catch { }

    if (-not $running) {
        Write-Info "Starting Ollama server..."
        Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 5

        # Wait for it
        $retries = 0
        while ($retries -lt 30) {
            try {
                $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
                if ($response.StatusCode -eq 200) { break }
            } catch { }
            $retries++
            Start-Sleep -Seconds 1
        }

        if ($retries -ge 30) {
            Write-Fail "Ollama failed to start. Try running 'ollama serve' manually."
        }

        Write-Success "Ollama server started"
    } else {
        Write-Success "Ollama server already running"
    }

    # Get installed models
    $installed = ""
    try { $installed = & ollama list 2>&1 | Out-String } catch { }

    foreach ($model in $MODELS) {
        if ($installed -match [regex]::Escape($model)) {
            Write-Success "Model already downloaded: $model"
        } else {
            Write-Info "Downloading $model... (this may take 10-15 min on first run)"
            & ollama pull $model
            Write-Success "Model ready: $model"
        }
    }
}

# ══════════════════════════════════════════════════════════════════
# Step 4: JCode
# ══════════════════════════════════════════════════════════════════
function Install-JCode {
    Write-Step "Setting up JCode"

    if (Test-Path $JCODE_HOME) {
        if (Test-Path (Join-Path $JCODE_HOME ".git")) {
            Write-Info "Updating JCode..."
            Push-Location $JCODE_HOME
            try { & git pull --ff-only 2>&1 | Out-Null } catch {
                Write-Warn "Could not auto-update. Continuing with existing version."
            }
            Pop-Location
        } else {
            Write-Success "JCode directory already exists: $JCODE_HOME"
        }
    } else {
        Write-Info "Downloading JCode..."
        if (Test-Command "git") {
            & git clone $JCODE_REPO $JCODE_HOME
        } else {
            # Fallback: download as zip
            $zipUrl = $JCODE_REPO -replace "\.git$", "/archive/refs/heads/main.zip"
            $tmpZip = Join-Path $env:TEMP "jcode_download.zip"
            Invoke-WebRequest -Uri $zipUrl -OutFile $tmpZip -UseBasicParsing
            Expand-Archive -Path $tmpZip -DestinationPath $env:TEMP -Force
            Move-Item (Join-Path $env:TEMP "JcodeAgent-main") $JCODE_HOME
            Remove-Item $tmpZip -ErrorAction SilentlyContinue
        }
        Write-Success "JCode downloaded to: $JCODE_HOME"
    }

    Push-Location $JCODE_HOME

    # Create virtual environment
    $venvPath = Join-Path $JCODE_HOME ".venv"
    if (-not (Test-Path $venvPath)) {
        Write-Info "Creating Python virtual environment..."
        if ($PYTHON_CMD -eq "py -3") {
            & py -3 -m venv .venv
        } else {
            & $PYTHON_CMD -m venv .venv
        }
        Write-Success "Virtual environment created"
    } else {
        Write-Success "Virtual environment already exists"
    }

    # Activate and install
    $pipCmd = Join-Path $venvPath "Scripts" "pip.exe"
    & $pipCmd install --upgrade pip -q 2>&1 | Out-Null
    & $pipCmd install -e . -q
    Write-Success "JCode installed"

    Pop-Location
}

# ══════════════════════════════════════════════════════════════════
# Step 5: Add to PATH
# ══════════════════════════════════════════════════════════════════
function Setup-Path {
    Write-Step "Configuring PATH"

    $venvBin = Join-Path $JCODE_HOME ".venv" "Scripts"
    $currentPath = [System.Environment]::GetEnvironmentVariable("Path", "User")

    if ($currentPath -like "*$venvBin*") {
        Write-Success "PATH already configured"
    } else {
        [System.Environment]::SetEnvironmentVariable("Path", "$venvBin;$currentPath", "User")
        $env:Path = "$venvBin;$env:Path"
        Write-Success "Added to PATH: $venvBin"
    }
}

# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════
function Show-Summary {
    Write-Host ""
    Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Green
    Write-Host "  ║                                          ║" -ForegroundColor Green
    Write-Host "  ║   JCode is ready! 🚀                    ║" -ForegroundColor Green
    Write-Host "  ║                                          ║" -ForegroundColor Green
    Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Green
    Write-Host ""
    Write-Host "  To start JCode:" -ForegroundColor White
    Write-Host ""
    Write-Host "    jcode" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  If 'jcode' isn't found, open a new terminal first." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Quick start:" -ForegroundColor White
    Write-Host ""
    Write-Host "    jcode" -ForegroundColor Cyan
    Write-Host "    jcode> build a todo list web app" -ForegroundColor DarkGray
    Write-Host ""

    $pyVer = ""
    try {
        if ($PYTHON_CMD -eq "py -3") {
            $pyVer = & py -3 --version 2>&1
        } else {
            $pyVer = & $PYTHON_CMD --version 2>&1
        }
    } catch { $pyVer = "installed" }

    Write-Host "  Installed:" -ForegroundColor White
    Write-Host "    ✅ Python    $pyVer" -ForegroundColor Green
    Write-Host "    ✅ Ollama    installed" -ForegroundColor Green
    Write-Host "    ✅ Models    $($MODELS -join ', ')" -ForegroundColor Green
    Write-Host "    ✅ JCode     $JCODE_HOME" -ForegroundColor Green
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════
Show-Banner
Write-Info "Detected: Windows $([System.Environment]::OSVersion.Version)"

Install-Python
Install-Ollama
Setup-Models
Install-JCode
Setup-Path
Show-Summary
