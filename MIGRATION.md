# Migration from Static HTML to Next.js

This document explains the migration from `docs/` (static HTML) to `frontend/` (Next.js).

## What Changed

### Structure
```
OLD (docs/):                    NEW (frontend/):
├── index.html              →   ├── app/page.tsx
├── beginner-guide.html     →   ├── app/guide/page.tsx
├── technical.html          →   ├── app/technical/page.tsx
├── api/install.sh.js       →   ├── app/api/install.sh/route.ts
├── api/install.ps1.js      →   ├── app/api/install.ps1/route.ts
├── api/stats.js            →   ├── app/api/stats/route.ts
└── vercel.json             →   ├── vercel.json (updated routing)
                                └── components/ (extracted shared UI)
```

### Technology Stack
- **Old:** Pure HTML/CSS/JS, Vercel serverless functions
- **New:** Next.js 14, React 18, TypeScript, Tailwind CSS, Edge Runtime

### Key Improvements

1. **Component Reusability**
   - Extracted `<Header>`, `<Footer>`, `<ThemeProvider>` for consistency
   - Created `<FeatureCard>`, `<InstallButton>`, `<ReleaseItem>` for clean code

2. **Type Safety**
   - Full TypeScript coverage
   - Compile-time error checking
   - Better IDE autocomplete

3. **Performance**
   - Server-side rendering for faster initial load
   - Automatic code splitting
   - Optimized bundle sizes

4. **Developer Experience**
   - Hot module reload
   - Modern tooling (ESLint, Prettier)
   - Better debugging with React DevTools

5. **Maintainability**
   - Single source of truth for styles (Tailwind)
   - Easier to add new pages/features
   - Better code organization

## Migration Steps (Already Done)

✅ 1. Created Next.js project structure  
✅ 2. Converted HTML pages to React components  
✅ 3. Migrated API endpoints to Next.js API routes  
✅ 4. Extracted shared components (Header, Footer, etc.)  
✅ 5. Converted CSS to Tailwind utility classes  
✅ 6. Copied assets (favicon, icons) to `public/`  
✅ 7. Configured vercel.json for routing  

## Next Steps (TODO)

⬜ 1. Install dependencies:
```bash
cd frontend
npm install
```

⬜ 2. Test locally:
```bash
npm run dev
# Visit http://localhost:3000
```

⬜ 3. Build for production:
```bash
npm run build
```

⬜ 4. Deploy to Vercel:
```bash
vercel --prod
```

## Vercel Configuration

The new `frontend/vercel.json` handles routing:
- `/install.sh` → `/api/install.sh` (Next.js route)
- `/install.ps1` → `/api/install.ps1` (Next.js route)

Analytics still require Vercel KV (same setup as before).

## Backward Compatibility

- All URLs remain the same (`/`, `/guide`, `/technical`, `/api/stats`)
- Install commands unchanged (`curl https://getjcode.vercel.app/install.sh | bash`)
- Analytics schema unchanged (same KV keys)

## Old `docs/` Folder

The old `docs/` folder can be kept as reference or archived. The frontend is now fully standalone in `frontend/`.

## Future Enhancements

Now that we're on Next.js, we can easily add:
- Blog with MDX support
- Search functionality
- Interactive demos
- User authentication (if needed)
- API documentation with Swagger/OpenAPI
- Real-time stats dashboard (WebSocket)
