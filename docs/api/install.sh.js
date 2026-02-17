// Serverless function: /api/install.sh
// Tracks installs and serves the install script

import { kv } from '@vercel/kv';

export const config = {
  runtime: 'edge',
};

const INSTALL_SCRIPT_URL = 'https://raw.githubusercontent.com/ShakenTheCoder/JcodeAgent/main/install.sh';

export default async function handler(req) {
  const ip = req.headers.get('x-forwarded-for') || req.headers.get('x-real-ip') || 'unknown';
  const userAgent = req.headers.get('user-agent') || 'unknown';
  const timestamp = new Date().toISOString();
  
  // Infer OS from User-Agent
  let os = 'unknown';
  if (userAgent.includes('Mac')) os = 'macOS';
  else if (userAgent.includes('Linux')) os = 'Linux';
  else if (userAgent.includes('Windows')) os = 'Windows';
  
  // Log install attempt
  const installData = {
    ip: ip.split(',')[0].trim(), // First IP in case of proxy chain
    timestamp,
    userAgent,
    os,
    platform: 'unix',
  };

  try {
    // Increment global counter
    await kv.incr('jcode:install:count:unix');
    
    // Log individual install
    await kv.lpush('jcode:installs', JSON.stringify(installData));
    
    // Keep only last 1000 installs
    await kv.ltrim('jcode:installs', 0, 999);
    
    // Track daily installs
    const dateKey = `jcode:installs:${timestamp.split('T')[0]}`;
    await kv.incr(dateKey);
    await kv.expire(dateKey, 90 * 24 * 60 * 60); // 90 days expiry
  } catch (err) {
    console.error('Analytics error:', err);
    // Don't fail install if analytics fail
  }

  // Fetch and return the actual install script
  try {
    const response = await fetch(INSTALL_SCRIPT_URL);
    const script = await response.text();
    
    return new Response(script, {
      status: 200,
      headers: {
        'Content-Type': 'text/plain',
        'Cache-Control': 'public, max-age=300', // Cache for 5 minutes
      },
    });
  } catch (err) {
    return new Response('# Error fetching install script\necho "Failed to download installer. Please try again or visit https://github.com/ShakenTheCoder/JcodeAgent"', {
      status: 500,
      headers: { 'Content-Type': 'text/plain' },
    });
  }
}
