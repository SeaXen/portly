"""Tests for categories and rules engine."""

import pytest
from portly.backend.categories import categorize_app, match_rule, preview_rule_matches


def test_match_rule_port_range():
    rule = {"field": "port", "operator": "range", "value": "3000-3999", "category_id": "development"}
    assert match_rule({"port": 3000}, rule) is True
    assert match_rule({"port": 3500}, rule) is True
    assert match_rule({"port": 3999}, rule) is True
    assert match_rule({"port": 4000}, rule) is False
    assert match_rule({"port": None}, rule) is False
    assert match_rule({"port": 3000}, {"field": "port", "operator": "range", "value": "invalid"}) is False


def test_match_rule_port_equals_and_contains():
    assert match_rule({"port": 8080}, {"field": "port", "operator": "equals", "value": "8080"}) is True
    assert match_rule({"port": 8081}, {"field": "port", "operator": "equals", "value": "8080"}) is False
    assert match_rule({"port": 8080}, {"field": "port", "operator": "equals", "value": "bad_num"}) is False
    assert match_rule({"port": 8080}, {"field": "port", "operator": "contains", "value": "80"}) is True


def test_match_rule_image_contains():
    rule = {"field": "image", "operator": "contains", "value": "postgres", "category_id": "databases"}
    assert match_rule({"image": "postgres:16.4-alpine"}, rule) is True
    assert match_rule({"image": "redis:7"}, rule) is False


def test_match_rule_process():
    rule = {"field": "process", "operator": "contains", "value": "grafana", "category_id": "monitoring"}
    assert match_rule({"process_name": "grafana-server"}, rule) is True
    assert match_rule({"name": "grafana"}, rule) is True
    assert match_rule({"process_name": "node.exe"}, rule) is False


def test_match_rule_cmdline_and_compose():
    assert match_rule({"cmdline": "python -m uvicorn main:app"}, {"field": "cmdline", "operator": "contains", "value": "uvicorn"}) is True
    assert match_rule({"compose_project": "ecommerce"}, {"field": "compose_project", "operator": "equals", "value": "ecommerce"}) is True


def test_match_rule_labels():
    app = {"labels": {"tier": "backend", "team": "platform"}}
    assert match_rule(app, {"field": "label", "value": "backend"}) is True
    assert match_rule(app, {"field": "label", "value": "frontend"}) is False


def test_match_rule_operators():
    # startswith
    assert match_rule({"name": "postgres-primary"}, {"field": "name", "operator": "startswith", "value": "postgres"}) is True
    assert match_rule({"name": "replica-postgres"}, {"field": "name", "operator": "startswith", "value": "postgres"}) is False

    # regex
    assert match_rule({"name": "web-v2-prod"}, {"field": "name", "operator": "regex", "value": r"web-v\d+-prod"}) is True
    assert match_rule({"name": "web-alpha"}, {"field": "name", "operator": "regex", "value": r"web-v\d+-prod"}) is False
    assert match_rule({"name": "bad"}, {"field": "name", "operator": "regex", "value": r"[unclosed("}) is False


def test_category_priority():
    rules = [
        {"id": "r1", "category_id": "databases", "field": "image", "operator": "contains", "value": "postgres", "priority": 5},
        {"id": "r2", "category_id": "development", "field": "port", "operator": "range", "value": "5000-5999", "priority": 10},
    ]
    app = {"image": "postgres:16", "port": 5432}
    cat = categorize_app(app, rules)
    assert cat == "databases"

    # Docker label category override takes precedence over rules
    app_labeled = {"image": "postgres:16", "port": 5432, "label_category": "custom-infra"}
    assert categorize_app(app_labeled, rules) == "custom-infra"


def test_preview_rule_matches():
    rule = {"field": "port", "operator": "equals", "value": "8080", "category_id": "development"}
    apps = [{"id": "app1", "port": 8080}, {"id": "app2", "port": 3000}]
    matched = preview_rule_matches(rule, apps)
    assert matched == ["app1"]
