# Arca Frontend

Next.js 14 dashboard for the Arca self-improving agent platform.
Talks to the FastAPI backend over HTTPS.

## Stack

- Next.js 14 (App Router)
- TypeScript + Tailwind CSS
- Inter (sans) + Fraunces (display serif) via `next/font/google`

## Local dev

```bash
cd frontend
npm install
cp .env.example .env.local   # edit if your backend isn't at http://localhost:8000
npm run dev
```

Open <http://localhost:3000>.

## Env vars

| Var | Example | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `https://arca-pet9.onrender.com` | Where the backend lives |

## Pages

| Route | Purpose |
| --- | --- |
| `/` | Editorial landing page — hero + 3 agent showcases |
| `/chat` | Live chat with feedback ↑/↓ |
| `/dashboard` | Per-agent scorecards |
| `/sandboxes` | List of shadow agents |
| `/sandboxes/[id]` | Config, scores, vs-production compare |
| `/optimizer` | Recent runs + manual trigger |
| `/promotions` | Approval queue |
| `/promotions/[id]` | Gate detail + approve/reject |
| `/versions` | Per-agent timeline + rollback |

## Deploy

Push to GitHub. Import the repo on [vercel.com](https://vercel.com),
set the **Root Directory** to `frontend/`, add the env var
`NEXT_PUBLIC_API_URL=https://arca-pet9.onrender.com`, deploy.
