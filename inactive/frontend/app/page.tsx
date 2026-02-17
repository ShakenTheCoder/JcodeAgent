'use client'

import { useState } from 'react'
import styles from './page.module.css'

export default function Home() {
  const [activeTab, setActiveTab] = useState<'mac' | 'win'>('mac')
  const [copied, setCopied] = useState(false)

  const copyInstall = (os: 'mac' | 'win') => {
    const commands = {
      mac: 'curl -fsSL https://getjcode.vercel.app/install.sh | bash',
      win: 'iwr -useb https://getjcode.vercel.app/install.ps1 | iex'
    }
    navigator.clipboard.writeText(commands[os]).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <>
      <div className="container">
        {/* Hero */}
        <div className={styles.hero}>
          <pre className={styles.heroAscii}>{`     █▀ ██████▀ ██████▀ ██████▀ ███████▀
     █║█▀▄▄▄▄┘█▀▄▄▄█▀█▀▄▄█▀█▀▄▄▄▄┘
     █║█║     █║   █║█║  █║███▀
█   █║█║     █║   █║█║  █║█▄▄┘
▀███▀┘▀████▀▀████▀┘████▀┘███████▀
 ▀▄▄▄▄┘ ▀▄▄▄▄▄┘ ▀▄▄▄▄▄┘ ▀▄▄▄▄▄┘ ▀▄▄▄▄▄▄▄┘`}</pre>
          <h1>Your local, unlimited & private <span className="accent">software engineer</span></h1>
          <p>JCode plans, codes, reviews, and iterates — automatically — until your project works. 4 AI roles running entirely on your machine. No cloud. No API keys. No limits.</p>

          <div className={styles.installTabs}>
            <button 
              className={`${styles.installTab} ${activeTab === 'mac' ? styles.active : ''}`}
              onClick={() => setActiveTab('mac')}
            >
              Mac / Linux
            </button>
            <button 
              className={`${styles.installTab} ${activeTab === 'win' ? styles.active : ''}`}
              onClick={() => setActiveTab('win')}
            >
              Windows
            </button>
          </div>

          {activeTab === 'mac' && (
            <div className={styles.installPanel}>
              <div className={styles.installBox}>
                <div className="label">install</div>
                <code>curl -fsSL https://getjcode.vercel.app/install.sh | bash</code>
                <button className={styles.copyBtn} onClick={() => copyInstall('mac')}>
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          )}

          {activeTab === 'win' && (
            <div className={styles.installPanel}>
              <div className={styles.installBox}>
                <div className="label">install</div>
                <code>iwr -useb https://getjcode.vercel.app/install.ps1 | iex</code>
                <button className={styles.copyBtn} onClick={() => copyInstall('win')}>
                  {copied ? 'Copied!' : 'Copy'}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Terminal Demo */}
        <div className={styles.terminal}>
          <div className={styles.terminalBar}>
            <span className={`${styles.terminalDot} ${styles.r}`}></span>
            <span className={`${styles.terminalDot} ${styles.y}`}></span>
            <span className={`${styles.terminalDot} ${styles.g}`}></span>
            <span className={styles.terminalTitle}>jcode — zsh</span>
          </div>
          <div className={styles.terminalBody}>
            <div><span className={styles.prompt}>$</span> <span className={styles.cmd}>jcode</span></div>
            <div><span className={styles.cyan}>Ollama connected</span></div>
            <div>&nbsp;</div>
            <div><span className={styles.prompt}>jcode&gt;</span> <span className={styles.cmd}>build a REST API with FastAPI for a todo app</span></div>
            <div>&nbsp;</div>
            <div><span className={styles.dim}>12:04:01</span>  <span className={styles.cyan}>PHASE 1</span>   Planning project architecture</div>
            <div><span className={styles.dim}>12:04:12</span>  <span className={styles.cyan}>PLAN</span>      6 task(s) created</div>
            <div>&nbsp;</div>
            <div><span className={styles.dim}>12:04:12</span>  <span className={styles.cyan}>PHASE 2</span>   Building</div>
            <div><span className={styles.dim}>12:04:15</span>  <span className={styles.cyan}>GENERATE</span>  main.py</div>
            <div><span className={styles.dim}>12:04:22</span>  <span className={styles.cyan}>REVIEW</span>    <span className={styles.ok}>Approved</span></div>
            <div><span className={styles.dim}>12:04:23</span>  <span className={styles.cyan}>VERIFY</span>    <span className={styles.ok}>passed</span></div>
            <div><span className={styles.dim}>12:04:25</span>  <span className={styles.cyan}>GENERATE</span>  models.py</div>
            <div><span className={styles.dim}>12:04:31</span>  <span className={styles.cyan}>REVIEW</span>    2 issue(s) -- patching</div>
            <div><span className={styles.dim}>12:04:35</span>  <span className={styles.cyan}>VERIFY</span>    failed</div>
            <div><span className={styles.dim}>12:04:35</span>  <span className={styles.cyan}>FIX</span>       Attempt 1/8 <span className={styles.dim}>(targeted patch)</span></div>
            <div><span className={styles.dim}>12:04:40</span>  <span className={styles.cyan}>VERIFY</span>    <span className={styles.ok}>passed after 1 attempt(s)</span></div>
            <div>&nbsp;</div>
            <div><span className={styles.dim}>12:05:10</span>  <span className={styles.cyan}>DONE</span>      Build complete -- all files verified</div>
            <div>&nbsp;</div>
            <div><span className={styles.prompt}>todo-api&gt;</span> <span className={styles.cmd}>add user authentication with JWT</span></div>
            <div><span className={styles.dim}>12:05:18</span>  <span className={styles.cyan}>THINKING</span>  Processing your request...</div>
            <div><span className={styles.dim}>12:05:30</span>  <span className={styles.cyan}>APPLIED</span>   Updated 3 file(s)</div>
            <div>&nbsp;</div>
            <div><span className={styles.prompt}>todo-api&gt;</span> <span className={styles.typingCursor}></span></div>
          </div>
        </div>

        {/* How It Works */}
        <section id="how-it-works" className={styles.section}>
          <h2 className={styles.sectionH2}>How it <span className="accent">works</span></h2>
          <p className={styles.subtitle}>4 specialized AI agents cooperate through a 6-step build pipeline</p>
          <div className={styles.pipeline}>
            <div className={`${styles.holoCard} ${styles.pipeStep}`}>
              <div className={styles.stepNum}>Step 01</div>
              <h3 className={styles.pipeStepH3}>Planner</h3>
              <p className={styles.pipeStepP}>Creates a task DAG (directed acyclic graph) from your request. Defines dependencies so tasks run in correct order. Estimates complexity.</p>
            </div>
            <div className={`${styles.holoCard} ${styles.pipeStep}`}>
              <div className={styles.stepNum}>Step 02</div>
              <h3 className={styles.pipeStepH3}>Coder</h3>
              <p className={styles.pipeStepP}>Generates each file incrementally, with full context from previous files. Honors task dependencies. Applies best practices and conventions.</p>
            </div>
            <div className={`${styles.holoCard} ${styles.pipeStep}`}>
              <div className={styles.stepNum}>Step 03</div>
              <h3 className={styles.pipeStepH3}>Reviewer</h3>
              <p className={styles.pipeStepP}>Pre-execution code review with re-review loop. Catches bugs, missing imports, and logic errors. Issues get patched and re-reviewed.</p>
            </div>
            <div className={`${styles.holoCard} ${styles.pipeStep}`}>
              <div className={styles.stepNum}>Step 04</div>
              <h3 className={styles.pipeStepH3}>Verifier</h3>
              <p className={styles.pipeStepP}>Static analysis: syntax checks, linting, type validation, test execution. Every file is verified individually against real tooling.</p>
            </div>
            <div className={`${styles.holoCard} ${styles.pipeStep}`}>
              <div className={styles.stepNum}>Step 05</div>
              <h3 className={styles.pipeStepH3}>Analyzer</h3>
              <p className={styles.pipeStepP}>When something fails, the Analyzer diagnoses the root cause with cross-file context. Deep analysis considers dependency chains.</p>
            </div>
            <div className={`${styles.holoCard} ${styles.pipeStep}`}>
              <div className={styles.stepNum}>Step 06</div>
              <h3 className={styles.pipeStepH3}>Iterate</h3>
              <p className={styles.pipeStepP}>Up to 8 fix cycles with 5 strategies: targeted patch, deep analysis, full regen, simplify, and research-based repair. No giving up.</p>
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="features" className={styles.section}>
          <h2 className={styles.sectionH2}>Built <span className="accent">different</span></h2>
          <p className={styles.subtitle}>Engineering over model size. Architecture over brute force.</p>
          <div className={styles.features}>
            <div className={styles.holoCard}>
              <h3 className={styles.featureCardH3}>100% Local & Private</h3>
              <p className={styles.featureCardP}>Everything runs on your machine. Your code never leaves your computer. No API keys, no cloud, no subscriptions. Ever.</p>
            </div>
            <div className={styles.holoCard}>
              <h3 className={styles.featureCardH3}>Pure Chat-Driven</h3>
              <p className={styles.featureCardP}>No commands to memorize. Just type naturally: "fix the login bug", "add dark mode", "how does routing work?" JCode understands your intent.</p>
            </div>
            <div className={styles.holoCard}>
              <h3 className={styles.featureCardH3}>8-Attempt Fix Engine</h3>
              <p className={styles.featureCardP}>5 escalating strategies per file: targeted patch, deep cross-file analysis, full regeneration, simplification, and research-based repair.</p>
            </div>
            <div className={styles.holoCard}>
              <h3 className={styles.featureCardH3}>DAG Task Engine</h3>
              <p className={styles.featureCardP}>Tasks have dependencies. A file is not generated until its deps are verified. No more broken imports or circular references.</p>
            </div>
            <div className={styles.holoCard}>
              <h3 className={styles.featureCardH3}>Structured Memory</h3>
              <p className={styles.featureCardP}>Each role sees only what it needs — architecture summary, file index, failure log. Not raw context dumps. That is how 14B competes with 200B.</p>
            </div>
            <div className={styles.holoCard}>
              <h3 className={styles.featureCardH3}>Web Search & Docs</h3>
              <p className={styles.featureCardP}>Fetches documentation and searches the web to build better code. Reads APIs, frameworks docs, and guides. All with your permission.</p>
            </div>
            <div className={styles.holoCard}>
              <h3 className={styles.featureCardH3}>Auto Run & Deploy</h3>
              <p className={styles.featureCardP}>Detects your tech stack and knows exactly how to run it. Ask for deploy guidance and get copy-pasteable commands for Vercel, Railway, Docker, and more.</p>
            </div>
            <div className={styles.holoCard}>
              <h3 className={styles.featureCardH3}>Per-Project Chat</h3>
              <p className={styles.featureCardP}>Every project gets its own conversation history. Resume where you left off. Brainstorm features, request changes, or just ask questions.</p>
            </div>
            <div className={styles.holoCard}>
              <h3 className={styles.featureCardH3}>Save & Resume</h3>
              <p className={styles.featureCardP}>Sessions auto-save. Resume any project from where you left off. Switch between projects freely. Your progress is never lost.</p>
            </div>
          </div>
        </section>

        {/* Releases */}
        <section id="releases" className={styles.section}>
          <h2 className={styles.sectionH2}>Release <span className="accent">history</span></h2>
          <p className={styles.subtitle}>Latest updates and improvements.</p>
          <ul className={styles.releases}>
            <li className={styles.releaseItem}>
              <div className={styles.releaseHeader}>
                <span className={styles.releaseTag}>v0.5.3</span>
                <span className={styles.releaseDate}>Feb 2026</span>
                <span className={styles.releaseTitle}>Analytics & Version Command</span>
              </div>
              <div className={styles.releaseBody}>
                Install tracking and version display.
                <ul className={styles.releaseBodyUl}>
                  <li>Analytics-enabled install endpoints via Vercel serverless functions</li>
                  <li>Real-time install metrics: IP, timestamp, User-Agent, OS, counter</li>
                  <li>Dashboard at /api/stats showing install statistics</li>
                  <li>New <code className={styles.releaseBodyCode}>version</code> command in CLI to display current version</li>
                  <li>Install commands now use getjcode.vercel.app for tracking</li>
                </ul>
              </div>
            </li>
            <li className={styles.releaseItem}>
              <div className={styles.releaseHeader}>
                <span className={`${styles.releaseTag} ${styles.old}`}>v0.5.2</span>
                <span className={styles.releaseDate}>Feb 2026</span>
                <span className={styles.releaseTitle}>Agentic Auto-Fix</span>
              </div>
              <div className={styles.releaseBody}>
                Eliminated generic advice — JCode now acts as true agentic fixer.
                <ul className={styles.releaseBodyUl}>
                  <li>Auto-capture runtime errors and feed to agent (5-attempt loop)</li>
                  <li>Post-build Phase 3: runtime verification catches missing imports</li>
                  <li>CHAT_SYSTEM prompt rewritten: no generic tips, reads actual files, outputs fixes</li>
                  <li>Smart run command: detects project type and executes properly</li>
                </ul>
              </div>
            </li>
            <li className={styles.releaseItem}>
              <div className={styles.releaseHeader}>
                <span className={`${styles.releaseTag} ${styles.old}`}>v0.5.1</span>
                <span className={styles.releaseDate}>Feb 2026</span>
                <span className={styles.releaseTitle}>Resilient Fix Engine & Docs</span>
              </div>
              <div className={styles.releaseBody}>
                Major overhaul of the code review and fix pipeline.
                <ul className={styles.releaseBodyUl}>
                  <li>8-attempt fix loop with 5 escalating strategies</li>
                  <li>Cross-file dependency analysis for deeper root cause detection</li>
                  <li>Research-based error pattern matching (last resort strategy)</li>
                  <li>Agent knows how to run and deploy all major project types</li>
                  <li>Beginner guide and technical documentation</li>
                  <li>Landing page dark/light theme toggle</li>
                </ul>
              </div>
            </li>
          </ul>
        </section>
      </div>
    </>
  )
}
