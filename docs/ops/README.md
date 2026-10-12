# WenQuest Ops - Operations Runbook

For the IT department or managed service provider (MSP) that installs and runs WenQuest Ops for a business.
Everything runs on one Linux server with Docker. WenQuest Ops talks to ERPNext only through its REST API;
ERPNext runs from its official, unmodified images.

## What gets installed

| Service | Purpose | Reachable from outside |
| --- | --- | --- |
| caddy | HTTPS entry point for both addresses, automatic certificates | yes, ports 80 and 443 |
| hub | WenQuest Ops (web and API) | through Caddy |
| db | PostgreSQL for WenQuest Ops | no |
| erp-* | ERPNext v16: web, workers, scheduler, websocket | ERPNext web through Caddy |
| erp-db, erp-redis-* | MariaDB and Redis for ERPNext | no |

## Requirements

- Ubuntu 22.04 or 24.04 (other Linux with Docker works), 4 CPU cores, 8 GB memory (16 GB recommended),
  40 GB free disk (100 GB recommended)
- Docker Engine with the compose plugin: `curl -fsSL https://get.docker.com | sh`
- Two DNS names pointing at the server, e.g. `ops.example.com` and `erp.ops.example.com`,
  with ports 80 and 443 open; or use `--tls-internal` on an intranet
- The company manifest `company.yaml` (see below)
- A registry token for the private WenQuest Ops image (provided with your subscription)

## 1. Describe the business

Start from the Excel template, fill it in, and convert it:

```bash
pip install wenquest-ops              # or use the hub image: docker run --rm ... python -m wqops.company
python -m wqops.company template company.xlsx
# fill in company.xlsx: Company, Sites, Warehouses, Departments, People, Modules
python -m wqops.company import company.xlsx company.yaml
python -m wqops.company check company.yaml
```

Errors name the sheet, row and column. The template is filled with a fictional demo company;
replace every row with the real business.

## 2. Install

Copy the `deploy/` directory to the server (for example to `/opt/wenquest-ops`) and run:

```bash
cd /opt/wenquest-ops
./install.sh --company company.yaml --domain ops.example.com --email it@example.com \
             --registry-token <token>
```

The first run takes 15-25 minutes (images, the ERPNext site, the setup wizard). It:

1. checks memory, disk and Docker;
2. writes `.env` with generated passwords and keys (mode 600; keep it and the backups safe);
3. checks the company manifest and stores it in `company/company.yaml`;
4. creates the ERPNext site and runs its setup wizard with the company, country, currency, time zone and fiscal year;
5. creates an API key for WenQuest Ops, then the warehouses, departments and addresses in ERPNext;
6. starts WenQuest Ops and Caddy, takes a first backup and prints the status.

Running `install.sh` again is safe: finished steps are skipped.

The ERPNext administrator is `Administrator`; the password is `ERP_ADMIN_PASSWORD` in `.env`.
Sign-in to WenQuest Ops arrives with the next release of Phase 1.

## 3. Daily operation

| Task | Command |
| --- | --- |
| Status (exit code 1 when something is wrong) | `./status.sh` |
| Back up now | `./backup.sh` |
| Restore | `./restore.sh backups/wqo-<time>.tar.gz` |
| Upgrade | `./upgrade.sh [tag] [--company company.yaml]` |
| Logs | `docker compose -p wqo logs -f hub` |

### Backup

`backup.sh` writes `backups/wqo-<time>.tar.gz` with the WenQuest Ops database, the ERPNext database and files,
`.env` and the company manifest, and keeps the newest 14 (`WQO_KEEP`). Schedule it daily:

```bash
echo "30 2 * * * root /opt/wenquest-ops/backup.sh" > /etc/cron.d/wenquest-ops-backup
```

Set `WQO_BACKUP_COPY_TO=/mnt/offsite` to copy each backup to a second location. A backup contains passwords:
store it like one.

### Restore

`restore.sh backups/wqo-<time>.tar.gz` asks for confirmation (or pass `--yes`), then restores both databases and the
ERPNext files. The configuration inside the backup is unpacked into `backups/restore-<time>/` for comparison and is
not copied over the current `.env`.

### Upgrade

`upgrade.sh` backs up first, pulls the new image and restarts. With `--company` it checks the new manifest first
(nothing changes if it has errors) and then creates new warehouses, departments and addresses. The company name,
currency and time zone are fixed at installation.

### Monitoring

- `https://<domain>/api/health` returns 200 with `{"ok": true, ...}` when the database, ERPNext and the company
  manifest are fine, and 503 with the failing check otherwise. Point your RMM or uptime monitor at it.
- `status.sh` exits with 1 when a check fails; it also shows free disk and the newest backup.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Certificate errors | DNS names point at the server; ports 80/443 open; `docker compose -p wqo logs caddy` |
| `/api/health` says `erpnext: error` | `docker compose -p wqo ps`; ERPNext needs a few minutes after a restart |
| `/api/health` says `database: error` | `docker compose -p wqo logs db`; free disk |
| Setup wizard fails | country, currency and time zone in `company.yaml` must be valid ERPNext values |
| Out of memory | ERPNext needs 8 GB at least; check `free -h` |

## Security notes

- Only Caddy is reachable from outside; databases and Redis stay on internal Docker networks.
- `.env`, `company/` and `backups/` hold passwords and business data: keep them on this server, mode 600.
- WenQuest Ops never writes to ERPNext without a person confirming it (ADR-0001, ADR-0002).
