#!/usr/bin/env bash
# Provision nginx on a host from the configs tracked in this repo.
# Operates on whatever is currently checked out; does not touch git.
# Does not start nginx and does not write SSL material; operator does both.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NGINX_CONF_SRC="$SCRIPT_DIR/nginx-conf"

for arg in "$@"; do
  case "$arg" in
    -h|--help)
      cat <<EOF
Usage: sudo $0

Copies nginx configs from the repo into /etc/nginx, creates required
runtime directories, chowns them to www-data, and runs 'nginx -t'.
Does NOT place SSL certificates and does NOT start or reload nginx.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (use sudo)." >&2
  exit 1
fi

if [[ ! -d "$NGINX_CONF_SRC" ]]; then
  echo "Expected nginx configs at $NGINX_CONF_SRC but directory is missing." >&2
  exit 1
fi

echo "==> Copying nginx configs"
install -m 0644 "$NGINX_CONF_SRC/nginx.conf" /etc/nginx/nginx.conf
install -d -m 0755 /etc/nginx/sites-available /etc/nginx/sites-enabled
install -m 0644 "$NGINX_CONF_SRC/sites-available/default" /etc/nginx/sites-available/default
install -m 0644 "$NGINX_CONF_SRC/sites-available/suvani.xyz.conf" /etc/nginx/sites-available/suvani.xyz.conf

echo "==> Enabling sites"
ln -sfn /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
ln -sfn /etc/nginx/sites-available/suvani.xyz.conf /etc/nginx/sites-enabled/suvani.xyz.conf

echo "==> Creating runtime directories"
install -d -m 0755 /etc/nginx/ssl
install -d -m 0755 /run/nginx/client_body_temp
install -d -m 0755 /var/run/nginx/client_body_temp
install -d -m 0755 /etc/services.d/nginx/log

echo "==> Setting ownership to www-data:www-data"
for dir in /etc/nginx/ssl /var/run/nginx /run/nginx /var/lib/nginx /var/log/nginx; do
  if [[ -d "$dir" ]]; then
    chown -R www-data:www-data "$dir"
  else
    echo "   (skipping $dir — does not exist)"
  fi
done

echo "==> Validating nginx configuration"
nginx -t

cat <<'EOF'

==============================================================
 nginx configuration is valid.

 NEXT STEPS (manual):
   1. Place your SSL certificate and key at:
        /etc/nginx/ssl/origin.pem
        /etc/nginx/ssl/origin.key
      then:
        chown www-data:www-data /etc/nginx/ssl/origin.*
        chmod 600 /etc/nginx/ssl/origin.key

   2. Start or reload nginx yourself:
        nginx             # if not running
        nginx -s reload   # if already running
==============================================================
EOF
