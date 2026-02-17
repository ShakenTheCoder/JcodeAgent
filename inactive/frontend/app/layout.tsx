import type { Metadata } from 'next'
import './globals.css'
import { ThemeProvider } from '@/components/ThemeProvider'
import Header from '@/components/Header'
import Footer from '@/components/Footer'

export const metadata: Metadata = {
  title: 'JCode — Your Local, Unlimited & Private Software Engineer',
  description: 'JCode is a local AI coding agent that iterates until your project works. 4 AI roles, zero cloud, 100% private.',
  keywords: 'AI coding agent, local AI, Ollama, code generation, project builder',
  authors: [{ name: 'Ioan Andrei' }],
  openGraph: {
    title: 'JCode — Local AI Coding Agent',
    description: 'Build complete projects from a single prompt. Powered by Ollama, running 100% locally.',
    url: 'https://getjcode.vercel.app',
    siteName: 'JCode',
    locale: 'en_US',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'JCode — Local AI Coding Agent',
    description: 'Build complete projects from a single prompt. Powered by Ollama, running 100% locally.',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/JcodeLogo.ico" type="image/x-icon" />
      </head>
      <body>
        <ThemeProvider>
          <Header />
          {children}
          <Footer />
        </ThemeProvider>
      </body>
    </html>
  )
}
