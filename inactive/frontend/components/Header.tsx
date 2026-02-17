'use client'

import Link from 'next/link'
import { useTheme } from './ThemeProvider'
import styles from './Header.module.css'

export default function Header() {
  const { theme, toggleTheme } = useTheme()

  return (
    <>
      <div className={styles.themeSwitch}>
        <label className={styles.switch}>
          <input 
            type="checkbox" 
            checked={theme === 'light'} 
            onChange={toggleTheme}
            aria-label="Toggle theme"
          />
          <span className={styles.slider}></span>
        </label>
      </div>

      <div className="container">
        <nav className={styles.nav}>
          <span className={styles.navLogo}>&gt; jcode</span>
          <div className={styles.navLinks}>
            <Link href="#how-it-works">How It Works</Link>
            <Link href="#features">Features</Link>
            <Link href="#releases">Releases</Link>
            <Link href="/guide">Guide</Link>
            <Link href="/technical">Docs</Link>
            <a href="https://github.com/ShakenTheCoder/JcodeAgent" target="_blank" rel="noopener noreferrer">
              GitHub
            </a>
          </div>
        </nav>
      </div>
    </>
  )
}
