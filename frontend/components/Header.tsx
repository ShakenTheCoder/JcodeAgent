'use client'

import Link from 'next/link'
import { useTheme } from './ThemeProvider'

export default function Header() {
  const { theme, toggleTheme } = useTheme()

  return (
    <header className="fixed top-0 left-0 right-0 z-50 glass-effect">
      <div className="container mx-auto px-6 py-4">
        <div className="flex justify-between items-center">
          <Link href="/" className="flex items-center space-x-2">
            <span className="text-2xl font-bold">JCode</span>
          </Link>
          
          <nav className="hidden md:flex items-center space-x-8">
            <Link href="/#features" className="hover:text-accent transition-colors">
              Features
            </Link>
            <Link href="/#releases" className="hover:text-accent transition-colors">
              Releases
            </Link>
            <Link href="/guide" className="hover:text-accent transition-colors">
              Guide
            </Link>
            <Link href="/technical" className="hover:text-accent transition-colors">
              Docs
            </Link>
            <a
              href="https://github.com/ShakenTheCoder/JcodeAgent"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-accent transition-colors"
            >
              GitHub
            </a>
          </nav>

          <button
            onClick={toggleTheme}
            className="p-2 rounded-lg glass-effect hover:bg-white/20 transition-all"
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>
        </div>
      </div>
    </header>
  )
}
