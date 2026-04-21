# Banking Agent · Deployment runbook (Railway)

Target state: a public HTTPS URL that serves a minimal chat UI + `/api/chat` + `/healthz`, backed by your existing AWS RDS Postgres and Pinecone.

---

## 0. Pre-flight (local, 2 min)

```bash
cd Banking_Agent_reorg
python -c "from src.server.app import app; print('import ok, routes:', [r.path for r in app.routes if hasattr(r,'path')])"
```

Should print `/healthz`, `/api/chat`, `/`. If it fails, fix locally first — Railway won't make broken imports magically work.

Optional Docker smoke-test once Docker Desktop is running:

```bash
docker build -t banking-agent .
docker run --rm --env-file .env -p 8000:8000 banking-agent
curl -s localhost:8000/healthz    # => {"status":"ok"}
open http://localhost:8000        # chat UI
```

---

## 1. Push to GitHub

Your current branch is `reorg`. Two options:

**A. Deploy the `reorg` branch directly** (recommended — least churn):
```bash
git add -A
git commit -m "feat(agent): modular monolith + FastAPI + Pydantic contracts for Railway"
git push origin reorg
```

**B. Merge into `main` first**: `git checkout main && git merge reorg && git push`.

---

## 2. Railway project setup

1. Go to https://railway.com → sign in with GitHub.
2. **New Project → Deploy from GitHub repo** → select `NaNa7Miiii/Banking_Agent` → pick branch `reorg` (or whichever you pushed).
3. Railway auto-detects `Dockerfile` and starts building. The build takes ~3–5 min on first run (wheels for `xgboost`, `psycopg2`, etc).
4. **Settings → Networking → Generate Domain** → get `xxx.up.railway.app`.
5. **Settings → Healthcheck**:
   - Path: `/healthz`
   - Timeout: 60 seconds (cold start is slow)
6. **Settings → Deploy → Region**: pick one close to your RDS (e.g. `us-east-1` if your RDS is there).

---

## 3. Environment variables

**Variables** tab → paste the whole block below (values from your local `.env`):

```
OPENAI_API_KEY=sk-...
DB_HOST=xxx.xxx.rds.amazonaws.com
DB_PORT=5432
DB_USERNAME=postgres
DB_PASSWORD=...
DB_DATABASE=customer_transaction_db
DB_TABLE_NAME=transactions
PINECONE_API_KEY=...
PINECONE_INDEX_NAME=cibc-docs-hybrid
RAG_DEFAULT_NAMESPACE=cibc-en
TAVILY_API_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
MAX_CONCURRENT_STEPS=4
SQL_DEFAULT_LIMIT=200
SQL_MAX_ROWS=1000
LOG_LEVEL=INFO
```

Do **not** set `PORT` — Railway injects it automatically and the Dockerfile `CMD` passes it to uvicorn.

After saving, Railway redeploys.

---

## 4. AWS RDS → whitelist Railway egress IPs

Railway publishes a static list of outbound IP ranges per region (search the Railway docs for **"static outbound IPs"** or **"egress IP ranges"**).

1. AWS Console → **RDS → Databases → <your db> → Connectivity & security → VPC security groups** → click the SG.
2. **Inbound rules → Edit inbound rules → Add rule**:
   - Type: `PostgreSQL`
   - Port: `5432` (auto)
   - Source: `Custom` → paste Railway's egress CIDR(s) for your region, e.g. `66.33.22.0/24`
   - Description: `Railway agent egress`
3. Verify the DB is **Publicly accessible: Yes** (Connectivity & security panel). Otherwise Railway can't reach it even with the SG rule.
4. Save.

From Railway logs (Deployments tab) you should now see successful SQL queries on a test chat.

---

## 5. Smoke test in production

```bash
# Replace with your generated domain.
APP=https://xxx.up.railway.app

curl -s $APP/healthz                # => {"status":"ok"}

curl -s -X POST $APP/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"How much did I spend last month?","customer_id":"CUST_0001","session_id":"demo"}' | jq .
```

Browser: open `$APP` → you'll see the demo UI.

---

## 6. Demo-day checklist (pre rehearsal)

- [ ] Deployed 24h before the demo, not the morning of.
- [ ] Ran ≥3 queries end-to-end and saved screenshots (backup if network dies).
- [ ] Warmed up at T-30min: `curl $APP/healthz` + one real chat → subsequent requests stay warm.
- [ ] Browser tab open, `$APP` loaded. Backup: local `docker run` on your laptop.
- [ ] Slide showing the architecture diagram (mermaid in the plan doc).

---

## 7. Known knobs to tighten later (post-demo)

- Switch to **Railway Redis add-on** for conversation memory (it injects `REDIS_URL`; small edit in `src/utils/memory.py`).
- Replace the inline Python config with a `railway.json` or a `Procfile` if you want non-Docker deploy.
- Move from free Pinecone sandbox to paid if you outgrow 100k vectors.
- Split `subagent:sql|rag|fraud` into separate Railway services once you need to scale them independently. The Pydantic schemas in `src/graph/*/schema.py` are already the wire contract; each handler in `executor.py` would become an HTTP client call.
