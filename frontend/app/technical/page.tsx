import Link from 'next/link'

export default function TechnicalPage() {
  return (
    <div className="container mx-auto px-6 py-32 max-w-4xl">
      <Link href="/" className="text-accent hover:underline mb-8 inline-block">
        ← Back to Home
      </Link>

      <h1 className="text-5xl font-bold mb-4">
        Technical <span className="text-accent">Documentation</span>
      </h1>
      <p className="text-xl opacity-80 mb-12">
        Deep dive into JCode's architecture, algorithms, and design decisions.
      </p>

      {/* Architecture */}
      <section className="mb-16">
        <h2 className="text-3xl font-bold mb-6 pb-4 border-b border-white/20">
          Architecture Overview
        </h2>

        <div className="space-y-6">
          <div className="glass-effect rounded-lg p-6">
            <h3 className="text-2xl font-semibold mb-4 text-accent">4-Role Agent System</h3>
            <div className="space-y-4">
              <div>
                <p className="font-semibold mb-2">1. Planner (deepseek-r1:14b)</p>
                <p className="opacity-90">
                  Creates a structured task DAG, defines dependencies, estimates complexity
                </p>
              </div>
              <div>
                <p className="font-semibold mb-2">2. Coder (qwen2.5-coder:14b)</p>
                <p className="opacity-90">
                  Generates production-quality code, implements features, follows best practices
                </p>
              </div>
              <div>
                <p className="font-semibold mb-2">3. Reviewer (qwen2.5-coder:14b)</p>
                <p className="opacity-90">
                  Analyzes code for bugs, security issues, performance problems, suggests fixes
                </p>
              </div>
              <div>
                <p className="font-semibold mb-2">4. Analyzer (deepseek-r1:14b)</p>
                <p className="opacity-90">
                  Post-mortem analysis, identifies root causes, recommends improvements
                </p>
              </div>
            </div>
          </div>

          <div className="glass-effect rounded-lg p-6">
            <h3 className="text-2xl font-semibold mb-4 text-accent">DAG Build Engine</h3>
            <p className="opacity-90 mb-4">
              Tasks are executed in topological order based on dependencies:
            </p>
            <pre className="bg-black/40 p-4 rounded-lg">
              <code>{`Task A (no deps) → runs first
Task B (depends on A) → waits for A
Task C (depends on A) → runs parallel to B
Task D (depends on B,C) → runs after both complete`}</code>
            </pre>
            <p className="opacity-90 mt-4">
              This ensures optimal execution order and prevents circular dependencies.
            </p>
          </div>
        </div>
      </section>

      {/* Fix Strategies */}
      <section className="mb-16">
        <h2 className="text-3xl font-bold mb-6 pb-4 border-b border-white/20">
          8-Attempt Fix Loop
        </h2>

        <p className="opacity-90 mb-6">
          When errors occur, JCode uses 5 escalating strategies across 8 attempts:
        </p>

        <div className="glass-effect rounded-lg p-6 space-y-4">
          <div>
            <span className="text-accent font-semibold">Attempts 1-2:</span>
            <span className="opacity-90 ml-2">Standard review with error context</span>
          </div>
          <div>
            <span className="text-accent font-semibold">Attempts 3-4:</span>
            <span className="opacity-90 ml-2">Cross-file dependency analysis</span>
          </div>
          <div>
            <span className="text-accent font-semibold">Attempt 5:</span>
            <span className="opacity-90 ml-2">Targeted root-cause search</span>
          </div>
          <div>
            <span className="text-accent font-semibold">Attempt 6:</span>
            <span className="opacity-90 ml-2">Full context dump (all files + full errors)</span>
          </div>
          <div>
            <span className="text-accent font-semibold">Attempts 7-8:</span>
            <span className="opacity-90 ml-2">Research-based error pattern matching</span>
          </div>
        </div>
      </section>

      {/* Phase System */}
      <section className="mb-16">
        <h2 className="text-3xl font-bold mb-6 pb-4 border-b border-white/20">
          Build Phases
        </h2>

        <div className="space-y-4">
          <div className="glass-effect rounded-lg p-6">
            <h3 className="text-xl font-semibold mb-2 text-accent">Phase 1: Planning</h3>
            <p className="opacity-90">
              Planner creates task DAG, defines dependencies, estimates complexity
            </p>
          </div>

          <div className="glass-effect rounded-lg p-6">
            <h3 className="text-xl font-semibold mb-2 text-accent">Phase 2: Execution</h3>
            <p className="opacity-90">
              Coder generates files, Reviewer checks for issues, auto-fix loop runs if needed
            </p>
          </div>

          <div className="glass-effect rounded-lg p-6">
            <h3 className="text-xl font-semibold mb-2 text-accent">Phase 3: Verification</h3>
            <p className="opacity-90">
              Auto-run project to catch runtime errors (missing imports, syntax errors), 
              fix up to 3 times before handing to user
            </p>
          </div>
        </div>
      </section>

      {/* Memory System */}
      <section className="mb-16">
        <h2 className="text-3xl font-bold mb-6 pb-4 border-b border-white/20">
          Context Management
        </h2>

        <div className="glass-effect rounded-lg p-6">
          <p className="opacity-90 mb-4">
            JCode maintains structured memory across sessions:
          </p>
          <ul className="list-disc list-inside space-y-2 opacity-90">
            <li><strong>Project State:</strong> Current plan, completed tasks, pending tasks</li>
            <li><strong>File Tree:</strong> Full directory structure with metadata</li>
            <li><strong>Build History:</strong> Past errors, fixes applied, iteration count</li>
            <li><strong>Chat History:</strong> Conversation log for natural interaction</li>
          </ul>
          <p className="opacity-90 mt-4">
            State is persisted to <code>~/Desktop/JCode_Workspace/&lt;project&gt;/.jcode/</code>
          </p>
        </div>
      </section>

      {/* Models */}
      <section className="mb-16">
        <h2 className="text-3xl font-bold mb-6 pb-4 border-b border-white/20">
          Model Selection
        </h2>

        <div className="glass-effect rounded-lg p-6 space-y-4">
          <div>
            <p className="font-semibold mb-2">deepseek-r1:14b (Planner + Analyzer)</p>
            <p className="opacity-90">
              Excels at reasoning, planning, and analysis. Uses chain-of-thought for complex decisions.
            </p>
          </div>
          <div>
            <p className="font-semibold mb-2">qwen2.5-coder:14b (Coder + Reviewer)</p>
            <p className="opacity-90">
              Specialized for code generation and review. Fast, accurate, follows conventions.
            </p>
          </div>
        </div>
      </section>

      <div className="mt-16 text-center space-y-4">
        <Link 
          href="/guide"
          className="inline-block px-8 py-3 bg-accent rounded-lg font-semibold hover:bg-accent/80 transition-colors"
        >
          ← Back to Beginner's Guide
        </Link>
        <br />
        <a
          href="https://github.com/ShakenTheCoder/JcodeAgent"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block px-8 py-3 glass-effect rounded-lg font-semibold hover:bg-white/20 transition-colors"
        >
          View Source on GitHub →
        </a>
      </div>
    </div>
  )
}
