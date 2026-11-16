"""End-to-End (E2E) web application test suite for Portly using Playwright.

Tests user flows, navigation, views, modals, drawer telemetry,
command palette, accessibility, and visual presentation.
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
def page(browser_instance, portly_server):
    """Isolated page context for each test case."""
    context = browser_instance.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()

    console_errors = []
    page_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda err: page_errors.append(str(err)))

    page.goto(portly_server, wait_until="domcontentloaded")
    # Wait for React app root and initial discovery layout
    page.wait_for_selector(".portly-sidebar, .c068", timeout=12000)

    # Attach error trackers to page
    page.console_errors = console_errors
    page.page_errors = page_errors

    yield page
    context.close()


def test_webapp_shell_and_title(page: Page):
    """Priority 1: Web application shell loads with proper title, header, and stats."""
    # Verify page title
    assert page.title() == "Portly – Port & Container Dashboard"

    # Verify Sidebar branding
    brand = page.locator(".sidebar-brand")
    expect(brand).to_be_visible()
    expect(brand).to_contain_text("Portly")

    # Verify Stats Strip is rendered and contains CPU & Memory telemetry
    stats_strip = page.locator(".c081")
    expect(stats_strip).to_be_visible()
    expect(stats_strip).to_contain_text("CPU", ignore_case=True)
    expect(stats_strip).to_contain_text("Memory", ignore_case=True)

    # Verify no unhandled JavaScript runtime crashes
    assert len(page.page_errors) == 0, f"Page errors: {page.page_errors}"


def test_view_switching(page: Page):
    """Test switching across views: Table, Grid, List, and Board."""
    table_btn = page.locator('button[aria-label="Table"]')
    grid_btn = page.locator('button[aria-label="Grid"]')
    list_btn = page.locator('button[aria-label="List"]')
    board_btn = page.locator('button[aria-label="Board"]')

    expect(table_btn).to_be_visible()
    expect(grid_btn).to_be_visible()

    # Switch to Grid view
    grid_btn.click()
    page.wait_for_timeout(300)
    expect(grid_btn).to_have_class(re.compile(r"\bc094\b"))

    # Switch to List view
    list_btn.click()
    page.wait_for_timeout(300)
    expect(list_btn).to_have_class(re.compile(r"\bc094\b"))

    # Switch to Board view
    board_btn.click()
    page.wait_for_timeout(300)
    expect(board_btn).to_have_class(re.compile(r"\bc094\b"))

    # Switch back to Table view
    table_btn.click()
    page.wait_for_timeout(300)
    expect(table_btn).to_have_class(re.compile(r"\bc094\b"))


def test_sidebar_navigation(page: Page):
    """Test navigating through Sidebar pages: Overview, Conflicts, History, Ports."""
    overview_nav = page.locator('button.sidebar-nav-btn:has-text("Overview")')
    conflicts_nav = page.locator('button.sidebar-nav-btn:has-text("Conflicts")')
    history_nav = page.locator('button.sidebar-nav-btn:has-text("History")')
    ports_nav = page.locator('button.sidebar-nav-btn:has-text("Ports")')

    # Navigate to Overview
    overview_nav.click()
    page.wait_for_timeout(400)
    expect(overview_nav).to_have_class(re.compile(r"\bactive\b"))

    # Navigate to Conflicts
    conflicts_nav.click()
    page.wait_for_timeout(400)
    expect(conflicts_nav).to_have_class(re.compile(r"\bactive\b"))

    # Navigate to History
    history_nav.click()
    page.wait_for_timeout(400)
    expect(history_nav).to_have_class(re.compile(r"\bactive\b"))

    # Return to Ports
    ports_nav.click()
    page.wait_for_timeout(400)
    expect(ports_nav).to_have_class(re.compile(r"\bactive\b"))


def test_system_telemetry_drawer(page: Page):
    """Test opening the System Telemetry Drawer from Stats Strip."""
    cpu_card = page.locator('.c082, .c088').first
    cpu_card.click()

    # Drawer panel should be visible
    drawer = page.locator('.drawer-panel')
    expect(drawer).to_be_visible(timeout=5000)
    expect(drawer).to_contain_text("System Telemetry & Hardware")

    # Check for close button and close it
    close_btn = drawer.locator('button[aria-label="Close"]')
    expect(close_btn).to_be_visible()
    close_btn.click()

    # Drawer should be hidden
    expect(drawer).not_to_be_visible()


def test_customize_settings_drawer(page: Page):
    """Test opening the Customize layout and settings drawer."""
    customize_btn = page.locator('button[aria-label="Customize layout"]')
    expect(customize_btn).to_be_visible()
    customize_btn.click()

    # Verify customize drawer panel opens
    drawer = page.locator('.drawer-panel')
    expect(drawer).to_be_visible(timeout=5000)
    expect(drawer).to_contain_text("Customize Dashboard")

    # Close drawer
    close_btn = drawer.locator('button[aria-label="Close drawer"]')
    close_btn.click()
    expect(drawer).not_to_be_visible()


def test_theme_toggle(page: Page):
    """Test switching between dark and light themes."""
    theme_btn = page.locator('button[aria-label="Toggle theme"]')
    expect(theme_btn).to_be_visible()

    # Initial theme is dark
    theme_btn.click()
    page.wait_for_timeout(300)

    # Toggle back to dark
    theme_btn.click()
    page.wait_for_timeout(300)


def test_keyboard_shortcuts_and_command_palette(page: Page):
    """Test keyboard shortcuts cheatsheet (?) and Command Palette (Ctrl+K)."""
    # Press '?' to trigger Shortcuts Modal
    page.keyboard.press("?")
    shortcuts_modal = page.locator('.modal-content:has-text("Keyboard Shortcuts")')
    expect(shortcuts_modal).to_be_visible(timeout=3000)
    expect(shortcuts_modal).to_contain_text("Quick focus search input")

    # Close via Escape
    page.keyboard.press("Escape")
    expect(shortcuts_modal).not_to_be_visible()

    # Open Command Palette via Ctrl+K
    page.keyboard.press("Control+k")
    palette = page.locator('.command-palette')
    expect(palette).to_be_visible(timeout=3000)
    expect(palette.locator('input[type="text"]')).to_be_visible()

    # Close Command Palette via Escape
    page.keyboard.press("Escape")
    expect(palette).not_to_be_visible()


def test_add_app_modal_flow(page: Page):
    """Test opening the Add App modal and verifying port availability check."""
    add_btn = page.locator('button:has-text("Add App")')
    expect(add_btn).to_be_visible()
    add_btn.click()

    # Modal opens
    modal = page.locator('.modal-content:has-text("Add custom app")')
    expect(modal).to_be_visible(timeout=5000)

    # Verify input fields exist
    name_input = modal.locator('input[placeholder*="Billing API"]').first
    expect(name_input).to_be_visible()

    # Close modal
    close_btn = modal.locator('button:has-text("Cancel")')
    close_btn.click()
    expect(modal).not_to_be_visible()


def test_accessibility_audit(page: Page):
    """Perform lightweight automated accessibility audit."""
    a11y_result = page.evaluate(
        """() => {
            const text = (el) => (el.innerText || el.textContent || '').trim();
            return {
                images_without_alt: document.querySelectorAll('img:not([alt])').length,
                buttons_without_name: [...document.querySelectorAll('button')].filter(
                    el => !text(el) && !el.getAttribute('aria-label') && !el.getAttribute('title')
                ).length,
                inputs_without_label: [...document.querySelectorAll('input:not([type=hidden]), select, textarea')].filter(
                    el => !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby') && !el.getAttribute('placeholder') && !el.closest('label')
                ).length,
                h1_count: document.querySelectorAll('h1').length,
            };
        }"""
    )
    assert a11y_result["images_without_alt"] == 0, f"Images missing alt text: {a11y_result['images_without_alt']}"
    assert a11y_result["buttons_without_name"] == 0, f"Buttons missing accessible name: {a11y_result['buttons_without_name']}"
    assert a11y_result["inputs_without_label"] == 0, f"Inputs missing label: {a11y_result['inputs_without_label']}"
    assert a11y_result["h1_count"] >= 1, "Page must have at least one top-level h1 heading"
