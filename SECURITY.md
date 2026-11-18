# Security Policy 🛡️

## Security Architecture

Portly manages network sockets, host processes, and Docker container configurations. Security is designed into every layer:

### 1. Safe Mode by Default
- Mutating actions (stopping/starting services, killing processes, remapping ports, recreating containers, pruning storage) are strictly locked by default.
- Safe mode must be unlocked with explicit user intent.
- Auto-relock timer defaults to 5 minutes to prevent lingering administrative access.
- Safe mode checks are enforced on the backend regardless of frontend state.

### 2. Network & Authentication Boundaries
- When binding to loopback (`127.0.0.1`), Portly assumes single-user desktop access.
- When binding to public interfaces (`0.0.0.0`) or launched with `PORTLY_MODE=server`, Portly requires an administrative setup token generated at startup and outputted to `stderr`.
- Password authentication uses PBKDF2-HMAC-SHA256 with timing-safe verification (`hmac.compare_digest`) and dummy hash execution on non-existent users to prevent timing side-channel attacks.
- Login attempts are rate-limited to 5 failures per 15-minute window per IP/username.
- Session tokens are stored in the database as SHA-256 hashes; raw tokens are never persisted.
- Passwords must meet a minimum strength requirement of 10 characters.

### 3. Cross-Site Request Forgery (CSRF) & Origin Protection
- All state-changing endpoints (`POST`, `PATCH`, `DELETE`, `PUT`) validate the presence of the `X-Portly-Client: 1` header.
- CORS policies prohibit wildcards with credentials.
- Strict security response headers are injected: `Content-Security-Policy`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.

### 4. Command Injection & Execution Boundaries
- Docker container `exec` endpoints enforce a strict allowlist of read-only diagnostic commands (`ps`, `df`, `free`, `top`, `uptime`, `uname`, `whoami`, `id`, `hostname`, `date`, `pwd`, `ss`, `netstat`, `ip`, `ls`, `env`, `cat`).
- Shell chaining operators (`;`, `&&`, `||`, `|`, `>`, `<`, `` ` ``, `$()`, `\n`) are unconditionally rejected.
- Execution output is strictly truncated at 256 KB to prevent memory exhaustion and buffer overflows.

### 5. Server-Side Request Forgery (SSRF) Safeguards
- Health check probes, webhook deliveries, and favicon fetchers validate target IP addresses.
- Cloud metadata services (`169.254.169.254`, `fd00:ec2::254`), link-local IPs, multicast ranges, and broadcast addresses are unconditionally blocked.
- SVG favicons are sanitized to strip `<script>` tags, inline event handlers (`onload`, `onerror`), and `javascript:` URIs.

### 6. Process & Path Isolation
- Log reading validates paths against an allowlist of directories (`tempfile.gettempdir()`, Portly data directory, and the app's declared working directory).
- Traversals (`..`) and sensitive system files (`/etc/passwd`, `C:\Windows\System32\config\SAM`, `.bash_history`) are blocked.
- Critical processes (PID 0, 1, 4, Portly's own PID, `systemd`, `csrss.exe`, `lsass.exe`, `services.exe`) cannot be terminated.

### 7. Docker Deployment Privileges
The default `docker-compose.yml` intentionally requests broad host access. Understand it before deploying:

- **The Docker socket is root-equivalent, even when mounted `:ro`.** The `:ro` flag makes the socket *file* read-only; it does not restrict the Docker API reachable through it, which can create privileged containers and mount host paths. Treat container access as host-root access.
- **`network_mode: host` and `pid: host`** remove network and process namespace isolation. They are required to discover host sockets and processes.
- **`/:/hostfs:ro`** exposes the whole host filesystem read-only so disk stats reflect the host rather than container overlay storage. `:ro` limits writes but not visibility of sensitive files.
- **Lower-privilege option:** use a `docker-socket-proxy` (see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)). Read-only proxy endpoints support monitoring only; enabling Portly's start/stop/recreate actions requires write access, which restores the root-equivalent risk.
- Bind to `127.0.0.1` or place Portly behind authentication and a reverse proxy; do not expose it directly to untrusted networks.

---

## Reporting a Vulnerability

If you discover a security vulnerability in Portly, please send a report to the maintainers rather than opening a public issue.

- **Email**: `security@seaxen.dev`
- **Response Time**: Within 48 hours.
- **Disclosure Policy**: Coordinated disclosure after a fix is verified and released.
