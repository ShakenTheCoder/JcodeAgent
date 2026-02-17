import Link from 'next/link'
import styles from './Footer.module.css'

export default function Footer() {
  return (
    <footer className={styles.footer}>
      <div className="container">
        <p>
          JCode is open source · MIT License · Developed by{' '}
          <a 
            href="https://www.linkedin.com/in/ioan-andrei-bbb908268/" 
            target="_blank" 
            rel="noopener noreferrer"
          >
            Ioan Andrei
          </a>
        </p>
        <p className={styles.footerLinks}>
          <a 
            href="https://github.com/ShakenTheCoder/JcodeAgent" 
            target="_blank" 
            rel="noopener noreferrer"
          >
            GitHub
          </a>
          {' · '}
          <Link href="#releases">Changelog</Link>
          {' · '}
          <Link href="/guide">Beginner Guide</Link>
          {' · '}
          <Link href="/technical">Technical Docs</Link>
        </p>
      </div>
    </footer>
  )
}
