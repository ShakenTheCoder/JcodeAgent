'use client'

import Link from 'next/link'
import styles from './guide.module.css'

export default function GuidePage() {
  return (
    <div className="container">
      <h1>Beginner <span className="accent">Guide</span></h1>
      <p className={styles.heroSub}>Everything you need to get started with JCode &mdash; from installation to your first project.</p>

      <h2>Prerequisites</h2>
      <p>Before installing JCode, make sure you have:</p>
      <ul>
        <li><strong>Python 3.10+</strong> &mdash; Check with <code>python3 --version</code></li>
        <li><strong>Ollama</strong> &mdash; Install from <a href="https://ollama.ai" target="_blank" rel="noopener noreferrer">ollama.ai</a></li>
        <li><strong>8GB+ RAM</strong> &mdash; For running 14B parameter models locally</li>
        <li><strong>20GB+ disk space</strong> &mdash; For the two AI models (~7GB each)</li>
      </ul>

      <div className={styles.callout}>
        <strong>Note:</strong> JCode runs entirely on your machine. No API keys, no cloud accounts, and no internet connection required after installation.
      </div>

      <h2>Installation</h2>
      <h3>One-command install (recommended)</h3>
      <p>Mac / Linux:</p>
      <pre><code>curl -fsSL https://getjcode.vercel.app/install.sh | bash</code></pre>
      <p>Windows (PowerShell):</p>
      <pre><code>iwr -useb https://getjcode.vercel.app/install.ps1 | iex</code></pre>
      <p>The installer will:</p>
      <ol>
        <li>Clone the JCode repository</li>
        <li>Create a Python virtual environment</li>
        <li>Install all dependencies</li>
        <li>Pull the required AI models (deepseek-r1:14b + qwen2.5-coder:14b)</li>
        <li>Add <code>jcode</code> to your PATH</li>
      </ol>

      <h3>Manual install</h3>
      <pre><code>{`git clone https://github.com/ShakenTheCoder/JcodeAgent.git
cd JcodeAgent
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
ollama pull deepseek-r1:14b
ollama pull qwen2.5-coder:14b`}</code></pre>

      <h2>First Launch</h2>
      <p>Start JCode by typing:</p>
      <pre><code>jcode</code></pre>
      <p>On your first run, JCode will ask for two permissions:</p>
      <ul>
        <li><strong>Autonomous file access</strong> &mdash; Lets JCode read and write files in your project directories</li>
        <li><strong>Internet access</strong> &mdash; Lets JCode search the web for documentation and solutions</li>
      </ul>
      <p>Both are optional. You only get asked once &mdash; your choices are saved permanently.</p>

      <h2>Your First Project</h2>
      <p>Here is a step-by-step walkthrough of building your first project:</p>

      <div className={styles.stepGrid}>
        <div className={styles.stepNum}>01</div>
        <div>
          <p><strong>Start JCode and type your project idea:</strong></p>
          <pre><code>jcode&gt; build a todo app with Flask and SQLite</code></pre>
        </div>

        <div className={styles.stepNum}>02</div>
        <div>
          <p><strong>JCode plans the architecture.</strong> The Planner breaks down your idea into a dependency-ordered task graph. You will see something like:</p>
          <pre><code>{`12:04:01  PHASE 1   Planning project architecture
12:04:12  PLAN      5 task(s) created`}</code></pre>
        </div>

        <div className={styles.stepNum}>03</div>
        <div>
          <p><strong>JCode generates and reviews each file.</strong> Every file goes through: generate &rarr; review &rarr; verify. If anything fails, the fix engine kicks in automatically.</p>
          <pre><code>{`12:04:15  GENERATE  app.py
12:04:22  REVIEW    Approved
12:04:23  VERIFY    passed`}</code></pre>
        </div>

        <div className={styles.stepNum}>04</div>
        <div>
          <p><strong>Build complete.</strong> Once all files pass, you drop into the project REPL:</p>
          <pre><code>{`12:05:10  DONE      Build complete -- all files verified

todo-app>`}</code></pre>
        </div>

        <div className={styles.stepNum}>05</div>
        <div>
          <p><strong>Chat naturally to iterate.</strong> Add features, fix bugs, or ask questions:</p>
          <pre><code>{`todo-app> add user authentication with password hashing
todo-app> why did you use Flask-Login instead of JWT?
todo-app> make the UI look more modern`}</code></pre>
        </div>

        <div className={styles.stepNum}>06</div>
        <div>
          <p><strong>Run your project.</strong> Type <code>run</code> and JCode auto-detects the right command:</p>
          <pre><code>{`todo-app> run
Running: python app.py
 * Running on http://127.0.0.1:5000`}</code></pre>
        </div>
      </div>

      <h2>Chat Mode</h2>
      <p>Once inside a project, everything is natural language. JCode detects your intent automatically:</p>
      <ul>
        <li><strong>Action requests</strong> &mdash; "add a search bar", "fix the login bug", "refactor the database layer" &rarr; JCode modifies files</li>
        <li><strong>Questions</strong> &mdash; "how does the routing work?", "explain the auth flow" &rarr; JCode answers without changing files</li>
        <li><strong>Run/Deploy</strong> &mdash; "how do I run this?", "how do I deploy to Vercel?" &rarr; JCode gives step-by-step commands</li>
      </ul>

      <h2>Reserved Commands</h2>
      <p>These are the only special commands. Everything else is natural language:</p>
      <pre><code>{`run       Run the project (auto-detects framework)
plan      Show the current task plan
files     List all project files
tree      Show directory tree
rebuild   Re-run the full build pipeline
back      Return to home screen
clear     Clear the terminal
help      Show help`}</code></pre>

      <h2>Tips &amp; Best Practices</h2>
      <ul>
        <li><strong>Be specific.</strong> "Build a REST API with FastAPI, PostgreSQL, JWT auth, and Docker" gives better results than "build an API".</li>
        <li><strong>Iterate in small steps.</strong> After the initial build, add features one at a time rather than asking for everything at once.</li>
        <li><strong>Use <code>run</code> often.</strong> Test after every change. JCode auto-installs dependencies when needed.</li>
        <li><strong>Ask questions.</strong> If something is unclear, ask JCode to explain. It has full context of your project.</li>
        <li><strong>Trust the fix engine.</strong> If a file fails verification, JCode has 8 attempts with 5 different strategies. Let it work.</li>
        <li><strong>Save your progress.</strong> Sessions auto-save. You can close JCode and resume later &mdash; your project and chat history are preserved.</li>
      </ul>

      <h2>Troubleshooting</h2>
      <h3>Ollama not found</h3>
      <p>Make sure Ollama is running: <code>ollama serve</code>. If not installed, get it from <a href="https://ollama.ai" target="_blank" rel="noopener noreferrer">ollama.ai</a>.</p>

      <h3>Models not downloaded</h3>
      <p>Pull both models manually:</p>
      <pre><code>{`ollama pull deepseek-r1:14b
ollama pull qwen2.5-coder:14b`}</code></pre>

      <h3>Out of memory</h3>
      <p>14B models need ~8GB RAM. Close other applications, or use smaller models by editing <code>jcode/config.py</code>:</p>
      <pre><code>{`PLANNER_MODEL = "deepseek-r1:7b"
CODER_MODEL = "qwen2.5-coder:7b"`}</code></pre>

      <h3>Permission denied</h3>
      <p>Reset permissions by deleting <code>~/.jcode/settings.json</code>. JCode will ask again on next launch.</p>

      <h3>Build keeps failing</h3>
      <p>If the 8-attempt fix engine cannot resolve an issue, JCode will pause and ask for guidance. You can:</p>
      <ul>
        <li>Provide a hint about what is wrong</li>
        <li>Skip the problematic file</li>
        <li>Retry with a fresh attempt</li>
      </ul>
    </div>
  )
}
