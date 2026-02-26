#!/usr/bin/env bash
# =============================================================================
# Saghat - Initial Server Setup Script
# =============================================================================
# Run this script ONCE on a fresh Ubuntu 22.04 / 24.04 server as root or
# a user with sudo privileges.
#
# Usage:
#   chmod +x setup-server.sh
#   sudo ./setup-server.sh
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration - edit these before running
# ---------------------------------------------------------------------------
REPO_URL="https://github.com/YOUR_ORG/saghat.git"   # <-- Replace with your repo URL
DEPLOY_DIR="/opt/saghat"
APP_USER="deploy"   # Non-root user that will own the app files

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()    { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
success() { echo -e "\033[1;32m[OK]\033[0m    $*"; }
warn()    { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
error()   { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; exit 1; }

require_root() {
  if [[ "$EUID" -ne 0 ]]; then
    error "This script must be run as root (or with sudo)."
  fi
}

# ---------------------------------------------------------------------------
# 1. System update
# ---------------------------------------------------------------------------
update_system() {
  info "Updating system packages..."
  apt-get update -y
  apt-get upgrade -y
  apt-get autoremove -y
  success "System packages updated."
}

# ---------------------------------------------------------------------------
# 2. Install Docker (official script)
# ---------------------------------------------------------------------------
install_docker() {
  if command -v docker &>/dev/null; then
    warn "Docker is already installed ($(docker --version)). Skipping."
    return
  fi

  info "Installing Docker via official install script..."
  apt-get install -y curl
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
  success "Docker installed and started."
}

# ---------------------------------------------------------------------------
# 3. Install Docker Compose plugin
# ---------------------------------------------------------------------------
install_docker_compose() {
  if docker compose version &>/dev/null; then
    warn "Docker Compose plugin already available ($(docker compose version)). Skipping."
    return
  fi

  info "Installing Docker Compose plugin..."
  apt-get install -y docker-compose-plugin
  success "Docker Compose plugin installed."
}

# ---------------------------------------------------------------------------
# 4. Create deploy user (optional but recommended)
# ---------------------------------------------------------------------------
create_deploy_user() {
  if id "$APP_USER" &>/dev/null; then
    warn "User '$APP_USER' already exists. Skipping."
  else
    info "Creating deploy user '$APP_USER'..."
    useradd --system --create-home --shell /bin/bash "$APP_USER"
    success "User '$APP_USER' created."
  fi

  info "Adding '$APP_USER' to the docker group..."
  usermod -aG docker "$APP_USER"
  success "'$APP_USER' added to docker group."
}

# ---------------------------------------------------------------------------
# 5. Create deploy directory and clone repository
# ---------------------------------------------------------------------------
setup_repository() {
  info "Creating deploy directory at $DEPLOY_DIR..."
  mkdir -p "$DEPLOY_DIR"

  if [[ -d "$DEPLOY_DIR/.git" ]]; then
    warn "Repository already cloned at $DEPLOY_DIR. Skipping clone."
  else
    info "Cloning repository from $REPO_URL..."
    git clone "$REPO_URL" "$DEPLOY_DIR"
    success "Repository cloned."
  fi

  chown -R "$APP_USER":"$APP_USER" "$DEPLOY_DIR"
  success "Deploy directory ready at $DEPLOY_DIR."
}

# ---------------------------------------------------------------------------
# 6. Create .env file from .env.example
# ---------------------------------------------------------------------------
setup_env_file() {
  local env_file="$DEPLOY_DIR/.env"
  local env_example="$DEPLOY_DIR/.env.example"

  if [[ -f "$env_file" ]]; then
    warn ".env file already exists at $env_file. Skipping."
    return
  fi

  if [[ ! -f "$env_example" ]]; then
    warn ".env.example not found. Creating empty .env file."
    touch "$env_file"
  else
    info "Creating .env from .env.example..."
    cp "$env_example" "$env_file"
    success ".env created at $env_file"
  fi

  warn "⚠️  IMPORTANT: Edit $env_file and fill in all required values before starting the app!"
  warn "   Required values: SECRET_KEY, DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, etc."
  warn "   Also set: APP_ENV=prod, DJANGO_SETTINGS_MODULE=saghat.settings.prod"
  chown "$APP_USER":"$APP_USER" "$env_file"
  chmod 600 "$env_file"
}

# ---------------------------------------------------------------------------
# 7. Ensure Docker starts on boot (already handled by systemctl enable above,
#    but we also make sure the compose stack restarts automatically)
# ---------------------------------------------------------------------------
setup_docker_autostart() {
  info "Ensuring Docker service is enabled on boot..."
  systemctl enable docker
  success "Docker will start automatically on boot."

  info "Note: The compose stack uses 'restart: unless-stopped' policy."
  info "      Containers will restart automatically after a server reboot."
}

# ---------------------------------------------------------------------------
# 8. Configure UFW firewall
# ---------------------------------------------------------------------------
setup_firewall() {
  if ! command -v ufw &>/dev/null; then
    info "Installing UFW..."
    apt-get install -y ufw
  fi

  info "Configuring UFW firewall rules..."

  # Reset to defaults (non-interactive)
  ufw --force reset

  # Default policies
  ufw default deny incoming
  ufw default allow outgoing

  # Allow SSH (critical - must be first to avoid locking yourself out)
  ufw allow 22/tcp comment "SSH"

  # Allow HTTP and HTTPS (Caddy)
  ufw allow 80/tcp  comment "HTTP"
  ufw allow 443/tcp comment "HTTPS"

  # Enable UFW
  ufw --force enable

  success "UFW firewall configured."
  ufw status verbose
}

# ---------------------------------------------------------------------------
# 9. Install git (needed for git pull in CD pipeline)
# ---------------------------------------------------------------------------
install_git() {
  if command -v git &>/dev/null; then
    warn "git already installed ($(git --version)). Skipping."
    return
  fi
  info "Installing git..."
  apt-get install -y git
  success "git installed."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
  require_root

  echo ""
  echo "=============================================="
  echo "  Saghat - Server Setup"
  echo "=============================================="
  echo ""

  update_system
  install_git
  install_docker
  install_docker_compose
  create_deploy_user
  setup_repository
  setup_env_file
  setup_docker_autostart
  setup_firewall

  echo ""
  echo "=============================================="
  success "Server setup complete!"
  echo "=============================================="
  echo ""
  echo "Next steps:"
  echo "  1. Edit the .env file:  nano $DEPLOY_DIR/.env"
  echo "     Fill in: SECRET_KEY, DATABASE_URL, REDIS_URL, JWT_SECRET_KEY"
  echo "     Set:     APP_ENV=prod, DJANGO_SETTINGS_MODULE=saghat.settings.prod"
  echo "     Set:     ALLOWED_HOSTS=[\"YOUR_SERVER_IP\"]"
  echo ""
  echo "  2. Start the production stack:"
  echo "     cd $DEPLOY_DIR"
  echo "     docker compose -f compose.yml -f deploy/compose.prod.yml up -d --build"
  echo ""
  echo "  3. Add GitHub Secrets to your repository:"
  echo "     SERVER_HOST        = $(hostname -I | awk '{print $1}')"
  echo "     SERVER_USER        = $APP_USER  (or your sudo user)"
  echo "     SERVER_PASSWORD    = <your password>"
  echo "     SERVER_DEPLOY_PATH = $DEPLOY_DIR"
  echo ""
  echo "  4. Push to main branch to trigger the CD pipeline."
  echo ""
}

main "$@"
