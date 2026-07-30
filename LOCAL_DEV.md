# Running CreditFlow locally without Docker

This repo is 13 FastAPI services + a Celery worker + a React frontend, all
designed around **one Postgres instance, one Redis instance, one RabbitMQ
instance, one MongoDB instance** (see `docs/ARCHITECTURE.md`). Every
service's `app/config.py` already has sane localhost defaults for
non-Docker dev — the trick is just getting infra listening on the *exact*
ports those defaults expect, so you don't have to hand-edit 13 `.env` files.

## 0. Prerequisites

- Python 3.12
- Node 18+
- Postgres 16, Redis 7, RabbitMQ 3.13 (with management plugin), MongoDB 7
  installed natively (Homebrew on macOS, apt on Ubuntu/Debian, or your
  distro's package manager)
- `openssl`

## 1. Start infra on the ports the code already expects

The services default to the **host-published ports** from
`docker-compose.override.yml` (5433/6380/5673/27018), not the standard
ones, so nothing else running on your machine conflicts with them. Two
ways to get there — pick one: run infra manually on those exact ports
(**Option A**, assumed for the rest of this guide), or run infra on
standard ports and override every service's `.env` instead (**Option B**
— more repetitive, skip unless you have a reason to).

### Option A on macOS/Linux
```bash
# Postgres
pg_ctl -D /usr/local/var/postgres -o "-p 5433" -l pg.log start   # path varies by install

# Redis
redis-server --port 6380 --daemonize yes

# RabbitMQ (AMQP on 5673, mgmt UI stays on 15672)
RABBITMQ_NODE_PORT=5673 rabbitmq-server -detached

# MongoDB
mongod --port 27018 --dbpath /usr/local/var/mongodb --fork --logpath mongo.log
```

### Option A on Windows (Git Bash)

None of the infra tools ship with Windows or Git Bash — they need to be
installed first. [Chocolatey](https://chocolatey.org/install) is the
least painful way (run these in an **elevated** PowerShell/CMD, not Git
Bash — Chocolatey needs admin rights):

```powershell
choco install postgresql16 --params '/Password:creditflow' -y
choco install mongodb -y
choco install rabbitmq -y        # pulls in Erlang automatically
choco install memurai-developer -y   # Redis-compatible server for Windows; "redis-64" also works
```

Close and reopen Git Bash afterward so PATH updates take effect. Each of
these installs as a **Windows service on its default port**
(5432/27017/5672/6379) — getting them onto 5433/6380/5673/27018 needs a
one-time config change per service rather than a start-up flag:

- **Postgres**: open `services.msc`, stop `postgresql-x64-16`. Edit
  `port = 5433` in `C:\Program Files\PostgreSQL\16\data\postgresql.conf`.
  Start the service again.
- **Redis/Memurai**: open `services.msc`, stop the service. Edit the
  `port` setting in its config file (`C:\Program Files\Memurai\memurai.conf`,
  or the redis package's `.conf`). Start the service again.
- **RabbitMQ**: create/edit
  `C:\Users\<you>\AppData\Roaming\RabbitMQ\rabbitmq.conf` (or
  `%RABBITMQ_BASE%\rabbitmq.conf`) with `listeners.tcp.default = 5673`,
  then restart the `RabbitMQ` service from `services.msc`.
- **MongoDB**: stop the `MongoDB` service in `services.msc`, edit `port:
  27018` in `C:\Program Files\MongoDB\Server\7.0\bin\mongod.cfg`, start it
  again.

After that, each runs automatically in the background as a Windows
service — you don't need to start them manually every session, just leave
them running and jump straight to step 2 next time.

**Simpler alternative:** if you don't mind enabling
[WSL2](https://learn.microsoft.com/windows/wsl/install), install Ubuntu
inside it and run the macOS/Linux commands above verbatim — apt-get
installs of Postgres/Redis/RabbitMQ/MongoDB behave exactly like the Linux
case and custom ports are just a start-up flag, no service-config editing.
Your Windows filesystem (including this repo) is reachable from WSL at
`/mnt/c/...`, and `localhost` is shared between WSL2 and Windows, so
services running inside WSL2 are still reachable at `localhost:<port>`
from Git Bash / your browser.

Verify (from Git Bash, once services are up — for Postgres/Mongo you'll
need `psql`/`mongosh` on PATH, which the installers above add):
```bash
psql -h localhost -p 5433 -U creditflow -c '\conninfo'   # after step 2 creates the role/db
redis-cli -p 6380 ping        # or: memurai-cli -p 6380 ping
rabbitmqctl status            # or check http://localhost:15672 (guest/guest)
mongosh --port 27018 --eval 'db.runCommand({ping:1})'
```

## 2. Create the Postgres role, database, and per-service schemas

```bash
createuser -p 5433 -U postgres --createdb --pwprompt creditflow   # password: creditflow
createdb -p 5433 -U creditflow creditflow
psql -h localhost -p 5433 -U creditflow -d creditflow -f scripts/init_schemas.sql
```

This creates the 11 schemas (`auth`, `tenant`, `billing`, `credits`,
`usage`, `ai`, `content`, `scheduler`, `social`, `notification`, `admin`) —
one per Postgres-backed service. `api-gateway` has no DB state;
`scraper-service` uses MongoDB instead.

## 3. Generate the JWT keypair

Only the public key ships in the repo (`keys/jwt_public.pem`); the private
key is gitignored on purpose. Generate a matching pair for local dev:

```bash
openssl genrsa -out keys/jwt_private.pem 2048
openssl rsa -in keys/jwt_private.pem -pubout -out keys/jwt_public.pem
```

`auth-service` is the only service that reads the private key; everyone
else only verifies signatures with the public key.

## 4. Install dependencies and run migrations

```bash
bash scripts/setup_venvs.sh
```

This creates a `.venv` inside each `services/<name>/` folder, installs
that service's `requirements.txt`, and runs `alembic upgrade head` for
every service that has migrations (all except `api-gateway` and
`scraper-service`).

## 5. Start everything

```bash
bash scripts/start_all.sh
```

This backgrounds all 13 `uvicorn --reload` processes on the ports the
gateway already expects (see table below), plus the scheduler's Celery
worker+beat. Logs go to `logs/<service>.log`; PIDs to `run/<service>.pid`.

```bash
bash scripts/stop_all.sh   # stop everything later
```

| Service | Port | Health check |
|---|---|---|
| api-gateway | 8000 | http://localhost:8000/healthz |
| auth-service | 8001 | http://localhost:8001/healthz |
| user-service | 8002 | http://localhost:8002/healthz |
| billing-service | 8003 | http://localhost:8003/healthz |
| credits-service | 8004 | http://localhost:8004/healthz |
| usage-service | 8005 | http://localhost:8005/healthz |
| ai-generation-service | 8006 | http://localhost:8006/healthz |
| content-service | 8007 | http://localhost:8007/healthz |
| scheduler-service | 8008 | http://localhost:8008/healthz |
| social-publishing-service | 8009 | http://localhost:8009/healthz |
| scraper-service | 8010 | http://localhost:8010/healthz |
| notification-service | 8011 | http://localhost:8011/healthz |
| admin-service | 8012 | http://localhost:8012/healthz |

Everything routes through the gateway at `:8000` — that's the only port
the frontend talks to.

## 6. Frontend

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL=http://localhost:8000
npm run dev            # http://localhost:5173
```

## 7. Secrets you'll want for full functionality

Everything above boots and answers `/healthz` with just the defaults. For
features that call third parties, export these before starting the
relevant service (or put them in that service's own `.env`):

- `ai-generation-service`: `OPENROUTER_API_KEY`
- `billing-service`: `STRIPE_SECRET_KEY`, `STRIPE_PRICE_ID_PRO`, `STRIPE_PRICE_ID_TEAM`
- `social-publishing-service`: `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `TOKEN_ENCRYPTION_KEY` (a base64 Fernet key)
- `notification-service`: `RESEND_API_KEY`

Without these, everything still runs — those specific integrations will
just fail at call-time rather than at startup.

## Troubleshooting

- **`relation "X" does not exist` on first request** → a schema wasn't
  created before migrations ran. Re-run `scripts/init_schemas.sql`, then
  `alembic upgrade head` for that one service.
- **A service can't reach Postgres/Redis/RabbitMQ** → confirm it's
  listening on the port that service's `app/config.py` defaults to (see
  step 1), or check `logs/<service>.log`.
- **`ModuleNotFoundError` when running alembic directly** → run it from
  inside that service's folder with its own `.venv`, e.g.
  `cd services/auth-service && ./.venv/bin/alembic upgrade head`.
- **JWT verification fails everywhere** → the public/private key don't
  match; regenerate both from the same `openssl genrsa` (step 3) and
  restart every service.
