# Nginx with s6-supervise Setup

## Initial Setup
## Primarily set up for E2E server, which seems to have s6 config but running s6-supervise for service.d

1. Create necessary directories:
   ```bash
   sudo mkdir -p /etc/services.d/nginx/log
   sudo mkdir -p /etc/nginx/conf.d
   ```

2. Copy s6 service files:
   ```bash
   sudo cp -r infra/s6-nginx/* /etc/services.d/nginx
   sudo chmod +x /etc/services.d/nginx/run /etc/services.d/nginx/log/run
   ```

3. Copy Nginx configuration:
   ```bash
   sudo cp infra/nginx-conf/nginx.conf /etc/nginx/nginx.conf
   ```

## Starting the Service

1. Start s6-supervise for Nginx:
   ```bash
   s6-svscan /etc/services.d &
   s6-svc -u /etc/services.d/nginx
   ```

2. Verify Nginx is running:
   ```bash
   ps aux | grep nginx
   curl -I http://localhost
   ```

## Logs

View Nginx logs:
```bash
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log
```

## Common Commands

- Restart Nginx: `s6-svc -r /etc/services.d/nginx`
- Stop Nginx: `s6-svc -d /etc/services.d/nginx`
- Check status: `s6-svstat /etc/services.d/nginx`