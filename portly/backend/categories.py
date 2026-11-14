"""Categories and rules engine for Portly."""

import re
from typing import Any, Dict, List, Optional


def match_rule(app: Dict[str, Any], rule: Dict[str, Any]) -> bool:
    """Checks if an app matches a single rule."""
    field = rule.get("field", "").lower()
    op = rule.get("operator", "contains").lower()
    rule_val = str(rule.get("value", "")).strip().lower()

    target_val = ""
    if field == "image":
        target_val = str(app.get("image", "")).lower()
    elif field == "process":
        target_val = str(app.get("process_name", "") or app.get("name", "")).lower()
    elif field == "cmdline":
        target_val = str(app.get("cmdline", "")).lower()
    elif field == "compose_project":
        target_val = str(app.get("compose_project", "")).lower()
    elif field == "port":
        port = app.get("port")
        if port is None:
            return False
        if op == "range":
            # e.g. "3000-3999"
            if "-" in rule_val:
                try:
                    start_str, end_str = rule_val.split("-", 1)
                    start_port = int(start_str.strip())
                    end_port = int(end_str.strip())
                    return start_port <= int(port) <= end_port
                except ValueError:
                    return False
            return False
        elif op == "equals":
            try:
                return int(port) == int(rule_val)
            except ValueError:
                return False
        elif op == "contains":
            return rule_val in str(port)
        return False
    elif field == "label":
        labels = app.get("labels") or {}
        for k, v in labels.items():
            if rule_val in str(k).lower() or rule_val in str(v).lower():
                return True
        return False
    else:
        target_val = str(app.get(field, "")).lower()

    if op == "contains":
        return rule_val in target_val
    elif op == "equals":
        return rule_val == target_val
    elif op == "startswith":
        return target_val.startswith(rule_val)
    elif op == "regex":
        try:
            return bool(re.search(rule_val, target_val, re.IGNORECASE))
        except re.error:
            return False

    return False


def categorize_app(app: Dict[str, Any], rules: List[Dict[str, Any]]) -> str:
    """Matches app against ordered rules and returns category_id or 'uncategorized'."""
    # Check docker label override first
    if app.get("label_category"):
        return app["label_category"]

    for rule in sorted(rules, key=lambda r: r.get("priority", 10)):
        if match_rule(app, rule):
            return rule.get("category_id", "uncategorized")

    return "uncategorized"


def preview_rule_matches(rule: Dict[str, Any], apps: List[Dict[str, Any]]) -> List[str]:
    """Returns list of app IDs matching the rule for live preview."""
    matched_ids = []
    for app in apps:
        if match_rule(app, rule):
            matched_ids.append(app.get("id", ""))
    return matched_ids
