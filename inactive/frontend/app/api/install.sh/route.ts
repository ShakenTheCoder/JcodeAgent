import { kv } from '@vercel/kv'
import { NextResponse } from 'next/server'

const INSTALL_SCRIPT_URL = 'https://raw.githubusercontent.com/ShakenTheCoder/JcodeAgent/main/install.sh'

export const runtime = 'edge'

export async function GET(request: Request) {
  const ip = request.headers.get('x-forwarded-for') || request.headers.get('x-real-ip') || 'unknown'
  const userAgent = request.headers.get('user-agent') || 'unknown'
  const timestamp = new Date().toISOString()
  
  // Infer OS from User-Agent
  let os = 'unknown'
  if (userAgent.includes('Mac')) os = 'macOS'
  else if (userAgent.includes('Linux')) os = 'Linux'
  else if (userAgent.includes('Windows')) os = 'Windows'
  
  const installData = {
    ip: ip.split(',')[0].trim(),
    timestamp,
    userAgent,
    os,
    platform: 'unix',
  }

  try {
    await kv.incr('jcode:install:count:unix')
    await kv.lpush('jcode:installs', JSON.stringify(installData))
    await kv.ltrim('jcode:installs', 0, 999)
    
    const dateKey = `jcode:installs:${timestamp.split('T')[0]}`
    await kv.incr(dateKey)
    await kv.expire(dateKey, 90 * 24 * 60 * 60)
  } catch (err) {
    console.error('Analytics error:', err)
  }

  try {
    const response = await fetch(INSTALL_SCRIPT_URL)
    const script = await response.text()
    
    return new Response(script, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain',
        'Cache-Control': 'public, max-age=300',
      },
    })
  } catch (err) {
    return new Response(
      '# Error fetching install script\necho "Failed to download installer. Please try again or visit https://github.com/ShakenTheCoder/JcodeAgent"',
      {
        status: 500,
        headers: { 'Content-Type': 'text/plain' },
      }
    )
  }
}
