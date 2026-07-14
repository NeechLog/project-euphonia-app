#!/usr/bin/env bash
# Back up machine-local nginx files that are intentionally not tracked in git.

set -euo pipefail

usage() {
  cat <<EOF
Usage: sudo $0 BACKUP_DIR

Backs up:
  /etc/nginx/ssl/origin.pem
  /etc/nginx/ssl/origin.key

The backup keeps file modes/ownership where cp -a supports it.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -ne 1 ]]; then
  usage >&2
  exit 2
fi

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (use sudo)." >&2
  exit 1
fi

BACKUP_ROOT="$1"
SSL_DIR="/etc/nginx/ssl"
REQUIRED_FILES=(
  "$SSL_DIR/origin.pem"
  "$SSL_DIR/origin.key"
)

for file in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Required file is missing: $file" >&2
    echo "Nothing was backed up. Place the file there first or choose another backup source." >&2
    exit 1
  fi
done

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_ROOT/nginx-local-state-$STAMP"

install -d -m 0700 "$DEST/ssl"

echo "==> Backing up nginx SSL files to $DEST"
cp -a "$SSL_DIR/origin.pem" "$DEST/ssl/origin.pem"
cp -a "$SSL_DIR/origin.key" "$DEST/ssl/origin.key"

cat > "$DEST/README.txt" <<EOF
Nginx local state backup
Created: $STAMP

Contains machine-local SSL files copied from:
  /etc/nginx/ssl/origin.pem
  /etc/nginx/ssl/origin.key

Restore manually or with a future restore script. Do not commit this backup to git.
EOF
chmod 0600 "$DEST/README.txt"

echo "Backup complete: $DEST"
