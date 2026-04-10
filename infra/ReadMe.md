# Nginx with s6-supervise Setup

## Initial Setup
## Primarily set up for E2E server, which seems to have s6 config but running s6-supervise for service.d
apt-get update
apt-get install gh nginx tmux
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
   setcap 'cap_net_bind_service=+ep' /usr/sbin/nginx
   ```
   Note: You'll need to re-run this if you update Nginx.

6. Set up nginx to pick up our infrastructure files:
   ```bash
   sudo cp infra/nginx-conf/sites-available/* /etc/nginx/sites-available/
   sudo ln -s /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
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

---

## Standalone Nginx (without s6)

Run nginx directly from the command line instead of through s6-supervise.

### Nginx conf changes from s6 to standalone

1. **Add `user` directive** — s6 ran the entire process as `www-data` via `s6-setuidgid`. Standalone nginx runs master as root and drops privileges to the worker user:
   ```
   # Add at top of nginx.conf
   user www-data;
   ```

2. **Change PID path** — s6 used a custom `/var/run/nginx/` directory. Use the standard path:
   ```
   # Before (s6)
   pid /var/run/nginx/nginx.pid;

   # After (standalone)
   pid /run/nginx.pid;
   ```

3. **Remove temp path directives** — s6 needed custom temp paths under `/run/nginx/` because it ran as `www-data`. Standalone nginx uses its defaults under `/var/lib/nginx/`:
   ```
   # Remove these lines from nginx.conf
   client_body_temp_path /run/nginx/client_body_temp;
   proxy_temp_path /run/nginx/proxy_temp;
   fastcgi_temp_path /run/nginx/fastcgi_temp;
   uwsgi_temp_path /run/nginx/uwsgi_temp;
   ```

### Setup

1. Install nginx:
   ```bash
   sudo apt-get update && sudo apt-get install nginx
   ```

2. Copy nginx configuration:
   ```bash
   sudo cp infra/nginx-conf/nginx.conf /etc/nginx/nginx.conf
   sudo cp infra/nginx-conf/sites-available/* /etc/nginx/sites-available/
   sudo ln -sf /etc/nginx/sites-available/default /etc/nginx/sites-enabled/default
   sudo ln -sf /etc/nginx/sites-available/suvani.xyz.conf /etc/nginx/sites-enabled/suvani.xyz.conf
   ```

3. Set permissions:
   ```bash
   sudo chown -R www-data:www-data /var/lib/nginx
   sudo chown -R www-data:www-data /var/log/nginx
   sudo chmod -R o+r /etc/nginx
   sudo chmod -R o+r /home/jovyan/voice_assist/prod/web/
   ```

4. Set up SSL certificate:
   ```bash
   sudo mkdir -p /etc/nginx/ssl
   sudo chown -R www-data:www-data /etc/nginx/ssl
   ```
   Get the actual certificate from GDrive and place it in the ssl directory.

5. Test configuration:
   ```bash
   sudo nginx -t
   ```

### Running

```bash
# Start
sudo nginx

# Stop
sudo nginx -s stop

# Graceful reload (after config changes)
sudo nginx -s reload

# Test config without restarting
sudo nginx -t
```

### Verify

```bash
ps aux | grep nginx
curl -I http://localhost
```

### Logs

```bash
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log
```

---

## Prerequisites

- The `ngx_http_realip_module` is required for Cloudflare real IP restoration (`set_real_ip_from` / `real_ip_header` directives). Verify it's available:
  ```bash
  nginx -V 2>&1 | grep realip
  ```
  It's included by default in most distributions. If missing, you'll need to recompile Nginx with `--with-http_realip_module`.