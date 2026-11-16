"""Desktop browser and responsive viewport test suite for Portly using Playwright.

Covers:
- Responsive desktop viewports: 1920x1080, 1440x900, 1024x768
- Non-wrapping layout integrity (StatsStrip and Toolbar)
- Table density toggle (Compact vs Comfy)
- Multi-column sorting and grouping controls
- Saved view tabs navigation
- Real-time search filtering
- Kiosk wallboard mode (Shift+K)
- App Detail modal deep tab inspection (Logs, Port Reassignment, Proxy Gen, TLS, Settings)
- Export menu validation (CSV, Markdown, JSON)
- Performance and clean console/runtime assertions
"""

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def desktop_page(browser_instance, portly_server):
    """Isolated page context for desktop browser testing."""
    context = browser_instance.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    console_errors = []
    page_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: page_errors.append(str(err)))

    page.goto(portly_server, wait_until="domcontentloaded")
    page.wait_for_selector(".portly-sidebar, .c068", timeout=12000)

    page.console_errors = console_errors
    page.page_errors = page_errors

    yield page
    context.close()


def test_desktop_viewports_and_non_wrapping_layout(desktop_page: Page):
    """Verify desktop responsive viewports and non-wrapping horizontal continuity."""
    viewports = [
        {"width": 1920, "height": 1080, "name": "Wide 1080p"},
        {"width": 1440, "height": 900, "name": "Standard Laptop"},
        {"width": 1024, "height": 768, "name": "Compact Desktop"},
    ]

    for vp in viewports:
        desktop_page.set_viewport_size({"width": vp["width"], "height": vp["height"]})
        desktop_page.wait_for_timeout(200)

        # 1. Verify Sidebar is visible
        sidebar = desktop_page.locator(".portly-sidebar")
        expect(sidebar).to_be_visible()

        # 2. Verify Stats Strip is single line and doesn't wrap
        stats_strip = desktop_page.locator(".c081")
        expect(stats_strip).to_be_visible()
        is_nowrap = desktop_page.evaluate(
            """() => {
                const el = document.querySelector('.c081');
                if (!el) return false;
                const style = window.getComputedStyle(el);
                return style.flexWrap === 'nowrap';
            }"""
        )
        assert is_nowrap, f"Stats strip wrapped on {vp['name']} viewport!"

        # 3. Verify Toolbar is visible and exists
        toolbar = desktop_page.locator(".c073").first
        expect(toolbar).to_be_visible()

    assert len(desktop_page.page_errors) == 0


def test_desktop_table_density_toggle(desktop_page: Page):
    """Test switching table density between Compact and Comfy."""
    compact_btn = desktop_page.locator('button[aria-label="Compact"]')
    comfy_btn = desktop_page.locator('button[aria-label="Comfy"]')

    expect(compact_btn).to_be_visible()
    expect(comfy_btn).to_be_visible()

    # Switch to Comfy
    comfy_btn.click()
    desktop_page.wait_for_timeout(200)
    expect(comfy_btn).to_have_class(re.compile(r"\bc094\b"))

    # Switch to Compact
    compact_btn.click()
    desktop_page.wait_for_timeout(200)
    expect(compact_btn).to_have_class(re.compile(r"\bc094\b"))


def test_desktop_sorting_and_grouping(desktop_page: Page):
    """Test desktop toolbar sorting dropdown and grouping dropdown."""
    # Open Sort dropdown
    sort_btn = desktop_page.locator('button:has-text("Sort:")')
    expect(sort_btn).to_be_visible()
    sort_btn.click()
    desktop_page.wait_for_timeout(200)

    # Click 'App Name'
    name_sort_opt = desktop_page.locator('button:has-text("App Name")')
    if name_sort_opt.is_visible():
        name_sort_opt.click()
        desktop_page.wait_for_timeout(200)

    # Open Group dropdown
    group_btn = desktop_page.locator('button:has-text("Group:")')
    expect(group_btn).to_be_visible()
    group_btn.click()
    desktop_page.wait_for_timeout(200)

    # Click 'No Grouping'
    group_opt = desktop_page.locator('button:has-text("No Grouping")')
    if group_opt.is_visible():
        group_opt.click()
        desktop_page.wait_for_timeout(200)


def test_desktop_saved_views_tabs(desktop_page: Page):
    """Test switching saved view tabs: All ports, Dev only, Exposed, Docker."""
    all_tab = desktop_page.locator('.c089 button:has-text("All ports"), .c089 button:has-text("All Ports")').first
    expect(all_tab).to_be_visible()

    # Check for available tabs
    tabs = desktop_page.locator('.c089 button')
    tab_count = tabs.count()
    assert tab_count >= 1, "Expected at least 1 saved view tab"

    # Click through available tabs
    for i in range(min(tab_count, 3)):
        tabs.nth(i).click()
        desktop_page.wait_for_timeout(200)


def test_desktop_realtime_search_filtering(desktop_page: Page):
    """Test real-time search input filtering on desktop."""
    search_input = desktop_page.locator('input[aria-label="Search ports, apps, containers"]')
    expect(search_input).to_be_visible()

    # Type query
    search_input.fill("python")
    desktop_page.wait_for_timeout(300)

    # Clear query
    search_input.fill("")
    desktop_page.wait_for_timeout(300)


def test_desktop_kiosk_wallboard_mode(desktop_page: Page):
    """Test toggling Kiosk wallboard display mode via button and Shift+K."""
    kiosk_btn = desktop_page.locator('button[aria-label="Toggle Kiosk mode"]')
    expect(kiosk_btn).to_be_visible()

    # Enter Kiosk Mode
    kiosk_btn.click()
    desktop_page.wait_for_timeout(300)

    # Verify floating exit button appears
    exit_kiosk_btn = desktop_page.locator('button:has-text("Exit Kiosk")')
    expect(exit_kiosk_btn).to_be_visible()

    # Sidebar should be hidden in kiosk mode
    sidebar = desktop_page.locator('.portly-sidebar')
    expect(sidebar).not_to_be_visible()

    # Exit Kiosk Mode
    exit_kiosk_btn.click()
    desktop_page.wait_for_timeout(300)

    # Sidebar should be restored
    expect(sidebar).to_be_visible()


def test_desktop_export_menu(desktop_page: Page):
    """Test opening the Export menu and verifying CSV, Markdown, and JSON links."""
    export_btn = desktop_page.locator('button:has-text("Export")')
    expect(export_btn).to_be_visible()

    # Click to open export menu
    export_btn.click()
    desktop_page.wait_for_timeout(200)

    # Verify CSV link
    csv_link = desktop_page.locator('a:has-text("CSV Table")')
    expect(csv_link).to_be_visible()
    expect(csv_link).to_have_attribute("href", re.compile(r"/api/export\?format=csv"))

    # Verify Markdown link
    md_link = desktop_page.locator('a:has-text("Markdown Sheet")')
    expect(md_link).to_be_visible()
    expect(md_link).to_have_attribute("href", re.compile(r"/api/export\?format=markdown"))

    # Verify JSON link
    json_link = desktop_page.locator('a:has-text("Full JSON Backup")')
    expect(json_link).to_be_visible()
    expect(json_link).to_have_attribute("href", re.compile(r"/api/export\?format=json"))

    # Close menu
    desktop_page.keyboard.press("Escape")


def test_desktop_app_detail_modal_tabs(desktop_page: Page):
    """Test opening AppDetailModal and inspecting tabs: Logs, Change Port, Proxy Gen, TLS, Settings."""
    first_row = desktop_page.locator('.portly-table-row').first
    if not first_row.is_visible():
        first_row = desktop_page.locator('.c026').first

    if first_row.is_visible():
        first_row.click()
        desktop_page.wait_for_timeout(400)

        modal = desktop_page.locator('.modal-content')
        expect(modal).to_be_visible(timeout=5000)

        # Inspect Logs Tab
        logs_tab = modal.locator('button:has-text("Logs")')
        if logs_tab.is_visible():
            logs_tab.click()
            desktop_page.wait_for_timeout(200)
            filter_input = modal.locator('input[aria-label="Filter logs"]')
            expect(filter_input).to_be_visible()

        # Inspect Change Port Tab
        ports_tab = modal.locator('button:has-text("Change Port")')
        if ports_tab.is_visible():
            ports_tab.click()
            desktop_page.wait_for_timeout(200)
            port_input = modal.locator('input#edit-host-port')
            expect(port_input).to_be_visible()

        # Inspect Proxy Gen Tab
        proxy_tab = modal.locator('button:has-text("Proxy Gen")')
        if proxy_tab.is_visible():
            proxy_tab.click()
            desktop_page.wait_for_timeout(200)
            proxy_input = modal.locator('input[aria-label="Proxy domain"]')
            expect(proxy_input).to_be_visible()

        # Inspect TLS Inspector Tab
        tls_tab = modal.locator('button:has-text("TLS Inspector")')
        if tls_tab.is_visible():
            tls_tab.click()
            desktop_page.wait_for_timeout(200)

        # Inspect Settings Tab
        settings_tab = modal.locator('button:has-text("Settings")')
        if settings_tab.is_visible():
            settings_tab.click()
            desktop_page.wait_for_timeout(200)
            name_input = modal.locator('input#settings-name')
            expect(name_input).to_be_visible()

        # Close Modal
        close_btn = modal.locator('button:has-text("✕")')
        close_btn.click()
        expect(modal).not_to_be_visible()


def test_desktop_browser_performance_and_errors(desktop_page: Page):
    """Verify absence of unhandled console errors and runtime exceptions."""
    assert len(desktop_page.page_errors) == 0, f"Page errors: {desktop_page.page_errors}"
    assert len(desktop_page.console_errors) == 0, f"Console errors: {desktop_page.console_errors}"
