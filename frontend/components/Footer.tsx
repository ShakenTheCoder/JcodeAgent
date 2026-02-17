import Link from 'next/link'

export default function Footer() {
  const currentYear = new Date().getFullYear()

  return (
    <footer className="glass-effect mt-20">
      <div className="container mx-auto px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          <div>
            <h3 className="text-xl font-bold mb-4">JCode</h3>
            <p className="text-sm opacity-80">
              Local AI coding agent powered by Ollama.
            </p>
          </div>

          <div>
            <h4 className="font-semibold mb-4">Resources</h4>
            <ul className="space-y-2 text-sm opacity-80">
              <li>
                <Link href="/guide" className="hover:text-accent transition-colors">
                  Getting Started
                </Link>
              </li>
              <li>
                <Link href="/technical" className="hover:text-accent transition-colors">
                  Technical Docs
                </Link>
              </li>
              <li>
                <Link href="/api/stats" className="hover:text-accent transition-colors">
                  Analytics
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <h4 className="font-semibold mb-4">Community</h4>
            <ul className="space-y-2 text-sm opacity-80">
              <li>
                <a
                  href="https://github.com/ShakenTheCoder/JcodeAgent"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-accent transition-colors"
                >
                  GitHub
                </a>
              </li>
              <li>
                <a
                  href="https://github.com/ShakenTheCoder/JcodeAgent/issues"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-accent transition-colors"
                >
                  Issues
                </a>
              </li>
              <li>
                <a
                  href="https://www.linkedin.com/in/ioan-andrei-bbb908268/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-accent transition-colors"
                >
                  LinkedIn
                </a>
              </li>
            </ul>
          </div>

          <div>
            <h4 className="font-semibold mb-4">Legal</h4>
            <ul className="space-y-2 text-sm opacity-80">
              <li>
                <a
                  href="https://github.com/ShakenTheCoder/JcodeAgent/blob/main/LICENSE"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-accent transition-colors"
                >
                  MIT License
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 pt-8 border-t border-white/10 text-center text-sm opacity-60">
          © {currentYear} JCode. Built with ❤️ by{' '}
          <a
            href="https://www.linkedin.com/in/ioan-andrei-bbb908268/"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-accent transition-colors"
          >
            Ioan Andrei
          </a>
        </div>
      </div>
    </footer>
  )
}
