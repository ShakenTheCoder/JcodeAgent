# JCode Frontend - Next.js

This is the Next.js frontend for JCode's landing page and documentation.

## Project Structure

```
frontend/
├── app/
│   ├── layout.tsx          # Root layout with theme provider
│   ├── page.tsx            # Home page
│   ├── guide/page.tsx      # Beginner's guide
│   ├── technical/page.tsx  # Technical documentation
│   ├── globals.css         # Global styles + Tailwind
│   └── api/
│       ├── install.sh/route.ts   # Install script with analytics
│       ├── install.ps1/route.ts  # Windows installer
│       └── stats/route.ts        # Analytics dashboard
├── components/
│   ├── Header.tsx          # Navigation header
│   ├── Footer.tsx          # Site footer
│   ├── ThemeProvider.tsx   # Dark/light theme context
│   └── HomeComponents.tsx  # Reusable home page components
├── public/
│   └── *.ico               # Favicons
├── package.json
├── tsconfig.json
├── tailwind.config.ts
└── vercel.json             # Vercel routing config
```

## Development

Install dependencies:
```bash
npm install
```

Run dev server:
```bash
npm run dev
```

Visit http://localhost:3000

## Build

```bash
npm run build
npm start
```

## Deployment

Configured for Vercel with:
- Edge runtime for API routes
- Vercel KV for analytics storage
- Automatic rewrites for `/install.sh` and `/install.ps1`

## Analytics

Install tracking requires Vercel KV:
1. Go to Vercel dashboard → Storage → Create Database → KV
2. Name: `jcode-analytics`
3. Connect to project
4. Deploy

See `/api/stats` for the analytics dashboard.
