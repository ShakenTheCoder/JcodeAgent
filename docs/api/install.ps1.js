// Serverless function: /api/install.ps1
// Tracks Windows installs and serves the PowerShell script

import { kv } from '@vercel/kv';

export const config = {
  runtime: 'edge',
};

const INSTALL_SCRIPT_URL = 'https://raw.githubusercontent.com/ShakenTheCoder/JcodeAgent/main/install.ps1';

export default async function handler(req) {
  const ip = req.headers.get('x-forwarded-for') || req.headers.get('x-real-ip') || 'unknown';
  const userAgent = req.headers.get('user-agent') || 'unknown';
  const timestamp = new Date().toISOString();
  
  const installData = {
    ip: ip.split(',')[0].trim(),
    timestamp,
    userAgent,
    os: 'Windows',
    platform: 'windows',
  };

  try {
    await kv.incr('jcode:install:count:windows');
    await kv.lpush('jcode:installs', JSON.stringify(installData));
    await kv.ltrim('jcode:installs', 0, 999);
    
    const dateKey = `jcode:installs:${timestamp.split('T')[0]}`;
    await kv.incr(dateKey);
    await kv.expire(dateKey, 90 * 24 * 60 * 60);
  } catch (err) {
    console.error('Analytics error:', err);
  }

  try {
    const response = await fetch(INSTALL_SCRIPT_URL);
    const script = await response.text();
    
    return new Response(script, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain',
        'Cache-Control': 'public, max-age=300',
      },
    });
  } catch (err) {
    return new Response('# Error\nWrite-Host "Failed to download installer. Visit https://github.com/ShakenTheCoder/JcodeAgent" -ForegroundColor Red', {
      status: 500,
      headers: { 'Content-Type': 'text/plain' },
    });
  }
}
