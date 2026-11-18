"""Smoke test for the first-run flow: fresh start -> setup -> admin -> dashboard."""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def fresh_page(browser_instance, fresh_portly_server_info):
    """A clean browser context (no pre-seeded cookie) pointed at the fresh server."""
    context = browser_instance.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    yield page
    context.close()


def test_first_run_setup_creates_admin_and_loads_dashboard(
    fresh_portly_server_info, fresh_page: Page
):
    """A brand-new install shows the setup screen, then the dashboard after admin creation."""
    page = fresh_page
    page.goto(fresh_portly_server_info["url"], wait_until="domcontentloaded")

    # Fresh start shows the setup screen.
    expect(page.get_by_role("heading", name="Welcome to Portly")).to_be_visible(timeout=15000)
    expect(page.locator("#setup-username")).to_be_visible()
    expect(page.locator("button:has-text('Create Admin Account')")).to_be_visible()

    # Create the primary admin account.
    page.locator("#setup-username").fill("admin")
    page.locator("#setup-password").fill("Password1234!")
    page.locator("#setup-confirm-password").fill("Password1234!")
    page.locator("button:has-text('Create Admin Account')").click()

    # Dashboard loads once setup completes.
    expect(page.locator(".portly-sidebar")).to_be_visible(timeout=15000)
    expect(page.locator("button.sidebar-nav-btn:has-text('Ports')")).to_be_visible()
    expect(page.locator(".c081")).to_contain_text("CPU", ignore_case=True)
