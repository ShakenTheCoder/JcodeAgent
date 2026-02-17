'use client'

import { useState } from 'react'

interface FeatureCardProps {
  icon: string
  title: string
  description: string
}

export function FeatureCard({ icon, title, description }: FeatureCardProps) {
  return (
    <div className="glass-effect rounded-xl p-8 hover:scale-105 transition-transform duration-300">
      <div className="text-4xl mb-4">{icon}</div>
      <h3 className="text-xl font-bold mb-3">{title}</h3>
      <p className="opacity-90">{description}</p>
    </div>
  )
}

interface InstallButtonProps {
  platform: 'mac' | 'windows'
}

export function InstallButton({ platform }: InstallButtonProps) {
  const [copied, setCopied] = useState(false)

  const commands = {
    mac: "curl -fsSL https://getjcode.vercel.app/install.sh | bash",
    windows: "iwr -useb https://getjcode.vercel.app/install.ps1 | iex"
  }

  const copyToClipboard = () => {
    navigator.clipboard.writeText(commands[platform])
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="glass-effect rounded-lg p-4 flex items-center justify-between">
      <code className="text-sm flex-1">{commands[platform]}</code>
      <button
        onClick={copyToClipboard}
        className="ml-4 px-4 py-2 bg-accent rounded-lg hover:bg-accent-light transition-colors"
      >
        {copied ? '✓ Copied!' : 'Copy'}
      </button>
    </div>
  )
}

interface ReleaseItemProps {
  version: string
  date: string
  title: string
  features: string[]
  isLatest?: boolean
}

export function ReleaseItem({ version, date, title, features, isLatest }: ReleaseItemProps) {
  return (
    <div className="glass-effect rounded-xl p-6 mb-4">
      <div className="flex flex-wrap items-center gap-4 mb-4">
        <span className={`px-4 py-1 rounded-full text-sm font-semibold ${isLatest ? 'bg-accent' : 'bg-white/20'}`}>
          {version}
        </span>
        <span className="text-sm opacity-70">{date}</span>
        <span className="text-lg font-bold">{title}</span>
      </div>
      <ul className="space-y-2 opacity-90">
        {features.map((feature, idx) => (
          <li key={idx} className="flex items-start">
            <span className="mr-2">•</span>
            <span dangerouslySetInnerHTML={{ __html: feature }} />
          </li>
        ))}
      </ul>
    </div>
  )
}
