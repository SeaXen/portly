# Deployment & Production Guide ⚓

This guide covers deployment strategies for Portly on bare metal, virtual machines, home servers, and NAS appliances (Synology, TrueNAS, Unraid).

---

## 1. Docker Compose Deployment (Recommended)

Docker Compose is the standard production deployment method for Portly.

### Production `docker-compose.yml`

```yaml
version: '3.8'

services:
  portly:
    build: .
    image: portly:latest
    container_name: portly
    restart: unless-stopped
    network_mode: host
    pid: host
    group_add:
      - "${DOCKER_GID:-999}"
    environment:
      - PORTLY_HOST=0.0.0.0
      - PORTLY_PORT=5533
      - PORTLY_MODE=server
      - PORTLY_DATA_DIR=/app/data
      - PORTLY_HOSTFS=/hostfs
      - PORTLY_ALLOW_INSECURE_BIND=false
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./data:/app/data
      - /:/hostfs:ro
```

### Non-Root User & Docker Socket Permissions (`DOCKER_GID`)
Portly runs inside the container as the non-privileged user `portly` (UID/GID 1000/1000). On Linux hosts, `/var/run/docker.sock` is owned by `root:docker`.
To allow Portly to read Docker metrics without running as root, find your host's docker group GID:
```bash
getent group docker | cut -d: -f3
# e.g., 998 or 999
```
Then supply it in your `.env` or compose environment:
```bash
DOCKER_GID=998 docker compose up -d
```

### Hardened Socket Alternative (`docker-socket-proxy`)
If you prefer not to mount `/var/run/docker.sock` directly into Portly, you can deploy Portly alongside `tecnativa/docker-socket-proxy`, exposing only the read-only endpoints:
```yaml
services:
  docker-proxy:
    image: tecnativa/docker-socket-proxy:latest
    container_name: docker-proxy
    environment:
      - CONTAINERS=1
      - INFO=1
      - NETWORKS=1
      - POST=0
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    ports:
      - "127.0.0.1:2375:2375"
```
And point `DOCKER_HOST=tcp://127.0.0.1:2375` in Portly's environment.

### Why `network_mode: host`, `pid: host`, and `PORTLY_HOSTFS`?
- **Host Socket Discovery:** In bridge network mode, containers only see network namespaces isolated to that bridge. `network_mode: host` allows `psutil` and `netstat` to monitor the physical host's listening ports.
- **Process Inspection:** `pid: host` allows Portly to resolve process names, command lines, memory RSS, and CPU utilization for listening host processes.
- **Docker Socket Mount:** `/var/run/docker.sock` allows Portly to query the Docker Engine API and receive real-time container lifecycle events.
- **Host Filesystem Mount:** Mounts root filesystem at `/hostfs:ro` and sets `PORTLY_HOSTFS=/hostfs` so Portly can report accurate host disk utilization rather than overlay container storage.

---

## 2. Systemd Service (Linux Bare-Metal)

For running Portly as a background system service on Ubuntu, Debian, or Rocky Linux:

1. Clone and install dependencies into a dedicated virtual environment:
   ```bash
   sudo mkdir -p /opt/portly
   sudo git clone https://github.com/SeaXen/portly.git /opt/portly
   cd /opt/portly
   python3 -m venv venv
   ./venv/bin/pip install -r requirements.txt
   ```

2. Create `/etc/systemd/system/portly.service`:
   ```ini
   [Unit]
   Description=Portly Dashboard Service
   After=network.target docker.service
   Wants=docker.service

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/opt/portly
   ExecStart=/opt/portly/venv/bin/python -m portly run --port 5533 --host 0.0.0.0 --mode server
   Restart=always
   RestartSec=3
   Environment="PORTLY_DATA_DIR=/var/lib/portly"

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start:
   ```bash
   sudo mkdir -p /var/lib/portly
   sudo systemctl daemon-reload
   sudo systemctl enable --now portly
   ```

---

## 3. Reverse Proxy Configuration

When exposing Portly behind an edge reverse proxy:

### Caddy
```caddy
portly.yourdomain.com {
    reverse_proxy 127.0.0.1:5533
}
```

### Nginx
```nginx
server {
    listen 80;
    server_name portly.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5533;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Cloudflare Tunnel (`cloudflared`)
Add to your `~/.cloudflared/config.yml`:
```yaml
ingress:
  - hostname: portly.yourdomain.com
    service: http://127.0.0.1:5533
  - service: http_status:404
```

---

## 4. Security Checklist

- [ ] Run with `--mode server` when exposed beyond `localhost` (`127.0.0.1`).
- [ ] On first launch in server mode, copy the **Setup Token** printed to `stderr` and create the initial admin password.
- [ ] Keep **Safe Mode** enabled by default in settings to guard against accidental container termination.
- [ ] Set `PORTLY_CORS_ORIGINS` to trusted domains if accessing Portly via custom cross-origin web clients.
