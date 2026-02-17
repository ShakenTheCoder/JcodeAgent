import Link from 'next/link'
import { FeatureCard, InstallButton, ReleaseItem } from '@/components/HomeComponents'

export default function Home() {
  const features = [
    {
      icon: '🤖',
      title: '4-Role Architecture',
      description: 'Planner, Coder, Reviewer, and Analyzer agents work together to build your project with precision.',
    },
    {
      icon: '🔄',
      title: 'DAG Build Engine',
      description: 'Task dependencies are resolved in a directed acyclic graph, ensuring optimal execution order.',
    },
    {
      icon: '💬',
      title: 'Pure Chat Interface',
      description: 'Natural language interaction — just describe what you want, no commands to memorize.',
    },
    {
      icon: '🔧',
      title: 'Agentic Auto-Fix',
      description: 'Runtime errors are automatically captured, analyzed, and fixed with multi-attempt loops.',
    },
    {
      icon: '🏠',
      title: '100% Local',
      description: 'Powered by Ollama — your code never leaves your machine. Complete privacy guaranteed.',
    },
    {
      icon: '⚡',
      title: 'Post-Build Verification',
      description: 'Phase 3 runtime checks catch missing imports and runtime errors before you see them.',
    },
  ]

  const releases = [
    {
      version: 'v0.5.3',
      date: 'Feb 2026',
      title: 'Analytics & Version Command',
      features: [
        'Analytics-enabled install endpoints via Vercel serverless functions',
        'Real-time install metrics: IP, timestamp, User-Agent, OS, counter',
        'Dashboard at /api/stats showing install statistics',
        'New <code>version</code> command in CLI to display current version',
        'Install commands now use getjcode.vercel.app for tracking',
      ],
      isLatest: true,
    },
    {
      version: 'v0.5.2',
      date: 'Feb 2026',
      title: 'Agentic Auto-Fix',
      features: [
        'Auto-capture runtime errors and feed to agent (5-attempt loop)',
        'Post-build Phase 3: runtime verification catches missing imports',
        'CHAT_SYSTEM prompt rewritten: no generic tips, reads actual files, outputs fixes',
        'Smart run command: detects project type and executes properly',
      ],
    },
    {
      version: 'v0.5.1',
      date: 'Feb 2026',
      title: 'Resilient Fix Engine & Docs',
      features: [
        '8-attempt fix loop with 5 escalating strategies',
        'Cross-file dependency analysis for deeper root cause detection',
        'Research-based error pattern matching (last resort strategy)',
        'Agent knows how to run and deploy all major project types',
        'Beginner guide and technical documentation',
        'Landing page dark/light theme toggle',
      ],
    },
  ]

  return (
    <div className="pt-20">
      {/* Hero Section */}
      <section className="container mx-auto px-6 py-20 text-center">
        <h1 className="text-5xl md:text-7xl font-bold mb-6">
          Build Projects with <span className="text-accent">AI</span>
        </h1>
        <p className="text-xl md:text-2xl mb-12 opacity-90 max-w-3xl mx-auto">
          A local AI coding agent that creates complete, production-ready projects from a single prompt.
          <br />
          Powered by <strong>Ollama</strong> — 100% local, 100% private.
        </p>

        <div className="max-w-4xl mx-auto space-y-6 mb-12">
          <div>
            <h3 className="text-lg font-semibold mb-3">macOS / Linux</h3>
            <InstallButton platform="mac" />
          </div>
          <div>
            <h3 className="text-lg font-semibold mb-3">Windows (PowerShell)</h3>
            <InstallButton platform="windows" />
          </div>
        </div>

        <div className="flex justify-center gap-4 flex-wrap">
          <Link
            href="/guide"
            className="px-8 py-3 bg-accent rounded-lg font-semibold hover:bg-accent-light transition-colors"
          >
            Get Started
          </Link>
          <a
            href="https://github.com/ShakenTheCoder/JcodeAgent"
            target="_blank"
            rel="noopener noreferrer"
            className="px-8 py-3 glass-effect rounded-lg font-semibold hover:bg-white/20 transition-colors"
          >
            View on GitHub
          </a>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="container mx-auto px-6 py-20">
        <h2 className="text-4xl font-bold text-center mb-12">
          <span className="text-accent">Features</span> that matter
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {features.map((feature, idx) => (
            <FeatureCard key={idx} {...feature} />
          ))}
        </div>
      </section>

      {/* Releases Section */}
      <section id="releases" className="container mx-auto px-6 py-20">
        <h2 className="text-4xl font-bold text-center mb-4">
          Release <span className="text-accent">history</span>
        </h2>
        <p className="text-center opacity-80 mb-12">Latest updates and improvements.</p>
        <div className="max-w-4xl mx-auto">
          {releases.map((release, idx) => (
            <ReleaseItem key={idx} {...release} />
          ))}
        </div>
      </section>
    </div>
  )
}
