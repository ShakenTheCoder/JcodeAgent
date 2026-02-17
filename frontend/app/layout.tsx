import type { Metadata } from 'next'
import './globals.css'
import { ThemeProvider } from '@/components/ThemeProvider'
import Header from '@/components/Header'
import Footer from '@/components/Footer'

export const metadata: Metadata = {
  title: 'JCode — Local AI Coding Agent',
  description: 'Build complete projects from a single prompt. Powered by Ollama, running 100% locally.',
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
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
      </head>
      <body className="gradient-bg text-white min-h-screen">
        <ThemeProvider>
          <Header />
          <main>{children}</main>
          <Footer />
        </ThemeProvider>
      </body>
    </html>
  )
}
