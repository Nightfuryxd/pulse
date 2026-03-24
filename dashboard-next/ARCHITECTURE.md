# PULSE Dashboard — Architecture

## Overview
The PULSE dashboard is a Next.js 16 application using the App Router pattern. It connects to a FastAPI backend via REST APIs.

```
┌─────────────────────────────────────────────┐
│                  Browser                     │
│  ┌─────────────────────────────────────────┐ │
│  │         Next.js App (Client)            │ │
│  │  ┌──────────┐ ┌──────────┐ ┌─────────┐ │ │
│  │  │ Contexts  │ │   Pages  │ │   UI    │ │ │
│  │  │ Auth,Theme│ │ 31 views │ │ Panel,  │ │ │
│  │  │          │ │          │ │ Badge,  │ │ │
│  │  └──────────┘ └──────────┘ │ Modal.. │ │ │
│  │                            └─────────┘ │ │
│  └────────────────┬────────────────────────┘ │
└───────────────────┼──────────────────────────┘
                    │ REST API (JWT)
┌───────────────────┼──────────────────────────┐
│  FastAPI Backend   │                          │
│  ┌────────────────┴───────────────────────┐  │
│  │  150+ endpoints                        │  │
│  │  /api/nodes, /api/alerts, /api/auth..  │  │
│  └────────────────────────────────────────┘  │
│  In-memory data store                        │
└──────────────────────────────────────────────┘
```

## Directory Structure

```
dashboard-next/
├── src/
│   ├── app/
│   │   ├── layout.tsx          # Root layout (Theme → Auth → Toast providers)
│   │   ├── page.tsx            # Root redirect (auth check)
│   │   ├── globals.css         # CSS variables, theme, animations, print styles
│   │   ├── login/page.tsx      # Login page (outside dashboard shell)
│   │   └── (dashboard)/        # Route group — wrapped in DashboardShell
│   │       ├── layout.tsx      # Dashboard layout (sidebar + topbar + auth guard)
│   │       ├── overview/       # 31 view directories, each with page.tsx
│   │       ├── nodes/
│   │       ├── alerts/
│   │       └── ...
│   ├── components/
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx     # Left nav, 10 sections, mobile responsive
│   │   │   ├── Topbar.tsx      # Theme toggle, notifications, user menu
│   │   │   └── DashboardShell.tsx  # Auth guard + layout wrapper
│   │   └── ui/
│   │       ├── Panel.tsx       # Card container
│   │       ├── Badge.tsx       # Status/severity badges (12+ variants)
│   │       ├── StatCard.tsx    # Metric cards with icons and trends
│   │       ├── Modal.tsx       # Dialog with Escape/click-outside close
│   │       └── Toast.tsx       # Toast notifications via context
│   ├── contexts/
│   │   ├── AuthContext.tsx     # JWT auth state, login/signup/logout
│   │   └── ThemeContext.tsx    # Dark/light toggle, localStorage persist
│   ├── hooks/
│   │   └── useApi.ts          # Data fetching hook (data, loading, error, refetch)
│   └── lib/
│       └── api.ts             # API client class, typed requests, auto-401 redirect
```

## Key Patterns

### Authentication Flow
1. User logs in via `/login` → API returns JWT token
2. Token stored in localStorage, set on ApiClient
3. AuthContext provides `user` state to entire app
4. DashboardShell redirects to `/login` if no user
5. API client auto-redirects on 401 responses

### Data Fetching
- `useApi<T>(url)` hook for GET requests with auto-refresh
- `api.get/post/put/delete` for mutations
- All API calls go through the typed `ApiClient` class

### Theming
- CSS variables defined in `globals.css` under `:root` (dark) and `[data-theme="light"]`
- ThemeContext toggles `data-theme` attribute on `<html>`
- Components use `var(--surface)`, `var(--text)`, etc.

### Mobile Responsiveness
- Sidebar hidden on `< lg` screens, toggled via hamburger menu
- Topbar stretches full width on mobile
- Content area removes left margin on mobile
- Grid layouts collapse to single column on small screens

### Component Hierarchy
```
RootLayout
  └── ThemeProvider
      └── AuthProvider
          └── ToastProvider
              └── DashboardShell (auth guard)
                  ├── Sidebar (mobile: slide-in with overlay)
                  ├── Topbar (hamburger + theme + user menu)
                  └── <main> (page content)
```
