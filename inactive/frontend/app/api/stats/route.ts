import { kv } from '@vercel/kv'

export const runtime = 'edge'

export async function GET() {
  try {
    const unixCount = (await kv.get('jcode:install:count:unix')) || 0
    const windowsCount = (await kv.get('jcode:install:count:windows')) || 0
    const totalCount = Number(unixCount) + Number(windowsCount)
    
    const recentInstalls = await kv.lrange('jcode:installs', 0, 49)
    const parsedInstalls = recentInstalls.map((item) => JSON.parse(item as string))
    
    const osDistribution = {
      macOS: 0,
      Linux: 0,
      Windows: Number(windowsCount),
      unknown: 0,
    }
    
    parsedInstalls.forEach((install: any) => {
      if (install.os === 'macOS') osDistribution.macOS++
      else if (install.os === 'Linux') osDistribution.Linux++
      else if (install.os === 'unknown') osDistribution.unknown++
    })
    
    const today = new Date().toISOString().split('T')[0]
    const todayCount = (await kv.get(`jcode:installs:${today}`)) || 0
    
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JCode Install Analytics</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #fff;
            padding: 40px 20px;
            min-height: 100vh;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            font-size: 2.5rem;
            margin-bottom: 40px;
            text-align: center;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }
        .stat-card {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 30px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .stat-value {
            font-size: 3rem;
            font-weight: bold;
            margin-bottom: 10px;
        }
        .stat-label {
            font-size: 1rem;
            opacity: 0.9;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .recent-installs {
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 12px;
            padding: 30px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }
        .recent-installs h2 {
            margin-bottom: 20px;
            font-size: 1.5rem;
        }
        .install-item {
            padding: 15px;
            background: rgba(0, 0, 0, 0.2);
            border-radius: 8px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }
        .install-time {
            opacity: 0.8;
            font-size: 0.9rem;
        }
        .install-os {
            background: rgba(255, 255, 255, 0.2);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
        }
        .back-link {
            display: inline-block;
            margin-bottom: 20px;
            padding: 10px 20px;
            background: rgba(255, 255, 255, 0.2);
            border-radius: 8px;
            text-decoration: none;
            color: #fff;
            transition: background 0.3s;
        }
        .back-link:hover {
            background: rgba(255, 255, 255, 0.3);
        }
    </style>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">← Back to Home</a>
        <h1>📊 JCode Install Analytics</h1>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">${totalCount}</div>
                <div class="stat-label">Total Installs</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${todayCount}</div>
                <div class="stat-label">Today</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${osDistribution.macOS}</div>
                <div class="stat-label">macOS</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${osDistribution.Linux}</div>
                <div class="stat-label">Linux</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">${osDistribution.Windows}</div>
                <div class="stat-label">Windows</div>
            </div>
        </div>
        
        <div class="recent-installs">
            <h2>Recent Installs</h2>
            ${parsedInstalls
              .slice(0, 20)
              .map((install: any) => {
                const date = new Date(install.timestamp)
                const timeStr = date.toLocaleString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })
                return `
                    <div class="install-item">
                        <span class="install-time">${timeStr}</span>
                        <span class="install-os">${install.os}</span>
                    </div>
                `
              })
              .join('')}
        </div>
    </div>
</body>
</html>`
    
    return new Response(html, {
      status: 200,
      headers: {
        'Content-Type': 'text/html',
        'Cache-Control': 'public, max-age=60',
      },
    })
  } catch (err) {
    console.error('Stats error:', err)
    return new Response(`Error loading stats: ${err}`, {
      status: 500,
      headers: { 'Content-Type': 'text/plain' },
    })
  }
}
