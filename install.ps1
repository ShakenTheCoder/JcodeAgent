# ──────────────────────────────────────────────────────────────────
# JCode Universal Installer for Windows
# One command. Installs everything.
#
# Usage:
#   iwr -useb https://raw.githubusercontent.com/ShakenTheCoder/JcodeAgent/main/install.ps1 | iex
#
# What it does (only if not already installed):
#   1. Installs Python 3.12+
#   2. Installs Ollama
#   3. Pulls AI models (qwen2.5-coder:14b, qwen2.5-coder:7b, deepseek-r1:14b)
#   4. Clones/updates JCode
#   5. Creates venv + installs dependencies
#   6. Adds 'jcode' to your PATH
# ──────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

# ── Config ─────────────────────────────────────────────────────────
# Models: coding (qwen2.5-coder) + reasoning (deepseek-r1) for multi-model routing
$JCODE_HOME  = if ($env:JCODE_HOME) { $env:JCODE_HOME } else { Join-Path $env:USERPROFILE "JcodeAgent" }
$JCODE_REPO  = "https://github.com/ShakenTheCoder/JcodeAgent.git"
$MIN_PYTHON  = [version]"3.10"
$MODELS      = @("qwen2.5-coder:14b", "qwen2.5-coder:7b", "deepseek-r1:14b")
$PYTHON_CMD  = ""

# ── Helpers ────────────────────────────────────────────────────────
function Write-Ok      { param($msg) Write-Host "  " -NoNewline; Write-Host "+" -ForegroundColor Green -NoNewline; Write-Host " $msg" }
function Write-Info    { param($msg) Write-Host "  $msg" -ForegroundColor DarkGray }
function Write-Warn    { param($msg) Write-Host "  " -NoNewline; Write-Host "!" -ForegroundColor Yellow -NoNewline; Write-Host " $msg" }
function Write-Fail    { param($msg) Write-Host "  " -NoNewline; Write-Host "x" -ForegroundColor Red -NoNewline; Write-Host " $msg"; exit 1 }
function Write-Section { param($msg) Write-Host ""; Write-Host "  $msg" -ForegroundColor Cyan; Write-Host "" }

function Test-Command { param($cmd) return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# ── Spinner simulation ────────────────────────────────────────────
function Show-Spinner {
    param($msg, [scriptblock]$action)
    $frames = @("-", "\", "|", "/")
    $job = Start-Job -ScriptBlock $action
    $i = 0
    while ($job.State -eq "Running") {
        $f = $frames[$i % $frames.Count]
        Write-Host "`r  $f $msg" -NoNewline -ForegroundColor DarkGray
        Start-Sleep -Milliseconds 150
        $i++
    }
    Write-Host "`r                                                          `r" -NoNewline
    Receive-Job $job -ErrorAction SilentlyContinue | Out-Null
    Remove-Job $job -ErrorAction SilentlyContinue | Out-Null
}

# ── Banner ─────────────────────────────────────────────────────────
function Show-Banner {
    Write-Host ""
    $banner = @"
     ##  ######  ######  ######  #######
     ## ##    ## ##   ## ##   ## ##
     ## ##       ##   ## ##   ## #####
##   ## ##       ##   ## ##   ## ##
 #####   ######   ######  ######  #######
"@
    Write-Host $banner -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Your local, unlimited & private software engineer" -ForegroundColor DarkGray
    Write-Host "  One command. Everything you need." -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  -------------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════
# Step 1: Python
# ══════════════════════════════════════════════════════════════════
function Install-Python {
    Write-Section "Python"

    foreach ($cmd in @("python", "python3", "py")) {
        if (Test-Command $cmd) {
            try {
                $verOutput = & $cmd --version 2>&1
                if ($verOutput -match "(\d+\.\d+\.\d+)") {
                    $ver = [version]$Matches[1]
                    if ($ver -ge $MIN_PYTHON) {
                        $script:PYTHON_CMD = $cmd
                        Write-Ok "Python $ver"
                        return
                    }
                }
            } catch { }
        }
    }

    if (Test-Command "py") {
        try {
            $verOutput = & py -3 --version 2>&1
            if ($verOutput -match "(\d+\.\d+\.\d+)") {
                $ver = [version]$Matches[1]
                if ($ver -ge $MIN_PYTHON) {
                    $script:PYTHON_CMD = "py -3"
                    Write-Ok "Python $ver (py -3)"
                    return
                }
            }
        } catch { }
    }

    Write-Warn "Python $MIN_PYTHON+ not found. Installing..."

    if (Test-Command "winget") {
        Show-Spinner "Installing Python via winget..." {
            winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent 2>&1 | Out-Null
        }
    } else {
        $pyUrl = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
        $pyInstaller = Join-Path $env:TEMP "python-installer.exe"
        Show-Spinner "Downloading Python..." {
            Invoke-WebRequest -Uri $using:pyUrl -OutFile $using:pyInstaller -UseBasicParsing
        }
        Show-Spinner "Installing Python..." {
            Start-Process -FilePath $using:pyInstaller -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0" -Wait
        }
        Remove-Item $pyInstaller -ErrorAction SilentlyContinue
    }

    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

    foreach ($cmd in @("python", "python3", "py")) {
        if (Test-Command $cmd) {
            try {
                $verOutput = & $cmd --version 2>&1
                if ($verOutput -match "(\d+\.\d+\.\d+)") {
                    $script:PYTHON_CMD = $cmd
                    Write-Ok "Python installed: $($Matches[1])"
                    return
                }
            } catch { }
        }
    }

    Write-Fail "Python installation failed. Install manually: https://www.python.org/downloads/"
}

# ══════════════════════════════════════════════════════════════════
# Step 2: Ollama
# ══════════════════════════════════════════════════════════════════
function Install-Ollama {
    Write-Section "Ollama"

    if (Test-Command "ollama") {
        Write-Ok "Ollama installed"
        return
    }

    Write-Warn "Ollama not found. Installing..."

    if (Test-Command "winget") {
        Show-Spinner "Installing Ollama via winget..." {
            winget install Ollama.Ollama --accept-package-agreements --accept-source-agreements --silent 2>&1 | Out-Null
        }
    } else {
        $ollamaUrl = "https://ollama.ai/download/OllamaSetup.exe"
        $ollamaInstaller = Join-Path $env:TEMP "OllamaSetup.exe"
        Show-Spinner "Downloading Ollama..." {
            Invoke-WebRequest -Uri $using:ollamaUrl -OutFile $using:ollamaInstaller -UseBasicParsing
        }
        Show-Spinner "Installing Ollama..." {
            Start-Process -FilePath $using:ollamaInstaller -ArgumentList "/SILENT" -Wait
        }
        Remove-Item $ollamaInstaller -ErrorAction SilentlyContinue
    }

    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

    if (-not (Test-Command "ollama")) {
        Write-Fail "Ollama installation failed. Install manually: https://ollama.ai/download"
    }

    Write-Ok "Ollama installed"
}

# ══════════════════════════════════════════════════════════════════
# Step 3: Start Ollama & pull models
# ══════════════════════════════════════════════════════════════════
function Setup-Models {
    Write-Section "AI Models"

    $running = $false
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) { $running = $true }
    } catch { }

    if (-not $running) {
        Show-Spinner "Starting Ollama server..." {
            Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
            Start-Sleep -Seconds 5
        }

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

        Write-Ok "Ollama server started"
    } else {
        Write-Ok "Ollama server running"
    }

    $installed = ""
    try { $installed = & ollama list 2>&1 | Out-String } catch { }

    foreach ($model in $MODELS) {
        if ($installed -match [regex]::Escape($model)) {
            Write-Ok "$model"
        } else {
            Show-Spinner "Downloading $model... (this may take 10-15 min)" {
                & ollama pull $using:model 2>&1 | Out-Null
            }
            Write-Ok "$model downloaded"
        }
    }
}

# ══════════════════════════════════════════════════════════════════
# Step 4: JCode
# ══════════════════════════════════════════════════════════════════
function Install-JCode {
    Write-Section "JCode"

    if (Test-Path $JCODE_HOME) {
        if (Test-Path (Join-Path $JCODE_HOME ".git")) {
            Show-Spinner "Updating JCode..." {
                Push-Location $using:JCODE_HOME
                try { & git pull --ff-only 2>&1 | Out-Null } catch { }
                Pop-Location
            }
            Write-Ok "Updated to latest"
        } else {
            Write-Ok "JCode directory exists"
        }
    } else {
        if (Test-Command "git") {
            Show-Spinner "Downloading JCode..." {
                & git clone $using:JCODE_REPO $using:JCODE_HOME 2>&1 | Out-Null
            }
        } else {
            $zipUrl = $JCODE_REPO -replace "\.git$", "/archive/refs/heads/main.zip"
            $tmpZip = Join-Path $env:TEMP "jcode_download.zip"
            Show-Spinner "Downloading JCode..." {
                Invoke-WebRequest -Uri $using:zipUrl -OutFile $using:tmpZip -UseBasicParsing
                Expand-Archive -Path $using:tmpZip -DestinationPath $env:TEMP -Force
                Move-Item (Join-Path $env:TEMP "JcodeAgent-main") $using:JCODE_HOME
                Remove-Item $using:tmpZip -ErrorAction SilentlyContinue
            }
        }
        Write-Ok "Downloaded to $JCODE_HOME"
    }

    Push-Location $JCODE_HOME

    $venvPath = Join-Path $JCODE_HOME ".venv"
    if (-not (Test-Path $venvPath)) {
        Show-Spinner "Creating virtual environment..." {
            if ($using:PYTHON_CMD -eq "py -3") {
                & py -3 -m venv .venv
            } else {
                & $using:PYTHON_CMD -m venv .venv
            }
        }
        Write-Ok "Virtual environment created"
    } else {
        Write-Ok "Virtual environment exists"
    }

    $pipCmd = Join-Path $venvPath "Scripts" "pip.exe"
    Show-Spinner "Installing dependencies..." {
        & $using:pipCmd install --upgrade pip -q 2>&1 | Out-Null
        & $using:pipCmd install -e . -q 2>&1 | Out-Null
    }
    Write-Ok "JCode installed"

    Pop-Location
}

# ══════════════════════════════════════════════════════════════════
# Step 5: Add to PATH
# ══════════════════════════════════════════════════════════════════
function Setup-Path {
    Write-Section "PATH"

    $venvBin = Join-Path $JCODE_HOME ".venv" "Scripts"
    $currentPath = [System.Environment]::GetEnvironmentVariable("Path", "User")

    if ($currentPath -like "*$venvBin*") {
        Write-Ok "PATH configured"
    } else {
        [System.Environment]::SetEnvironmentVariable("Path", "$venvBin;$currentPath", "User")
        $env:Path = "$venvBin;$env:Path"
        Write-Ok "Added to PATH"
    }
}

# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════
function Show-Summary {
    $pyVer = ""
    try {
        if ($PYTHON_CMD -eq "py -3") {
            $pyVer = & py -3 --version 2>&1
        } else {
            $pyVer = & $PYTHON_CMD --version 2>&1
        }
        if ($pyVer -match "(\d+\.\d+\.\d+)") { $pyVer = $Matches[1] }
    } catch { $pyVer = "installed" }

    Write-Host ""
    Write-Host "  -------------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Installation complete." -ForegroundColor Green
    Write-Host ""
    Write-Host "  Python    " -ForegroundColor DarkGray -NoNewline; Write-Host "$pyVer" -ForegroundColor Cyan
    Write-Host "  Ollama    " -ForegroundColor DarkGray -NoNewline; Write-Host "installed" -ForegroundColor Cyan
    Write-Host "  Models    " -ForegroundColor DarkGray -NoNewline; Write-Host "$($MODELS -join ', ')" -ForegroundColor Cyan
    Write-Host "  Location  " -ForegroundColor DarkGray -NoNewline; Write-Host "$JCODE_HOME" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  -------------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Get started:" -ForegroundColor White
    Write-Host ""
    Write-Host "    $ jcode" -ForegroundColor Cyan
    Write-Host "    jcode> build a todo list web app" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  If 'jcode' isn't found, open a new terminal." -ForegroundColor DarkGray
    Write-Host ""
}

# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════
Show-Banner
Write-Info "System: Windows $([System.Environment]::OSVersion.Version)"

Install-Python
Install-Ollama
Setup-Models
Install-JCode
Setup-Path
Show-Summary
