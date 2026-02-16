# Complete Beginner's Guide to JCode

> **Never coded before? No problem!** This guide will walk you through everything you need to get JCode running on your computer, step by step.

## What is JCode?

JCode is like having a team of AI programmers on your computer. You describe what you want to build in plain English, and it creates the code for you — completely free, completely private, running on your own machine.

**No coding knowledge required. No cloud services. No subscriptions.**

---

## ⚡ One-Command Install (Recommended)

The fastest way to get started — **one line installs everything**:

### Mac / Linux

Open Terminal and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/ShakenTheCoder/JcodeAgent/main/install.sh | bash
```

### Windows

Open PowerShell (right-click Start → "Windows PowerShell") and paste:

```powershell
iwr -useb https://raw.githubusercontent.com/ShakenTheCoder/JcodeAgent/main/install.ps1 | iex
```

**That's it!** The installer automatically:
- ✅ Installs Python (if you don't have it)
- ✅ Installs Ollama (if you don't have it)
- ✅ Downloads the AI models (if you don't have them)
- ✅ Downloads JCode
- ✅ Sets everything up and adds `jcode` to your PATH

After it finishes, just type `jcode` and start building!

> **Want to understand what's happening?** The manual steps below explain everything the installer does automatically.

---

## Manual Install (Step by Step)

If you prefer to install things yourself, or the one-liner didn't work, follow these steps:

---

## Step 1: Install Python (The Language JCode Speaks)

### For Mac Users

1. **Open Terminal** (it's an app on your Mac):
   - Press `Command + Space`
   - Type "Terminal"
   - Press Enter

2. **Install Homebrew** (a tool that makes installing things easier):
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```
   - Paste that line into Terminal and press Enter
   - It will ask for your password (the same one you use to unlock your Mac)
   - Wait 5-10 minutes for it to finish

3. **Install Python**:
   ```bash
   brew install python@3.12
   ```
   - Wait for it to finish (2-3 minutes)

4. **Verify Python is installed**:
   ```bash
   python3 --version
   ```
   - You should see something like `Python 3.12.x`

### For Windows Users

1. **Download Python**:
   - Go to https://www.python.org/downloads/
   - Click the big yellow button "Download Python 3.12.x"
   - Run the downloaded file

2. **During installation**:
   - ✅ **IMPORTANT**: Check the box that says "Add Python to PATH"
   - Click "Install Now"
   - Wait for it to finish

3. **Verify Python is installed**:
   - Press `Windows Key + R`
   - Type `cmd` and press Enter
   - Type: `python --version`
   - You should see `Python 3.12.x`

### For Linux Users

```bash
sudo apt update
sudo apt install python3.12 python3.12-venv python3-pip
```

---

## Step 2: Install Ollama (The AI Brain)

Ollama is the free, local AI that powers JCode. It runs on your computer — no internet needed after setup.

### For Mac Users

1. Go to https://ollama.ai/download
2. Click "Download for macOS"
3. Open the downloaded file and drag Ollama to your Applications folder
4. Open Ollama from Applications (it will add an icon to your menu bar)

### For Windows Users

1. Go to https://ollama.ai/download
2. Click "Download for Windows"
3. Run the installer
4. Ollama will start automatically (look for the llama icon in your system tray)

### For Linux Users

```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

---

## Step 3: Download the AI Models

These are the "brains" JCode uses. You only need to do this once.

### Open Terminal (Mac/Linux) or Command Prompt (Windows)

Type these two commands:

```bash
ollama pull deepseek-r1:14b
```

Wait for it to finish (10-15 minutes, downloads ~8 GB).

Then:

```bash
ollama pull qwen2.5-coder:14b
```

Wait for this one too (10-15 minutes, downloads ~8 GB).

**What's happening?** You're downloading two specialized AI models:
- **deepseek-r1** — the "architect" that plans your project
- **qwen2.5-coder** — the "programmer" that writes the code

---

## Step 4: Download JCode

### Option A: Download as ZIP (Easiest)

1. Go to wherever JCode is hosted (e.g., GitHub)
2. Click the green "Code" button
3. Click "Download ZIP"
4. Unzip the file (double-click it)
5. Move the `JcodeAgent` folder to your Desktop

### Option B: Using Git (If You Have It)

```bash
cd ~/Desktop
git clone <jcode-repository-url>
cd JcodeAgent
```

---

## Step 5: Install JCode

### Open Terminal/Command Prompt and Navigate to JCode

**Mac/Linux:**
```bash
cd ~/Desktop/JcodeAgent
```

**Windows:**
```bash
cd %USERPROFILE%\Desktop\JcodeAgent
```

### Install JCode

```bash
pip3 install -e .
```

**Windows users:** Use `pip install -e .` (without the 3)

This command tells Python to install JCode on your computer.

---

## Step 6: Start Ollama Server

JCode needs Ollama to be running in the background.

### Mac/Linux

Open a **new Terminal window** and type:

```bash
ollama serve
```

Leave this window open while you use JCode.

### Windows

Ollama starts automatically. Just make sure you see the llama icon in your system tray (bottom-right corner).

---

## Step 7: Launch JCode!

### In your original Terminal/Command Prompt window:

```bash
jcode
```

You should see the JCode banner followed by an **interactive launcher**:

```
     ╦╔═╗╔═╗╔╦╗╔═╗
     ║║  ║ ║ ║║║╣
    ╚╝╚═╝╚═╝═╩╝╚═╝  v0.2.0
  ─────────────────────────
  Local AI Coding Agent
  🧠 Planner  · 💻 Coder
  🔍 Reviewer · 🔬 Analyzer

  What would you like to do?

    1 · 🆕  Start a new project
    2 · 📂  Continue a previous project
    3 · 📥  Import an existing project
    4 · ⏭️   Skip (go to prompt)
```

Just type the number of your choice and press Enter!

**Congratulations! JCode is running!** 🎉

---

## Step 8: Create Your First Project

### Option 1: Use the Interactive Launcher (Easiest)

When JCode starts, choose **1 · Start a new project**.

It will ask you:
1. **Where to save the project** — just press Enter for the default location, or type a path
2. **What to build** — describe your idea in plain English
3. **Clone from GitHub?** — if you have an existing repo, paste the URL; otherwise just say no

### Option 2: From a GitHub Repository

Choose **3 · Import an existing project** from the launcher. You can:
- Paste a **GitHub URL** (e.g. `https://github.com/user/repo`) and JCode will clone it
- Or type a **local path** to a project folder on your computer

### Option 3: At the `jcode>` Prompt

If you chose option 4 (skip) at the launcher, type at the prompt:

```
build a simple todo list web app with a nice interface
```

### Example: Build a Todo List Web App

Describe your idea and watch the magic happen:

1. 🧠 **Planner** figures out what files you need
2. 💻 **Coder** writes the code
3. 🔍 **Reviewer** checks for bugs
4. ✅ **Verifier** tests the code
5. 🔬 **Analyzer** fixes any issues

After a few minutes, you'll have a complete project in a new folder!

### What If Something Goes Wrong?

If a task fails 3 times, JCode won't just crash — it will ask you what to do:

- **🔄 Re-generate** — try from scratch with a fresh approach
- **📐 Simplify** — create a minimal version with TODO comments for the hard parts
- **⏭️ Skip** — move on to the next task
- **⏸️ Pause** — pause and let you inspect the error, then provide guidance

### More Example Prompts to Try

```
build a simple calculator app with a GUI
```

```
build a REST API for managing a book library
```

```
build a weather app that shows the forecast
```

```
build a personal budget tracker
```

---

## Understanding JCode Commands

Once JCode is running, you can use these commands:

| Command | What It Does |
|---------|-------------|
| `build <description>` | Create a new project from your description |
| `plan` | Show what JCode is building |
| `tree` | See all the files JCode created |
| `projects` | List all your past projects |
| `resume` | Continue working on your last project |
| `update` | Check for and install JCode updates |
| `help` | Show all commands |
| `quit` | Exit JCode |

**Tip:** You don't have to memorize these — the interactive launcher handles the most common actions for you automatically!

---

## Troubleshooting

### "Command not found: jcode"

**Fix:**
```bash
pip3 install -e .
```

Make sure you're in the JcodeAgent folder first.

---

### "Ollama is not running"

**Mac/Linux:** Open a new Terminal and run:
```bash
ollama serve
```

**Windows:** Make sure you see the Ollama icon in your system tray. If not, search for "Ollama" in Start menu and launch it.

---

### "Model not found: deepseek-r1:14b"

You need to download the models:
```bash
ollama pull deepseek-r1:14b
ollama pull qwen2.5-coder:14b
```

---

### "Error: Read-only file system"

JCode tried to create files in a protected location. When it asks where to save your project, choose a different folder like:
- `~/Desktop/my_projects`
- `~/Documents/jcode_projects`

---

### Code Has Errors

JCode will automatically try to fix errors up to 3 times. If it still doesn't work, JCode will offer you 4 choices:

1. **Re-generate** — try a completely fresh approach
2. **Simplify** — create a minimal version and mark the tricky parts with TODOs
3. **Skip** — skip that file and continue with the rest
4. **Pause** — let you look at the error and give JCode hints

You can also:
- Type `resume` to continue from where it left off
- Try a simpler prompt first
- Check that both AI models are fully downloaded

---

## What Happens Behind the Scenes?

When you type `build <something>`:

```
Your idea
    ↓
🧠 Planner creates a blueprint
    ↓
💻 Coder writes the files one by one
    ↓
🔍 Reviewer checks each file for bugs
    ↓
✅ Verifier runs tests
    ↓
🔬 Analyzer fixes any errors
    ↓
📁 Complete working project!
```

All of this happens **on your computer**. No data is sent to the cloud. No subscriptions. Completely free and private.

---

## Where Are My Projects Saved?

By default, JCode saves projects to:
- **Mac/Linux:** `~/jcode_projects/`
- **Windows:** `C:\Users\YourName\jcode_projects\`

You can change this with the `settings` command.

---

## Tips for Better Results

### ✅ Good Prompts

```
build a simple todo list web app with HTML, CSS, and JavaScript
```

```
build a REST API with Python FastAPI for managing blog posts
```

```
build a calculator app with a graphical interface using Python tkinter
```

### ❌ Vague Prompts

```
build something cool
```

```
make an app
```

**Tip:** Be specific about what you want. Mention the technology if you know it, or describe the features clearly.

---

## Next Steps

1. **Experiment!** Try building simple projects to get comfortable
2. **Read the files** JCode creates — you'll learn by seeing the code
3. **Modify projects** — JCode creates a starting point, you can edit the files yourself
4. **Try `resume`** — if a project didn't work perfectly, resume and try again

---

## Still Need Help?

- Type `help` inside JCode for a command reference
- Check `README.md` for technical details
- Check `FEATURES.md` for a full feature list

---

## Frequently Asked Questions

**Q: Do I need internet?**  
A: Only for the initial setup (downloading Python, Ollama, and the AI models). After that, JCode works 100% offline.

**Q: Is it really free?**  
A: Yes! Everything is open-source and runs locally on your machine.

**Q: How much disk space do I need?**  
A: About 20 GB for the AI models, plus space for your projects.

**Q: Can I use this for commercial projects?**  
A: Yes, JCode is MIT licensed. The code it generates is yours.

**Q: Will this work on my old computer?**  
A: You need at least 16 GB of RAM. The AI models are quite large.

**Q: Can I use different AI models?**  
A: Yes, but you'll need to edit `jcode/config.py` to change the model names.

**Q: What if the code doesn't work?**  
A: JCode will automatically try to fix errors. You can also type `resume` to retry.

---

**Ready to build? Type `jcode` and let's go!** 🚀
