'use client'

import Link from 'next/link'
import styles from './technical.module.css'

export default function TechnicalPage() {
  return (
    <div className="container">
      <h1>Technical <span className="accent">Documentation</span></h1>
      <p className={styles.heroSub}>Architecture, internals, and module reference for JCode.</p>

      <h2>Architecture Overview</h2>
      <p>JCode is a multi-agent system with 4 specialized AI roles that collaborate through a structured pipeline. Each role has its own prompt template, model assignment, and memory context.</p>

      <div className={styles.archDiagram}>{`User Input
    |
    v
+-------------------+
|     Planner       |  deepseek-r1:14b
|  (Architecture)   |  Breaks idea into DAG of tasks
+-------------------+
    |
    v  Task Graph (dependency-ordered)
+-------------------+
|      Coder        |  qwen2.5-coder:14b
| (File Generation) |  Generates each file with structured context
+-------------------+
    |
    v  Generated code
+-------------------+     +-------------------+
|    Reviewer       | --> |      Coder        |
|  (Code Critic)    |     |   (Patch Mode)    |
+-------------------+     +-------------------+
    |                         |
    v  Approved code          v  Patched code
+-------------------+
|    Verifier       |  Static analysis: syntax, lint, types
| (executor.py)     |  + test execution (pytest / npm test)
+-------------------+
    |
    |--- PASS --> Next task
    |
    v  FAIL
+-------------------+     +-------------------+
|    Analyzer       | --> |   Fix Engine      |
| (Error Diagnosis) |     |  5 strategies     |
+-------------------+     |  8 attempts       |
                          +-------------------+`}</div>

      <h2>Model Configuration</h2>
      <table className={styles.table}>
        <thead>
          <tr><th>Role</th><th>Model</th><th>Context Size</th><th>Purpose</th></tr>
        </thead>
        <tbody>
          <tr><td>Planner</td><td><code>deepseek-r1:14b</code></td><td>16,384</td><td>Architecture design, task decomposition</td></tr>
          <tr><td>Coder</td><td><code>qwen2.5-coder:14b</code></td><td>16,384</td><td>Code generation, patching</td></tr>
          <tr><td>Reviewer</td><td><code>qwen2.5-coder:14b</code></td><td>16,384</td><td>Pre-execution code review</td></tr>
          <tr><td>Analyzer</td><td><code>deepseek-r1:14b</code></td><td>16,384</td><td>Error diagnosis, root cause analysis</td></tr>
        </tbody>
      </table>
      <p>Context sizes scale based on project complexity (detected automatically). For complex projects, context doubles to 32,768 tokens.</p>

      <h2>Module Reference</h2>

      <h3>jcode/cli.py &mdash; Command Line Interface</h3>
      <p>The main entry point. Implements a two-level REPL:</p>
      <ul>
        <li><strong>Home REPL</strong> (<code>_home_repl</code>) &mdash; Project selection, creation, update, uninstall</li>
        <li><strong>Project REPL</strong> (<code>_project_repl</code>) &mdash; Chat-driven interaction within a project</li>
      </ul>
      <p>Key functions:</p>
      <table className={styles.table}>
        <thead>
          <tr><th>Function</th><th>Description</th></tr>
        </thead>
        <tbody>
          <tr><td><code>main()</code></td><td>Entry point. Checks Ollama, permissions, starts home REPL</td></tr>
          <tr><td><code>_cmd_build()</code></td><td>Runs Planner + execute_plan pipeline</td></tr>
          <tr><td><code>_cmd_chat()</code></td><td>Natural language chat with project context</td></tr>
          <tr><td><code>_cmd_run()</code></td><td>Auto-detects and runs the project</td></tr>
          <tr><td><code>_apply_file_changes()</code></td><td>Parses ===FILE:=== markers from chat response</td></tr>
          <tr><td><code>_install_deps_if_needed()</code></td><td>Auto npm install / pip install before run</td></tr>
        </tbody>
      </table>

      <h3>jcode/iteration.py &mdash; Build Engine</h3>
      <p>The core DAG-based task execution engine. Processes tasks in dependency order with a multi-strategy fix loop.</p>
      <table className={styles.table}>
        <thead>
          <tr><th>Function</th><th>Description</th></tr>
        </thead>
        <tbody>
          <tr><td><code>execute_plan()</code></td><td>Main orchestrator. Resolves DAG, iterates until all pass or limits hit</td></tr>
          <tr><td><code>_process_task()</code></td><td>Generate &rarr; Review &rarr; Verify single task</td></tr>
          <tr><td><code>_review_and_patch()</code></td><td>2-round review loop with patching</td></tr>
          <tr><td><code>_fix_loop()</code></td><td>8-attempt fix with 5 strategies</td></tr>
          <tr><td><code>_escalate()</code></td><td>User prompt: retry / guided-fix / skip / pause</td></tr>
        </tbody>
      </table>

      <h4>Fix Strategies (in order)</h4>
      <table className={styles.table}>
        <thead>
          <tr><th>Strategy</th><th>Attempts</th><th>Approach</th></tr>
        </thead>
        <tbody>
          <tr><td>A: Targeted Patch</td><td>1&ndash;3</td><td>Analyze error &rarr; patch the specific issue</td></tr>
          <tr><td>B: Deep Analysis</td><td>4&ndash;5</td><td>Cross-file dependency context, reverse dependency checking, dependency patching</td></tr>
          <tr><td>C: Full Regeneration</td><td>6</td><td>Regenerate entire file from scratch with error history</td></tr>
          <tr><td>D: Simplify</td><td>7</td><td>Generate minimal/simplified version prioritizing correctness</td></tr>
          <tr><td>E: Research</td><td>8</td><td>Error pattern classification + web search for solutions</td></tr>
        </tbody>
      </table>

      <h3>jcode/config.py &mdash; Configuration</h3>
      <p>All constants, enums, and dataclasses:</p>
      <table className={styles.table}>
        <thead>
          <tr><th>Constant</th><th>Value</th><th>Description</th></tr>
        </thead>
        <tbody>
          <tr><td><code>MAX_TASK_FAILURES</code></td><td>8</td><td>Fix attempts per file before escalation</td></tr>
          <tr><td><code>MAX_ITERATIONS</code></td><td>15</td><td>Max full DAG passes</td></tr>
          <tr><td><code>BASE_PLANNER_CTX</code></td><td>16,384</td><td>Base context window for planner</td></tr>
          <tr><td><code>BASE_CODER_CTX</code></td><td>16,384</td><td>Base context window for coder</td></tr>
        </tbody>
      </table>
      <p>Key types:</p>
      <ul>
        <li><code>TaskStatus</code> &mdash; Enum: PENDING, IN_PROGRESS, DONE, FAILED, SKIPPED</li>
        <li><code>TaskNode</code> &mdash; Dataclass: task_id, description, file_path, deps, status, failures, output</li>
        <li><code>ProjectState</code> &mdash; Dataclass: name, description, root, language, framework, complexity</li>
      </ul>

      <h3>jcode/context.py &mdash; Structured Memory</h3>
      <p>The memory engine that gives each AI role precisely the context it needs.</p>
      <table className={styles.table}>
        <thead>
          <tr><th>Feature</th><th>Description</th></tr>
        </thead>
        <tbody>
          <tr><td>Task DAG</td><td>Ordered task list with dependency edges</td></tr>
          <tr><td>File Index</td><td>Map of file_path &rarr; content for all generated files</td></tr>
          <tr><td>Failure Log</td><td>History of errors and fix attempts per file</td></tr>
          <tr><td>Chat History</td><td>Per-project conversation log</td></tr>
          <tr><td>Serialization</td><td>Save/load to <code>~/.jcode/projects/{`{name}`}/</code></td></tr>
        </tbody>
      </table>
      <p>Context is trimmed per-role: the Coder gets the architecture summary + relevant dependency file contents, not the entire file index.</p>

      <h3>jcode/prompts.py &mdash; Prompt Templates</h3>
      <p>System prompts for each role:</p>
      <ul>
        <li><code>PLANNER_SYSTEM</code> / <code>PLANNER_REFINE</code> &mdash; Architecture planning with JSON DAG output</li>
        <li><code>CODER_SYSTEM</code> / <code>CODER_TASK</code> / <code>CODER_PATCH</code> &mdash; File generation and targeted patching</li>
        <li><code>REVIEWER_SYSTEM</code> / <code>REVIEWER_TASK</code> &mdash; Code review with JSON issue list</li>
        <li><code>ANALYZER_SYSTEM</code> / <code>ANALYZER_TASK</code> &mdash; Error diagnosis with structured fix strategy</li>
        <li><code>CHAT_SYSTEM</code> / <code>CHAT_CONTEXT</code> &mdash; Natural language chat with 3 modes (action / discussion / run-deploy)</li>
      </ul>

      <h3>jcode/executor.py &mdash; Execution &amp; Verification</h3>
      <table className={styles.table}>
        <thead>
          <tr><th>Function</th><th>Description</th></tr>
        </thead>
        <tbody>
          <tr><td><code>verify_file()</code></td><td>Routes to language-specific verifier</td></tr>
          <tr><td><code>_verify_python()</code></td><td>py_compile + optional pylint + pyflakes</td></tr>
          <tr><td><code>_verify_javascript()</code></td><td>node --check + optional eslint</td></tr>
          <tr><td><code>_verify_json()</code></td><td>json.loads validation</td></tr>
          <tr><td><code>run_command()</code></td><td>Execute shell command with timeout and capture</td></tr>
          <tr><td><code>install_dependencies()</code></td><td>Auto pip install / npm install</td></tr>
          <tr><td><code>run_tests()</code></td><td>Detect and run pytest / npm test</td></tr>
        </tbody>
      </table>

      <h3>jcode/ollama_client.py &mdash; Model Interface</h3>
      <p>Wrapper around the Ollama Python SDK. All model calls go through <code>call_model(role, messages, stream, num_ctx)</code>.</p>
      <ul>
        <li>Streaming support for real-time output</li>
        <li>Automatic context size based on role and project complexity</li>
        <li>Legacy wrappers: <code>call_planner()</code>, <code>call_coder()</code>, <code>call_reviewer()</code>, <code>call_analyzer()</code></li>
      </ul>

      <h3>jcode/web.py &mdash; Web Search</h3>
      <p>Web search and documentation fetching using DuckDuckGo (no API key required):</p>
      <ul>
        <li><code>web_search(query)</code> &mdash; Search DuckDuckGo, return top results</li>
        <li><code>fetch_page(url)</code> &mdash; Fetch and extract text content from a URL</li>
        <li><code>fetch_docs(query)</code> &mdash; Targeted documentation search</li>
        <li><code>search_and_summarize(query)</code> &mdash; Search + fetch + summarize results</li>
      </ul>

      <h3>jcode/settings.py &mdash; User Settings</h3>
      <p>Persistent settings stored in <code>~/.jcode/settings.json</code>:</p>
      <ul>
        <li><code>autonomous_access</code> &mdash; Permission to read/write project files</li>
        <li><code>internet_access</code> &mdash; Permission to search the web</li>
      </ul>

      <h2>Data Flow</h2>
      <h3>Build Pipeline</h3>
      <pre><code>{`User description
  |
  v
Planner.plan() --> TaskNode[] (DAG)
  |
  v
for each task in topological order:
  |
  +-- Coder.generate_file(task, context)
  |     |
  |     v
  +-- Reviewer.review_file(code)
  |     |-- issues? --> Coder.patch_file(code, issues)
  |     |               |-- re-review (max 2 rounds)
  |     |
  |     v
  +-- Executor.verify_file(path)
  |     |-- pass? --> mark DONE, continue
  |     |
  |     v  fail
  +-- Fix Loop (8 attempts, 5 strategies)
        |-- Analyzer.analyze_error(error)
        |-- Strategy A/B/C/D/E --> patch/regen/research
        |-- Executor.verify_file(path)
        |-- pass? --> break
        |-- all failed? --> escalate to user`}</code></pre>

      <h3>Chat Pipeline</h3>
      <pre><code>{`User message
  |
  v
Build context: architecture + file index + chat history
  |
  v
call_model("coder", [system + context + message])
  |
  v
Response contains ===FILE:path=== markers?
  |-- yes --> parse and apply file changes
  |-- no  --> display as text answer`}</code></pre>

      <h2>Project Structure</h2>
      <pre><code>{`JcodeAgent/
  jcode/
    __init__.py       Package init, version
    cli.py            Main CLI entry point (two-level REPL)
    config.py         Constants, enums, dataclasses
    context.py        Structured memory engine
    iteration.py      DAG build engine + fix loop
    prompts.py        All prompt templates
    coder.py          File generation + patching
    reviewer.py       Code review
    analyzer.py       Error diagnosis
    executor.py       Verification + test execution
    ollama_client.py  Ollama API wrapper
    web.py            Web search + doc fetching
    settings.py       User settings persistence
  docs/
    index.html        Landing page
    beginner-guide.html  This guide
    technical.html    You are here
  install.sh          Unix installer
  install.ps1         Windows installer
  pyproject.toml      Package metadata
  README.md           Repository readme`}</code></pre>

      <h2>Extending JCode</h2>
      <h3>Adding a new language verifier</h3>
      <p>Edit <code>executor.py</code> and add a new <code>_verify_*</code> function. Register it in <code>verify_file()</code>'s extension-to-verifier map.</p>

      <h3>Changing models</h3>
      <p>Edit <code>config.py</code>. Set <code>PLANNER_MODEL</code> and <code>CODER_MODEL</code> to any Ollama-compatible model.</p>

      <h3>Adding a new fix strategy</h3>
      <p>In <code>iteration.py</code>, add a new strategy block in <code>_fix_loop()</code>. Assign it an attempt number range and implement the fix logic.</p>
    </div>
  )
}
