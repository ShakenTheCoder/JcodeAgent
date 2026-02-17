import Link from 'next/link'
import { InstallButton } from '@/components/HomeComponents'

export default function GuidePage() {
  return (
    <div className="container mx-auto px-6 py-32 max-w-4xl">
      <Link href="/" className="text-accent hover:underline mb-8 inline-block">
        ← Back to Home
      </Link>

      <h1 className="text-5xl font-bold mb-4">
        Beginner's <span className="text-accent">Guide</span>
      </h1>
      <p className="text-xl opacity-80 mb-12">
        Get started with JCode in minutes — from installation to building your first project.
      </p>

      {/* Installation */}
      <section className="mb-16">
        <h2 className="text-3xl font-bold mb-6 pb-4 border-b border-white/20">
          Installation
        </h2>
        
        <div className="callout glass-effect rounded-lg p-6 mb-8">
          <p className="font-semibold text-accent mb-2">Prerequisites</p>
          <ul className="space-y-2">
            <li>• <strong>Ollama</strong> must be installed and running → <a href="https://ollama.com" target="_blank" rel="noopener" className="text-accent hover:underline">ollama.com</a></li>
            <li>• <strong>Python 3.10+</strong> installed on your system</li>
            <li>• At least 8GB RAM (16GB+ recommended for larger models)</li>
          </ul>
        </div>

        <h3 className="text-2xl font-semibold mb-4 text-accent">Quick Install</h3>
        
        <div className="mb-6">
          <p className="mb-3 font-semibold">macOS / Linux:</p>
          <InstallButton platform="mac" />
        </div>

        <div className="mb-8">
          <p className="mb-3 font-semibold">Windows (PowerShell as Admin):</p>
          <InstallButton platform="windows" />
        </div>

        <p className="opacity-90 mb-4">
          The installer will:
        </p>
        <ul className="list-disc list-inside space-y-2 opacity-90 mb-8">
          <li>Download the required Ollama models (deepseek-r1:14b, qwen2.5-coder:14b)</li>
          <li>Set up a Python virtual environment</li>
          <li>Install JCode and dependencies</li>
          <li>Add jcode to your PATH</li>
        </ul>
      </section>

      {/* First Project */}
      <section className="mb-16">
        <h2 className="text-3xl font-bold mb-6 pb-4 border-b border-white/20">
          Building Your First Project
        </h2>
        
        <div className="space-y-6">
          <div className="glass-effect rounded-lg p-6">
            <div className="flex items-start gap-4">
              <span className="text-accent font-mono font-bold">1.</span>
              <div>
                <p className="font-semibold mb-2">Launch JCode</p>
                <pre className="bg-black/40 p-4 rounded-lg"><code>jcode</code></pre>
              </div>
            </div>
          </div>

          <div className="glass-effect rounded-lg p-6">
            <div className="flex items-start gap-4">
              <span className="text-accent font-mono font-bold">2.</span>
              <div>
                <p className="font-semibold mb-2">Describe your project</p>
                <pre className="bg-black/40 p-4 rounded-lg"><code>jcode&gt; build a todo app with react and local storage</code></pre>
                <p className="mt-4 opacity-90">
                  JCode will plan, implement, review, and verify your project automatically.
                </p>
              </div>
            </div>
          </div>

          <div className="glass-effect rounded-lg p-6">
            <div className="flex items-start gap-4">
              <span className="text-accent font-mono font-bold">3.</span>
              <div>
                <p className="font-semibold mb-2">Interact with your project</p>
                <p className="mb-4 opacity-90">Once built, you'll enter project mode where you can:</p>
                <ul className="list-disc list-inside space-y-2 opacity-90">
                  <li>Chat naturally: "add dark mode"</li>
                  <li>Fix errors: "fix the TypeError in App.js"</li>
                  <li>Run your project: "run"</li>
                  <li>Ask questions: "how does routing work?"</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Commands */}
      <section className="mb-16">
        <h2 className="text-3xl font-bold mb-6 pb-4 border-b border-white/20">
          Available Commands
        </h2>

        <div className="glass-effect rounded-lg p-8 space-y-4">
          <div>
            <code className="text-accent">build &lt;prompt&gt;</code>
            <p className="mt-2 opacity-90">Create a new project from a description</p>
          </div>
          <div>
            <code className="text-accent">projects</code>
            <p className="mt-2 opacity-90">List all saved projects and select one to open</p>
          </div>
          <div>
            <code className="text-accent">continue</code>
            <p className="mt-2 opacity-90">Resume the last project you worked on</p>
          </div>
          <div>
            <code className="text-accent">version</code>
            <p className="mt-2 opacity-90">Show JCode version</p>
          </div>
          <div>
            <code className="text-accent">help</code>
            <p className="mt-2 opacity-90">Display help information</p>
          </div>
          <div>
            <code className="text-accent">quit</code>
            <p className="mt-2 opacity-90">Exit JCode</p>
          </div>
        </div>
      </section>

      {/* Tips */}
      <section className="mb-16">
        <h2 className="text-3xl font-bold mb-6 pb-4 border-b border-white/20">
          Pro Tips
        </h2>

        <div className="space-y-4">
          <div className="glass-effect rounded-lg p-6">
            <h3 className="text-xl font-semibold mb-2 text-accent">Be Specific</h3>
            <p className="opacity-90">
              Instead of "build a website", say "build a portfolio website with React, 
              dark mode toggle, and a contact form using EmailJS"
            </p>
          </div>

          <div className="glass-effect rounded-lg p-6">
            <h3 className="text-xl font-semibold mb-2 text-accent">Let It Fix Errors</h3>
            <p className="opacity-90">
              JCode has an 8-attempt fix loop with escalating strategies. 
              If you see errors, the agent will automatically analyze and fix them.
            </p>
          </div>

          <div className="glass-effect rounded-lg p-6">
            <h3 className="text-xl font-semibold mb-2 text-accent">Use Natural Language</h3>
            <p className="opacity-90">
              In project mode, just chat naturally. The agent understands intent — 
              whether you want to modify code or just discuss architecture.
            </p>
          </div>

          <div className="glass-effect rounded-lg p-6">
            <h3 className="text-xl font-semibold mb-2 text-accent">Projects are Saved</h3>
            <p className="opacity-90">
              All projects are saved to <code>~/Desktop/JCode_Workspace/</code>. 
              You can always return with the <code>projects</code> or <code>continue</code> command.
            </p>
          </div>
        </div>
      </section>

      {/* Troubleshooting */}
      <section>
        <h2 className="text-3xl font-bold mb-6 pb-4 border-b border-white/20">
          Troubleshooting
        </h2>

        <div className="space-y-6">
          <div>
            <h3 className="text-xl font-semibold mb-3 text-accent">
              "Cannot connect to Ollama"
            </h3>
            <p className="opacity-90 mb-2">Make sure Ollama is running:</p>
            <pre className="bg-black/40 p-4 rounded-lg"><code>ollama serve</code></pre>
          </div>

          <div>
            <h3 className="text-xl font-semibold mb-3 text-accent">
              "Model not found"
            </h3>
            <p className="opacity-90 mb-2">Pull the required models manually:</p>
            <pre className="bg-black/40 p-4 rounded-lg"><code>ollama pull deepseek-r1:14b{'\n'}ollama pull qwen2.5-coder:14b</code></pre>
          </div>

          <div>
            <h3 className="text-xl font-semibold mb-3 text-accent">
              Slow Performance
            </h3>
            <p className="opacity-90">
              Large models require significant RAM. Consider using smaller variants 
              or upgrading your hardware. Minimum 8GB RAM, 16GB+ recommended.
            </p>
          </div>
        </div>
      </section>

      <div className="mt-16 text-center">
        <Link 
          href="/technical"
          className="inline-block px-8 py-3 bg-accent rounded-lg font-semibold hover:bg-accent/80 transition-colors"
        >
          Read Technical Documentation →
        </Link>
      </div>
    </div>
  )
}
