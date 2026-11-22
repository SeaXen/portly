"""E2E browser tests for new All-in-One Docker, Tunnel & Port management features."""

import pytest
from playwright.sync_api import Page, expect


@pytest.fixture
def desktop_page(authenticated_context, portly_server):
    page = authenticated_context.new_page()
    with page.expect_response(lambda r: "/api/settings" in r.url, timeout=12000):
        page.goto(portly_server, wait_until="domcontentloaded")
    page.wait_for_selector(".portly-sidebar, .c068", timeout=12000)
    yield page


def test_deploy_container_tab_and_templates(desktop_page: Page):
    """Verify Deploy Container tab in Add App modal with quick templates."""
    # Click "+ Add App"
    add_btn = desktop_page.locator("button:has-text('+ Add App'), button:has-text('Add App')").first
    expect(add_btn).to_be_visible()
    add_btn.click()

    # Verify modal opened
    modal = desktop_page.locator(".modal-content")
    expect(modal).to_be_visible()

    # Click "Deploy Container" tab
    deploy_tab = modal.locator("button:has-text('Deploy Container')")
    expect(deploy_tab).to_be_visible()
    deploy_tab.click()

    # Click "+ Redis" preset template
    redis_preset = modal.locator("button:has-text('+ Redis')")
    expect(redis_preset).to_be_visible()
    redis_preset.click()

    # Verify fields populated
    image_input = modal.locator("#deploy-image")
    expect(image_input).to_have_value("redis:7-alpine")

    name_input = modal.locator("#deploy-name")
    expect(name_input).to_have_value("redis")

    # Close modal
    modal.locator("button:has-text('Cancel')").click()
    expect(modal).not_to_be_visible()


def test_system_drawer_docker_hygiene(desktop_page: Page):
    """Verify Docker Storage & Hygiene section in System Telemetry drawer."""
    # Click on the stats strip segment to open System Drawer
    stat_segment = desktop_page.locator("button[aria-label*='telemetry']").first
    expect(stat_segment).to_be_visible()
    stat_segment.click()

    drawer = desktop_page.locator(".drawer-panel")
    expect(drawer).to_be_visible()

    # Verify heading
    expect(drawer.locator("h2:has-text('System Telemetry & Hardware')")).to_be_visible()

    # Close drawer
    drawer.locator("button[aria-label='Close']").click()
    expect(drawer).not_to_be_visible()


def test_app_detail_tunnels_and_proxy(desktop_page: Page):
    """Verify Cloudflare Tunnel tab and Cloudflare Ingress generator in AppDetailModal."""
    # Click a row with a published port: proxy generation needs port > 0, and
    # the first row may be an unpublished container on Docker-heavy hosts.
    import re
    rows = desktop_page.locator(".portly-table-row")
    expect(rows.first).to_be_visible(timeout=15000)
    chosen = None
    for i in range(rows.count()):
        lines = [l.strip() for l in rows.nth(i).inner_text().splitlines()]
        if any(re.fullmatch(r"[1-9]\d{0,4}", l) for l in lines):
            chosen = rows.nth(i)
            break
    assert chosen is not None, "No table row with a published port found"
    chosen.click()

    detail_modal = desktop_page.locator(".modal-content")
    expect(detail_modal).to_be_visible()

    # Verify "Cloudflare / Tunnels" tab button
    tunnel_tab = detail_modal.locator("button:has-text('Cloudflare / Tunnels')")
    expect(tunnel_tab).to_be_visible()
    tunnel_tab.click()

    # Verify Tunnel URL input
    tunnel_input = detail_modal.locator("#tunnel-url-input")
    expect(tunnel_input).to_be_visible()

    # Switch to "Reverse Proxy" tab
    proxy_tab = detail_modal.locator("button:has-text('Reverse Proxy')")
    proxy_tab.click()

    # Verify "Cloudflare Tunnel" format button
    cf_format_btn = detail_modal.locator("button:has-text('Cloudflare Tunnel')")
    expect(cf_format_btn).to_be_visible()
    cf_format_btn.click()

    # Verify ingress YAML snippet rendered
    pre_snippet = detail_modal.locator("pre")
    expect(pre_snippet).to_contain_text("ingress:")

    # Close modal
    close_btn = detail_modal.locator("button[aria-label='Close dialog']").first
    close_btn.click()
    expect(detail_modal).not_to_be_visible()
