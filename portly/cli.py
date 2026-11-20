"""Portly Command Line Interface."""

import argparse
import json
import os
import socket
import sys
import webbrowser
import uvicorn

from portly.backend import auth
from portly.backend.discovery.merge import merge_discovered_apps
from portly.backend.ports import check_port_availability, suggest_free_ports
from portly.backend.store import Store


def _display_host(host: str) -> str:
    """Resolve wildcard bind addresses to a URL a user can actually open."""
    if host not in ("0.0.0.0", "::"):
        return host
    try:
        # UDP connect picks a route without sending a packet.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
        if ip and ip != "0.0.0.0":
            return ip
    except OSError:
        pass
    return "localhost"


def main():
    parser = argparse.ArgumentParser(prog="portly", description="Portly CLI: Port & Container Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # run command
    run_parser = subparsers.add_parser("run", help="Run the Portly web dashboard")
    run_parser.add_argument("--host", default=os.getenv("PORTLY_HOST", "127.0.0.1"), help="Host to bind (default: 127.0.0.1)")
    run_parser.add_argument("--port", type=int, default=int(os.getenv("PORTLY_PORT", 5533)), help="Port to bind (default: 5533)")
    run_parser.add_argument("--mode", default=os.getenv("PORTLY_MODE", "desktop"), choices=["desktop", "server"], help="Mode: desktop or server")

    # list command
    list_parser = subparsers.add_parser("list", help="List discovered ports and containers")
    list_parser.add_argument("--docker", action="store_true", help="Only show Docker containers")
    list_parser.add_argument("--host-only", action="store_true", help="Only show host processes")
    list_parser.add_argument("--json", action="store_true", help="Output raw JSON")

    # start command
    start_parser = subparsers.add_parser("start", help="Start an app by name or ID")
    start_parser.add_argument("app", help="App name or ID")

    # stop command
    stop_parser = subparsers.add_parser("stop", help="Stop an app by name or ID")
    stop_parser.add_argument("app", help="App name or ID")

    # open command
    open_parser = subparsers.add_parser("open", help="Open an app URL in the default web browser")
    open_parser.add_argument("app", help="App name or ID")

    # check-port command
    check_port_parser = subparsers.add_parser("check-port", help="Check if a specific port is available")
    check_port_parser.add_argument("port", type=int, help="Port number to check")
    check_port_parser.add_argument("--bind", default="0.0.0.0", help="Bind IP to check (default: 0.0.0.0)")

    # suggest command
    suggest_parser = subparsers.add_parser("suggest", help="Suggest free ports")
    suggest_parser.add_argument("--start", type=int, default=3000, help="Starting port (default: 3000)")
    suggest_parser.add_argument("--count", type=int, default=5, help="Number of ports to suggest (default: 5)")
    suggest_parser.add_argument("--bind", default="0.0.0.0", help="Bind IP to check (default: 0.0.0.0)")

    # logs command
    logs_parser = subparsers.add_parser("logs", help="Fetch logs for a container or custom app")
    logs_parser.add_argument("app", help="App name or ID")
    logs_parser.add_argument("--tail", type=int, default=100, help="Number of lines to show (default: 100)")

    # reset-setup-token command
    subparsers.add_parser("reset-setup-token", help="Generate a new admin setup token (invalidates the previous one)")

    args = parser.parse_args()

    if not args.command or args.command == "run":
        host = getattr(args, "host", os.getenv("PORTLY_HOST", "127.0.0.1"))
        port = getattr(args, "port", int(os.getenv("PORTLY_PORT", 5533)))
        mode = getattr(args, "mode", os.getenv("PORTLY_MODE", "desktop"))

        store = Store()

        # Security check: Refuse to start on non-loopback (0.0.0.0 or LAN) without auth setup if server mode requires it
        if host in ("0.0.0.0", "::") and mode != "server" and store.get_user_count() == 0:
            if os.getenv("PORTLY_ALLOW_INSECURE_BIND", "").lower() not in ("true", "1"):
                print("SECURITY ERROR: Binding to 0.0.0.0 requires authentication. Run with --mode server and set up an admin account or bind to 127.0.0.1.", file=sys.stderr)
                sys.exit(1)

        # In server mode with no users, generate and display setup token
        if mode == "server" and store.get_user_count() == 0:
            setup_token = auth.get_setup_token()
            print("=" * 80, file=sys.stderr)
            print("⚓ PORTLY INITIAL ADMIN SETUP REQUIRED", file=sys.stderr)
            print(f"Setup Token: {setup_token}", file=sys.stderr)
            print(f"Complete setup at: http://{_display_host(host)}:{port}", file=sys.stderr)
            print("=" * 80, file=sys.stderr)

        # Propagate configuration to environment for FastAPI lifespan and auth checks
        os.environ["PORTLY_HOST"] = str(host)
        os.environ["PORTLY_PORT"] = str(port)
        os.environ["PORTLY_MODE"] = str(mode)

        print(f"Starting Portly dashboard on http://{_display_host(host)}:{port} (Mode: {mode})")
        import logging
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        uvicorn.run("portly.backend.app:app", host=host, port=port, log_level="info")

    elif args.command == "reset-setup-token":
        if os.environ.get("PORTLY_SETUP_TOKEN", "").strip():
            print("PORTLY_SETUP_TOKEN is set; remove it to reset the setup token.", file=sys.stderr)
            sys.exit(1)
        token = auth.get_setup_token()
        print("=" * 80, file=sys.stderr)
        print("⚓ PORTLY SETUP TOKEN (regenerated)", file=sys.stderr)
        print(f"Setup Token: {token}", file=sys.stderr)
        print("=" * 80, file=sys.stderr)

    elif args.command == "list":
        store = Store()
        apps, conflicts = merge_discovered_apps(store)
        if args.docker:
            apps = [a for a in apps if a.get("source") == "docker"]
        elif args.host_only:
            apps = [a for a in apps if a.get("source") == "host"]

        if args.json:
            print(json.dumps({"apps": apps, "conflicts": conflicts}, indent=2))
        else:
            print(f"{'PORT':<8} {'NAME':<24} {'SOURCE':<10} {'BIND':<15} {'STATUS':<10} {'CATEGORY'}")
            print("-" * 80)
            for a in apps:
                port_str = f":{a['port']}"
                print(f"{port_str:<8} {a['name'][:23]:<24} {a['source']:<10} {a['bind']:<15} {a['status']:<10} {a['category_id']}")

    elif args.command in ("start", "stop"):
        store = Store()
        from portly.backend.actions import docker_actions, process_actions
        app_target = args.app
        apps, _ = merge_discovered_apps(store)
        target = None
        for a in apps:
            if a["id"] == app_target or a["name"].lower() == app_target.lower():
                target = a
                break

        if not target:
            print(f"Error: App '{app_target}' not found.", file=sys.stderr)
            sys.exit(1)

        try:
            if args.command == "start":
                if target["source"] == "docker":
                    res = docker_actions.start_container(target.get("container_name", ""), store)
                else:
                    res = process_actions.start_custom_app(target["id"], store)
                print(f"Success: {res}")
            else:
                if target["source"] == "docker":
                    res = docker_actions.stop_container(target.get("container_name", ""), store)
                else:
                    res = process_actions.stop_custom_app(target["id"], store)
                print(f"Success: {res}")
        except Exception as e:
            print(f"Failed: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "open":
        store = Store()
        apps, _ = merge_discovered_apps(store)
        app_target = args.app
        target = None
        for a in apps:
            if a["id"] == app_target or a["name"].lower() == app_target.lower():
                target = a
                break

        if not target:
            print(f"Error: App '{app_target}' not found.", file=sys.stderr)
            sys.exit(1)

        url = target.get("open_url") or target.get("url")
        if not url:
            port = target.get("port")
            if port and port > 0:
                bind = target.get("bind", "127.0.0.1")
                host = "127.0.0.1" if bind in ("0.0.0.0", "::", "") else bind
                url = f"http://{host}:{port}"

        if not url:
            print(f"Error: App '{app_target}' does not have an active URL or port.", file=sys.stderr)
            sys.exit(1)

        print(f"Opening {target['name']} at {url}...")
        webbrowser.open(url)

    elif args.command == "check-port":
        res = check_port_availability(args.port, args.bind, store=Store())
        is_free = res.get("free", res.get("available", False))
        print(f"Port {args.port} ({args.bind}): {'AVAILABLE' if is_free else 'OCCUPIED'}")
        if not is_free and res.get("used_by"):
            print(f"  Reason: {res.get('used_by')}")

    elif args.command == "suggest":
        ports = suggest_free_ports(start_port=args.start, count=args.count, bind_ip=args.bind, store=Store())
        print(f"Suggested free ports starting from {args.start} ({args.bind}):")
        for p in ports:
            print(f"  - {p}")

    elif args.command == "logs":
        store = Store()
        from portly.backend.actions import docker_actions, process_actions
        app_target = args.app
        apps, _ = merge_discovered_apps(store)
        target = None
        for a in apps:
            if a["id"] == app_target or a["name"].lower() == app_target.lower():
                target = a
                break

        if not target:
            # Maybe direct container name or custom id
            if app_target.startswith("docker:"):
                target = {"source": "docker", "container_name": app_target.split(":")[1]}
            elif app_target.startswith("custom:"):
                target = {"source": "custom", "id": app_target}
            else:
                target = {"source": "docker", "container_name": app_target}

        if target.get("source") == "docker":
            lines = docker_actions.get_container_logs(target.get("container_name", ""), tail=args.tail)
        elif target.get("source") == "custom":
            lines = process_actions.get_custom_app_logs(target.get("id", ""), store, tail=args.tail)
        else:
            print(f"Direct log capture not supported for host process '{app_target}'.", file=sys.stderr)
            sys.exit(1)

        for line in lines:
            print(line)


if __name__ == "__main__":
    main()
