#!/usr/bin/env bash
# Provision nginx on a host from this repo plus a machine-local SSL backup.
# Operates on whatever is currently checked out; does not touch git.
# Does not install or start nginx.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NGINX_CONF_SRC="$SCRIPT_DIR/nginx-conf"
S6_SRC="$SCRIPT_DIR/s6-nginx"
NGINX_USER="www-data"
CONFIGURE_S6=""
SSL_BACKUP_DIR=""

print_prerequisite_commands() {
  cat <<'EOF'
If you have not done so, run these prerequisite commands separately:
  pip install uv
  apt-get install -y libopenblas-dev
  apt-get install gh nginx tmux

This script only prints those commands; it does not execute them.
EOF
}

usage() {
  cat <<EOF
Usage: sudo $0 --ssl-backup-dir BACKUP_DIR [--with-s6|--without-s6]

BACKUP_DIR can be either:
  - the backup directory created by backup-nginx-local-state.sh
  - a directory containing ssl/origin.pem and ssl/origin.key
  - a directory containing origin.pem and origin.key directly

Copies nginx configs from this repo into /etc/nginx, restores the
machine-local SSL certificate/key from BACKUP_DIR, creates required runtime
directories, chowns them to $NGINX_USER, optionally configures s6-supervise,
and runs nginx -t.

This script does not install nginx and does not start or reload nginx.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

print_prerequisite_commands
echo

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --ssl-backup-dir)
      if [[ $# -lt 2 ]]; then
        echo "--ssl-backup-dir requires a path." >&2
        exit 2
      fi
      SSL_BACKUP_DIR="$2"
      shift 2
      ;;
    --with-s6)
      CONFIGURE_S6="yes"
      shift
      ;;
    --without-s6)
      CONFIGURE_S6="no"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$SSL_BACKUP_DIR" ]]; then
  echo "Missing required --ssl-backup-dir BACKUP_DIR." >&2
  usage >&2
  exit 2
fi

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (use sudo)." >&2
  exit 1
fi

if ! command -v nginx >/dev/null 2>&1; then
  echo "nginx is not installed. Install nginx separately, then rerun this script." >&2
  exit 1
fi

if ! id "$NGINX_USER" >/dev/null 2>&1; then
  echo "Required nginx user does not exist: $NGINX_USER" >&2
  echo "Create the user or install nginx separately so the package creates it." >&2
  exit 1
fi

if [[ ! -d "$NGINX_CONF_SRC" ]]; then
  echo "Expected nginx configs at $NGINX_CONF_SRC but directory is missing." >&2
  exit 1
fi

find_ssl_file() {
  local name="$1"
  if [[ -f "$SSL_BACKUP_DIR/ssl/$name" ]]; then
    echo "$SSL_BACKUP_DIR/ssl/$name"
  elif [[ -f "$SSL_BACKUP_DIR/$name" ]]; then
    echo "$SSL_BACKUP_DIR/$name"
  else
    return 1
  fi
}

ORIGIN_PEM="$(find_ssl_file origin.pem || true)"
ORIGIN_KEY="$(find_ssl_file origin.key || true)"

if [[ -z "$ORIGIN_PEM" || -z "$ORIGIN_KEY" ]]; then
  echo "Missing required SSL files in backup directory: $SSL_BACKUP_DIR" >&2
  echo "Expected origin.pem and origin.key either directly inside that directory or inside its ssl/ subdirectory." >&2
  exit 1
fi

if [[ -z "$CONFIGURE_S6" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Configure s6-supervise service files for nginx? [y/N] " answer
    case "$answer" in
      y|Y|yes|YES)
        CONFIGURE_S6="yes"
        ;;
      *)
        CONFIGURE_S6="no"
        ;;
    esac
  else
    CONFIGURE_S6="no"
    echo "No TTY available; skipping optional s6 setup. Pass --with-s6 to configure it."
  fi
fi

echo "==> Copying nginx configs"
install -d -m 0755 /etc/nginx /etc/nginx/conf.d
install -m 0644 "$NGINX_CONF_SRC/nginx.conf" /etc/nginx/nginx.conf
install -d -m 0755 /etc/nginx/sites-available /etc/nginx/sites-enabled
install -m 0644 "$NGINX_CONF_SRC/sites-available/default" /etc/nginx/sites-available/default
install -m 0644 "$NGINX_CONF_SRC/sites-available/suvani.xyz.conf" /etc/nginx/sites-available/suvani.xyz.conf

echo "==> Enabling sites"
ln -sfn /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
ln -sfn /etc/nginx/sites-available/suvani.xyz.conf /etc/nginx/sites-enabled/suvani.xyz.conf

echo "==> Creating runtime directories"
install -d -m 0755 /etc/nginx/ssl
install -d -m 0755 /run/nginx
install -d -m 0755 /run/nginx/client_body_temp
install -d -m 0755 /run/nginx/proxy_temp
install -d -m 0755 /run/nginx/fastcgi_temp
install -d -m 0755 /run/nginx/uwsgi_temp
install -d -m 0755 /var/run/nginx
install -d -m 0755 /var/run/nginx/client_body_temp
install -d -m 0755 /var/lib/nginx
install -d -m 0755 /var/log/nginx

echo "==> Restoring SSL certificate and key"
install -o "$NGINX_USER" -g "$NGINX_USER" -m 0644 "$ORIGIN_PEM" /etc/nginx/ssl/origin.pem
install -o "$NGINX_USER" -g "$NGINX_USER" -m 0600 "$ORIGIN_KEY" /etc/nginx/ssl/origin.key

echo "==> Setting ownership to $NGINX_USER:$NGINX_USER"
for dir in /etc/nginx/ssl /var/run/nginx /run/nginx /var/lib/nginx /var/log/nginx; do
  chown -R "$NGINX_USER:$NGINX_USER" "$dir"
done

echo "==> Ensuring app roots are readable by nginx when present"
for dir in \
  /home/jovyan/voice_assist/prod/root/app/xyz \
  /home/jovyan/voice_assist/prod/app/xyz \
  /home/jovyan/voice_assist/beta/app/xyz \
  /home/jovyan/voice_assist/test/app/xyz; do
  if [[ -d "$dir" ]]; then
    chmod -R o+rX "$dir"
  fi
done

if [[ "$CONFIGURE_S6" == "yes" ]]; then
  if [[ ! -d "$S6_SRC" ]]; then
    echo "Expected s6 configs at $S6_SRC but directory is missing." >&2
    exit 1
  fi

  echo "==> Configuring optional s6 service files"
  install -d -m 0755 /etc/services.d/nginx
  cp -a "$S6_SRC/." /etc/services.d/nginx/
  chmod +x /etc/services.d/nginx/run /etc/services.d/nginx/log/run
fi

echo "==> Validating nginx configuration"
nginx -t

if [[ "$CONFIGURE_S6" == "yes" ]]; then
  cat <<EOF

==============================================================
 nginx configuration is valid.

 s6 was configured. Start/reload manually:
   s6-svc -u /etc/services.d/nginx   # start
   s6-svc -r /etc/services.d/nginx   # restart
   s6-svstat /etc/services.d/nginx   # status
==============================================================
EOF
else
  cat <<EOF

==============================================================
 nginx configuration is valid.

 s6 was not configured. Start/reload manually:
   nginx             # if not running
   nginx -s reload   # if already running
==============================================================
EOF
fi
