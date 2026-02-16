# 🚀 Quick Start Guide

## First Run Setup

When you run JCode for the first time:

```bash
jcode
```

You'll be greeted with a setup wizard:

```
⚙️  First-Time Setup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Welcome to JCode!

Let's set up your preferences.
You can change these anytime in ~/.jcode/settings.json

Where should JCode save generated projects? [~/jcode_projects]:
```

Choose a directory where all your generated projects will be saved (defaults to `~/jcode_projects`).

## Building Your First Project

```
jcode> build a REST API with FastAPI for a todo list with SQLite
```

JCode will:
1. **Analyze complexity** — detects it's a medium complexity project
2. **Plan the structure** — creates file/folder layout
3. **Ask for confirmation** — you can review before generating
4. **Generate all files** — writes code with proper dependencies
5. **Validate & fix** — runs checks and auto-corrects errors
6. **Auto-save** — stores project metadata for later

## Project Complexity Detection

JCode automatically detects project complexity and adjusts context windows:

| Complexity | File Count | Features | Context Size |
|------------|-----------|----------|--------------|
| **Simple** | 1-3 files | Basic logic | 1.0x (16k) |
| **Medium** | 4-10 files | Moderate features | 1.5x (24k) |
| **Complex** | 11-20 files | DB, API, Auth | 2.0x (32k) |
| **Large** | 20+ files | Full application | 2.5x (40k) |

The system considers:
- Number of files and tasks
- Tech stack (database, API, auth, tests)
- Feature complexity

## Resuming Projects

List all your saved projects:
```
jcode> projects
```

Resume working on one:
```
jcode> resume my_project_name
```

JCode will load the full session including:
- All generated files
- Conversation history
- Current state and errors
- Output directory

## Iterating on a Project

After generating a project, you can continue working on it:

```
jcode> add a login page with email/password authentication
```

JCode will:
- Understand the existing project context
- Generate/modify only the necessary files
- Maintain consistency with existing code
- Auto-save progress

## Useful Commands

| Command | Description |
|---------|-------------|
| `plan` | Show current project structure |
| `files` | List all generated files |
| `tree` | Visual directory tree |
| `projects` | List all saved projects |
| `resume <name>` | Continue a project |
| `settings` | View configuration |
| `clear` | Start fresh (auto-saves current) |

## Settings Location

All JCode data is stored in `~/.jcode/`:

```
~/.jcode/
├── settings.json           # User preferences
└── projects/              # Project metadata
    ├── my_api.json
    ├── todo_app.json
    └── ...
```

Each generated project also has a hidden session file:
```
~/jcode_projects/my_project/.jcode_session.json
```

## Tips

### 1. Be Specific in Prompts
❌ "build a website"  
✅ "build a React portfolio website with a projects page, about page, and contact form using TailwindCSS"

### 2. Iterate Incrementally
After generating the base:
```
jcode> add unit tests for all API endpoints
jcode> add error handling and logging
jcode> add a README with setup instructions
```

### 3. Check Before Confirming
Always review the plan before saying "yes" to generation:
- File structure makes sense?
- Tech stack is correct?
- Tasks are in the right order?

### 4. Use Project Complexity Wisely
For large projects, break them into phases:
```
jcode> build the backend API first (Phase 1)
# (after completion)
jcode> clear
jcode> now build the frontend dashboard (Phase 2)
```

## Troubleshooting

### "Read-only file system" error
✅ **Fixed!** Now validates and expands paths properly.

Use full paths or `~/directory` notation:
- ✓ `/Users/you/projects/myapp`
- ✓ `~/Desktop/myapp`
- ✗ `/myapp` (root filesystem)

### Project not resuming
Check if the session file exists:
```bash
ls ~/jcode_projects/my_project/.jcode_session.json
```

If missing, JCode can only show metadata. The files are still there, but conversation history is lost.

### Models not found
On first run, JCode auto-downloads models. If interrupted:
```bash
ollama pull deepseek-r1:14b
ollama pull qwen2.5-coder:14b
```

## Next Steps

- Experiment with different project types
- Try the `projects` command to see your portfolio
- Use `resume` to continue multi-session projects
- Check `~/.jcode/settings.json` to customize defaults
