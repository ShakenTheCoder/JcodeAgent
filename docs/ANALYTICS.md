# JCode Analytics Setup

This document explains the analytics infrastructure for tracking JCode installs.

## Architecture

The install analytics system uses Vercel Edge Functions + Vercel KV (Redis) to track installations in real-time.

### Endpoints

- **`/install.sh`** → `/api/install.sh.js` — Tracks Unix/Linux/macOS installs
- **`/install.ps1`** → `/api/install.ps1.js` — Tracks Windows installs
- **`/api/stats`** → `/api/stats.js` — Analytics dashboard

### Data Collected

Each install logs:
- **IP Address** (first in proxy chain)
- **Timestamp** (ISO 8601)
- **User-Agent** string
- **OS** (inferred from User-Agent: macOS, Linux, Windows)
- **Platform** (`unix` or `windows`)

### Storage Schema (Vercel KV)

```
jcode:install:count:unix      → Integer (total Unix installs)
jcode:install:count:windows   → Integer (total Windows installs)
jcode:installs                → List (last 1000 installs, JSON strings)
jcode:installs:YYYY-MM-DD     → Integer (daily install count, 90-day TTL)
```

## Vercel Setup

### 1. Enable Vercel KV

1. Go to your Vercel project dashboard
2. Navigate to **Storage** → **Create Database** → **KV**
3. Name it `jcode-analytics` (or any name)
4. Click **Create & Continue**
5. Connect to your project (select `getjcode.vercel.app`)

### 2. Environment Variables

Vercel KV automatically injects these variables:
- `KV_REST_API_URL`
- `KV_REST_API_TOKEN`
- `KV_REST_API_READ_ONLY_TOKEN`

No manual configuration needed — the `@vercel/kv` package uses them automatically.

### 3. Deploy

```bash
# From the JcodeAgent repo root
cd docs
vercel --prod
```

The `vercel.json` config ensures `/install.sh` and `/install.ps1` are rewritten to the API endpoints.

## Testing Locally

Install Vercel CLI:
```bash
npm i -g vercel
```

Run dev server:
```bash
cd docs
vercel dev
```

Visit:
- `http://localhost:3000/install.sh` — Should return the install script
- `http://localhost:3000/api/stats` — Should show analytics dashboard

## Dashboard

Visit **`https://getjcode.vercel.app/api/stats`** to see:
- Total installs (Unix + Windows)
- Today's installs
- OS distribution (macOS, Linux, Windows)
- Last 20 installs with timestamps

## Maintenance

- **Data retention**: Last 1000 installs kept in `jcode:installs` list
- **Daily stats**: Expire after 90 days
- **KV limits**: Vercel free tier = 256MB storage, 10k requests/day (plenty for this use case)

## Privacy

- IPs are stored but not displayed publicly on the dashboard
- No personally identifiable information beyond IP/UA
- Data is used solely for install metrics

## Troubleshooting

If analytics fail (e.g., KV down), the install script still returns successfully — errors are logged but don't block installs.

Check Vercel logs:
```bash
vercel logs --prod
```
