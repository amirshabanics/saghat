# Saghat - Deployment Guide

This guide covers deploying Saghat to a Linux server using Docker Compose + Caddy as a reverse proxy, with automated CD via GitHub Actions.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Initial Server Setup](#2-initial-server-setup)
3. [GitHub Secrets](#3-github-secrets)
4. [Environment Variables](#4-environment-variables)
5. [Production Stack](#5-production-stack)
6. [Manual Deployment](#6-manual-deployment)
7. [Updating the App (CD Pipeline)](#7-updating-the-app-cd-pipeline)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Prerequisites

### Server Requirements

- Ubuntu 22.04 LTS or 24.04 LTS
- Minimum 1 vCPU, 1 GB RAM (2 GB recommended)
- A user with `sudo` privileges
- Ports 22, 80, and 443 open in your cloud provider's firewall/security group

### Local Requirements

- Git
- Access to the GitHub repository with permission to add Secrets

---

## 2. Initial Server Setup

Run the setup script **once** on a fresh server. It installs Docker, configures the firewall, and clones the repository.

```bash
# 1. Copy the script to the server (or clone the repo first)
scp deploy/setup-server.sh user@YOUR_SERVER_IP:/tmp/

# 2. SSH into the server
ssh user@YOUR_SERVER_IP

# 3. Run the setup script as root
chmod +x /tmp/setup-server.sh
sudo /tmp/setup-server.sh
```

The script will:

- Update system packages
- Install Docker and Docker Compose plugin
- Create a `deploy` user and add it to the `docker` group
- Clone the repository to `/opt/saghat`
- Create a `.env` file from `.env.example`
- Configure UFW firewall (allow ports 22, 80, 443)
- Enable Docker to start on boot

> **After the script completes**, edit the `.env` file before starting the app:
>
> ```bash
> sudo nano /opt/saghat/.env
> ```

---

## 3. GitHub Secrets

Add these secrets to your GitHub repository under **Settings → Secrets and variables → Actions**:

| Secret Name          | Description                                         | Example                |
| -------------------- | --------------------------------------------------- | ---------------------- |
| `SERVER_HOST`        | Server IP address                                   | `192.168.1.100`        |
| `SERVER_USER`        | SSH username (must have sudo + docker group access) | `deploy`               |
| `SERVER_PASSWORD`    | SSH password for the user                           | `your-secure-password` |
| `SERVER_DEPLOY_PATH` | Absolute path on server where the app is deployed   | `/opt/saghat`          |

> **Security tip:** Use a dedicated deploy user with a strong password. Consider switching to SSH key authentication for better security.

---

## 4. Environment Variables

Edit `/opt/saghat/.env` on the server. All variables from `.env.example` must be set:

| Variable                 | Description                                      | Production Value                          |
| ------------------------ | ------------------------------------------------ | ----------------------------------------- |
| `SECRET_KEY`             | Django secret key (generate a strong random key) | `<50+ char random string>`                |
| `DEBUG`                  | Django debug mode                                | `False`                                   |
| `APP_ENV`                | Application environment                          | `prod`                                    |
| `ALLOWED_HOSTS`          | Allowed hostnames/IPs (JSON array)               | `["YOUR_SERVER_IP"]`                      |
| `DATABASE_URL`           | PostgreSQL connection URL                        | `postgresql://saghat:pass@db:5432/saghat` |
| `REDIS_URL`              | Redis connection URL                             | `redis://redis:6379/0`                    |
| `JWT_SECRET_KEY`         | JWT signing secret                               | `<strong random string>`                  |
| `JWT_ALGORITHM`          | JWT algorithm                                    | `HS256`                                   |
| `JWT_EXPIRE_MINUTES`     | JWT token expiry in minutes                      | `10080` (7 days)                          |
| `BITPIN_API_BASE_URL`    | Bitpin API base URL                              | `https://api.bitpin.ir`                   |
| `BITPIN_API_KEY`         | Bitpin API key                                   | `<your api key>`                          |
| `STATIC_ROOT`            | Path for collected static files                  | `/static_root`                            |
| `DJANGO_SETTINGS_MODULE` | Django settings module                           | `saghat.settings.prod`                    |

Generate a strong `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

---

## 5. Production Stack

The production stack uses two Compose files merged together (as described in [docs.docker.com](https://docs.docker.com/compose/how-tos/multiple-compose-files)):

- `compose.yml` — base configuration (web, db, redis)
- `deploy/compose.prod.yml` — production override (adds Caddy, removes dev volumes, sets restart policies)

### Start the production stack

```bash
cd /opt/saghat

# Build and start all services (web, db, redis, caddy)
docker compose -f compose.yml -f deploy/compose.prod.yml up -d --build
```

### Check service status

```bash
docker compose -f compose.yml -f deploy/compose.prod.yml ps
```

### View logs

```bash
# All services
docker compose -f compose.yml -f deploy/compose.prod.yml logs -f

# Specific service
docker compose -f compose.yml -f deploy/compose.prod.yml logs -f web
docker compose -f compose.yml -f deploy/compose.prod.yml logs -f caddy
```

### Stop the stack

```bash
docker compose -f compose.yml -f deploy/compose.prod.yml down
```

### Architecture

```
Internet → :80 → Caddy (caddy:2-alpine)
                    ↓ reverse_proxy
               web:8000 (Django/Gunicorn)
                    ↓ depends_on
               db:5432 (PostgreSQL)
               redis:6379 (Redis)
```

---

## 6. Manual Deployment

To deploy manually without the CD pipeline:

```bash
# SSH into the server
ssh deploy@YOUR_SERVER_IP

# Navigate to the deploy directory
cd /opt/saghat

# Pull latest code
git pull origin main

# Rebuild and restart containers
docker compose -f compose.yml -f deploy/compose.prod.yml up -d --build

# Run migrations
docker compose -f compose.yml -f deploy/compose.prod.yml exec -T web uv run python manage.py migrate --noinput

# Collect static files
docker compose -f compose.yml -f deploy/compose.prod.yml exec -T web uv run python manage.py collectstatic --noinput
```

---

## 7. Updating the App (CD Pipeline)

The CD pipeline (`.github/workflows/deploy.yml`) runs automatically on every push to `main`:

1. **Trigger**: Push to `main` branch
2. **SSH into server**: Uses `appleboy/ssh-action@v1` with password auth
3. **Pull latest code**: `git pull origin main`
4. **Rebuild containers**: `docker compose ... up -d --build`
5. **Run migrations**: `manage.py migrate --noinput`
6. **Collect static files**: `manage.py collectstatic --noinput`
7. **Health check**: Verifies `http://YOUR_SERVER_IP/_health` returns HTTP 200

### Zero-downtime note

Docker Compose will restart only containers whose image has changed. The database and Redis containers remain running during web service updates, minimizing downtime.

---

## 8. Troubleshooting

### App not accessible on port 80

```bash
# Check if Caddy is running
docker compose -f compose.yml -f deploy/compose.prod.yml ps caddy

# Check Caddy logs
docker compose -f compose.yml -f deploy/compose.prod.yml logs caddy

# Check UFW firewall
sudo ufw status
```

### Database connection errors

```bash
# Check if db container is healthy
docker compose -f compose.yml -f deploy/compose.prod.yml ps db

# Check db logs
docker compose -f compose.yml -f deploy/compose.prod.yml logs db

# Verify DATABASE_URL in .env matches the db service credentials
cat /opt/saghat/.env | grep DATABASE_URL
```

### Migration errors

```bash
# Run migrations manually with output
docker compose -f compose.yml -f deploy/compose.prod.yml exec web uv run python manage.py migrate --verbosity=2

# Check migration status
docker compose -f compose.yml -f deploy/compose.prod.yml exec web uv run python manage.py showmigrations
```

### Container won't start

```bash
# Check container logs
docker compose -f compose.yml -f deploy/compose.prod.yml logs web

# Check if .env file exists and has correct permissions
ls -la /opt/saghat/.env

# Validate the .env file has all required variables
docker compose -f compose.yml -f deploy/compose.prod.yml config
```

### CD pipeline fails

1. Check GitHub Actions logs in the **Actions** tab of your repository
2. Verify all four GitHub Secrets are set correctly
3. Ensure the deploy user can run `docker compose` without sudo:
   ```bash
   # On the server, verify docker group membership
   groups deploy
   # Should include 'docker'
   ```
4. Test SSH connection manually:
   ```bash
   ssh deploy@YOUR_SERVER_IP
   ```

### Health check endpoint

The `/_health` endpoint is handled directly by Caddy (not Django) and always returns `200 OK`. Use it to verify the reverse proxy is running:

```bash
curl -v http://YOUR_SERVER_IP/_health
```

### Caddy log rotation

Caddy access logs are stored in `/var/log/caddy/access.log` inside the `caddy_logs` volume. They rotate automatically at 100 MB, keeping 5 files for up to 30 days.

```bash
# View Caddy access logs
docker compose -f compose.yml -f deploy/compose.prod.yml exec caddy tail -f /var/log/caddy/access.log
```
