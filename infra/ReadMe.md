# Nginx with s6-supervise Setup

## Initial Setup
## Primarily set up for E2E server, which seems to have s6 config but running s6-supervise for service.d

1. Create necessary directories:
   ```bash
   sudo mkdir -p /etc/services.d/nginx/log
   sudo mkdir -p /etc/nginx/conf.d
   mkdir -p /etc/services.d/nginx
   ```

2. Copy s6 service files:
   ```bash
   sudo cp -r infra/s6-nginx/* /etc/services.d/nginx
   sudo chmod +x /etc/services.d/nginx/run /etc/services.d/nginx/log/run
   ```

3. Create and set permissions for Nginx directories:
   ```bash
   # Runtime directory
   sudo mkdir -p /var/run/nginx/client_body_temp
   sudo chown -R www-data:www-data /var/run/nginx
   sudo chown -R www-data:www-data /var/run/nginx/client_body_temp
   sudo chown -R www-data:www-data /var/lib/nginx
   sudo chown -R www-data:www-data /var/log/nginx
   # Ensure Nginx can read its configuration
   sudo chmod -R o+r /etc/nginx
   
   # Set web root permissions (adjust /var/www if using a different directory)
   sudo chmod -R o+r /home/jovyan/voice_assist/prod/web/
   ```

4. Copy Nginx configuration:
   ```bash
   sudo cp infra/nginx-conf/nginx.conf /etc/nginx/nginx.conf
   ```

5. Allow Nginx to bind to privileged ports (80/443):
   ```bash
   sudo setcap 'cap_net_bind_service=+ep' /usr/sbin/nginx
   ```
   Note: You'll need to re-run this if you update Nginx.

6. Set up nginx to pick up our infrastructure files:
   ```bash
   sudo cp infra/nginx-conf/sites-available/* /etc/nginx/sites-available/
   sudo ln -s /etc/nginx/sites-available/suvani.xyz.conf /etc/nginx/sites-enabled/suvani.xyz.conf
   ```

7. Set up certificate:
 get the actual certificate from the gdrive and place it in the ssl directory
   ```bash
   sudo mkdir -p /etc/nginx/ssl
   sudo chown -R www-data:www-data /etc/nginx/ssl

   ```

## Starting the Service

1. Start s6-supervise for Nginx:
   ```bash
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

## Prerequisites

- The `ngx_http_realip_module` is required for Cloudflare real IP restoration (`set_real_ip_from` / `real_ip_header` directives). Verify it's available:
  ```bash
  nginx -V 2>&1 | grep realip
  ```
  It's included by default in most distributions. If missing, you'll need to recompile Nginx with `--with-http_realip_module`.