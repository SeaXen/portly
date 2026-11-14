"""Portly Command Line Interface."""

import argparse
import json
import os
import sys
import uvicorn

from portly.backend.discovery.merge import merge_discovered_apps
from portly.backend.store import Store


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

    args = parser.parse_args()

    if not args.command or args.command == "run":
        host = getattr(args, "host", os.getenv("PORTLY_HOST", "127.0.0.1"))
        port = getattr(args, "port", int(os.getenv("PORTLY_PORT", 5533)))
        mode = getattr(args, "mode", os.getenv("PORTLY_MODE", "desktop"))

        # Security check: Refuse to start on non-loopback (0.0.0.0 or LAN) without auth setup if server mode requires it
        store = Store()
        if host in ("0.0.0.0", "::") and mode != "server" and store.get_user_count() == 0:
            # Check environment bypass or enforce
            if os.getenv("PORTLY_ALLOW_INSECURE_BIND", "").lower() not in ("true", "1"):
                print("SECURITY ERROR: Binding to 0.0.0.0 requires authentication. Run with --mode server and set up an admin account or bind to 127.0.0.1.", file=sys.stderr)
                sys.exit(1)

        print(f"Starting Portly dashboard on http://{host}:{port} (Mode: {mode})")
        uvicorn.run("portly.backend.app:app", host=host, port=port, log_level="info")

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
        # Search app
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


if __name__ == "__main__":
    main()
