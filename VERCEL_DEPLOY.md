# Vercel Deployment Checklist

## ✅ Code Changes (DONE)
- [x] Created Vercel API endpoints for install tracking
- [x] Added analytics dashboard at /api/stats
- [x] Updated install commands in docs to use getjcode.vercel.app
- [x] Added `version` command to CLI
- [x] Bumped version to 0.5.3
- [x] Committed (1c09b08) and pushed to main

## 🚀 Vercel Setup (DO THIS NOW)

### 1. Enable Vercel KV
1. Go to https://vercel.com/dashboard
2. Select your `getjcode.vercel.app` project
3. Navigate to **Storage** tab
4. Click **Create Database** → Select **KV**
5. Name: `jcode-analytics` (or any name)
6. Click **Create & Continue**
7. Connect to your project

### 2. Deploy (if auto-deploy not enabled)
```bash
cd docs
vercel --prod
```

### 3. Test the Endpoints
```bash
# Test install script (should log analytics + return script)
curl -v https://getjcode.vercel.app/install.sh | head -20

# Check analytics dashboard
open https://getjcode.vercel.app/api/stats
```

## 📊 Analytics Schema

After first install, Vercel KV will have:
```
jcode:install:count:unix      → 1
jcode:install:count:windows   → 0
jcode:installs                → ["{"ip":"...", "timestamp":"...", ...}"]
jcode:installs:2026-02-XX     → 1
```

## 🧪 Test Locally (Optional)
```bash
# Requires Vercel CLI with KV connected
cd docs
vercel dev
# Visit http://localhost:3000/api/stats
```

## 📝 Notes
- Analytics fail gracefully — if KV is down, install script still returns
- Vercel free tier: 256MB storage, 10k requests/day (more than enough)
- See `docs/ANALYTICS.md` for detailed documentation
