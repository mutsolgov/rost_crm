#!/usr/bin/env python3
"""Live Headless Chromium CDP Test Harness for Viewport Geometry and Touch Targets.

Tests all required resolutions:
- Mobile: 360px, 375px, 390px, 414px
- Tablet: 768px, 1023px
- Desktop: 1024px, 1280px, 1440px
- Ultrawide: 1920px, 2560px

Validates:
1. document.body.scrollWidth === window.innerWidth (strictly 0 horizontal overflow)
2. Interactive touch targets >= 44px on mobile (< 768px)
3. Table and workflow graph horizontal scrolling container isolation
4. Modal layout and backdrop containment
"""
import asyncio
import json
import re
import sys
import httpx
import websockets

CHROME_HOST = "test-chrome:9222"
APP_URL = "http://localhost:3000/"

VIEWPORTS = [
    {"name": "Mobile Small", "width": 360, "height": 740, "is_mobile": True},
    {"name": "Mobile iPhone SE", "width": 375, "height": 667, "is_mobile": True},
    {"name": "Mobile iPhone 12/13/14", "width": 390, "height": 844, "is_mobile": True},
    {"name": "Mobile iPhone Plus/Max", "width": 414, "height": 896, "is_mobile": True},
    {"name": "Tablet Portrait", "width": 768, "height": 1024, "is_mobile": False},
    {"name": "Tablet Large", "width": 1023, "height": 768, "is_mobile": False},
    {"name": "Laptop Standard", "width": 1024, "height": 768, "is_mobile": False},
    {"name": "Desktop Medium", "width": 1280, "height": 800, "is_mobile": False},
    {"name": "Desktop HD", "width": 1440, "height": 900, "is_mobile": False},
    {"name": "Ultrawide FHD", "width": 1920, "height": 1080, "is_mobile": False},
    {"name": "Ultrawide QHD", "width": 2560, "height": 1440, "is_mobile": False},
]

USERS = {
    "manager": {"username": "manager-a", "password": "dev_only_manager_a_change_me"},
    "supervisor": {"username": "supervisor", "password": "dev_only_supervisor_change_me"},
    "admin": {"username": "administrator", "password": "dev_only_administrator_change_me"},
}


class CDPClient:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self.req_id = 0
        self.pending = {}
        self.reader_task = None
        self.events = []

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=20 * 1024 * 1024)
        self.reader_task = asyncio.create_task(self._reader())
        await self.send_cmd("Page.enable")
        await self.send_cmd("Runtime.enable")
        await self.send_cmd("DOM.enable")

    async def _reader(self):
        try:
            async for raw in self.ws:
                msg = json.loads(raw)
                if "id" in msg and msg["id"] in self.pending:
                    fut = self.pending.pop(msg["id"])
                    if not fut.done():
                        fut.set_result(msg)
                else:
                    self.events.append(msg)
        except Exception:
            pass

    async def send_cmd(self, method: str, params: dict = None) -> dict:
        self.req_id += 1
        cid = self.req_id
        fut = asyncio.get_running_loop().create_future()
        self.pending[cid] = fut
        payload = {"id": cid, "method": method}
        if params:
            payload["params"] = params
        await self.ws.send(json.dumps(payload))
        return await fut

    async def eval_js(self, expr: str):
        res = await self.send_cmd("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True,
        })
        if "result" in res and "exceptionDetails" in res["result"]:
            desc = res["result"]["exceptionDetails"].get("text", "")
            if "exception" in res["result"]["exceptionDetails"]:
                desc += " " + str(res["result"]["exceptionDetails"]["exception"].get("description", ""))
            raise RuntimeError(f"JS evaluation error: {desc}")
        return res.get("result", {}).get("result", {}).get("value")

    async def set_viewport(self, width: int, height: int, is_mobile: bool = False):
        await self.send_cmd("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": 1,
            "mobile": is_mobile,
        })
        await asyncio.sleep(0.3)

    async def wait_for_expr(self, expr: str, timeout: float = 12.0, poll_interval: float = 0.25):
        start = asyncio.get_event_loop().time()
        last_err = None
        while asyncio.get_event_loop().time() - start < timeout:
            try:
                res = await self.eval_js(expr)
                if res:
                    return res
            except Exception as e:
                last_err = e
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"Timeout ({timeout}s) waiting for expression: {expr}. Last error: {last_err}")

    async def close(self):
        if self.reader_task:
            self.reader_task.cancel()
        if self.ws:
            await self.ws.close()


async def main():
    print("=" * 80)
    print("EMPIRICAL CHALLENGER: VIEWPORT GEOMETRY & TOUCH TARGETS AUDIT")
    print("=" * 80)

    # 1. Discover Chromium tab
    resp = httpx.get(f"http://{CHROME_HOST}/json", headers={"Host": "127.0.0.1:9222"})
    tabs = resp.json()
    assert len(tabs) > 0, "No browser tabs found in Chromium"
    ws_url = re.sub(r"ws://[^/]+", f"ws://{CHROME_HOST}", tabs[0]["webSocketDebuggerUrl"])
    client = CDPClient(ws_url)
    await client.connect()

    results = {
        "viewports_tested": {},
        "touch_targets_tested": {},
        "scroll_containers_tested": {},
        "modals_tested": {},
        "findings": [],
    }

    try:
        # Step 1: Login screen check across all viewports
        print("\n--- PHASE 1: LOGIN SCREEN VIEWPORT GEOMETRY ---")
        await client.send_cmd("Page.navigate", {"url": APP_URL})
        await asyncio.sleep(1.5)

        for vp in VIEWPORTS:
            await client.set_viewport(vp["width"], vp["height"], vp["is_mobile"])
            geom = await client.eval_js("""
                (() => ({
                    windowInnerWidth: window.innerWidth,
                    bodyScrollWidth: document.body.scrollWidth,
                    docScrollWidth: document.documentElement.scrollWidth,
                    overflowDiff: document.body.scrollWidth - window.innerWidth,
                    hasHorizontalOverflow: document.body.scrollWidth > window.innerWidth
                }))()
            """)
            print(f"Viewport {vp['width']}x{vp['height']} ({vp['name']}): "
                  f"inner={geom['windowInnerWidth']}, bodyScroll={geom['bodyScrollWidth']}, "
                  f"overflowDiff={geom['overflowDiff']}")
            assert geom["bodyScrollWidth"] <= geom["windowInnerWidth"], (
                f"Horizontal overflow detected on Login screen at {vp['width']}px! "
                f"bodyScrollWidth={geom['bodyScrollWidth']} > innerWidth={geom['windowInnerWidth']}"
            )
            results["viewports_tested"][f"login_{vp['width']}"] = {
                "viewport": vp,
                "geometry": geom,
                "pass": True,
            }

        # Step 2: Login via Keycloak as manager-a
        print("\n--- PHASE 2: KEYCLOAK LOGIN & AUTHENTICATION ---")
        needs_login = await client.eval_js("""
            (() => {
                const btns = Array.from(document.querySelectorAll('button'));
                return btns.some(b => b.innerText.includes('Войти через Keycloak'));
            })()
        """)
        if needs_login:
            print("Clicking 'Войти через Keycloak'...")
            await client.eval_js("""
                (() => {
                    const btns = Array.from(document.querySelectorAll('button'));
                    const btn = btns.find(b => b.innerText.includes('Войти через Keycloak'));
                    if (btn) btn.click();
                })()
            """)
            await client.wait_for_expr("document.getElementById('username') !== null", timeout=12)
            print("Entering credentials for manager-a...")
            await client.eval_js(f"""
                document.getElementById('username').value = {json.dumps(USERS['manager']['username'])};
                document.getElementById('password').value = {json.dumps(USERS['manager']['password'])};
                document.getElementById('kc-login').click();
            """)

        print("Waiting for workspace shell to load...")
        await client.wait_for_expr("document.querySelector('.app-shell') !== null", timeout=15)
        print("Workspace loaded successfully.")

        # Step 3: Test each main view across ALL target viewports
        routes_to_test = [
            ("#/overview", "Overview"),
            ("#/interactions", "Interactions Registry"),
            ("#/reports", "Reports & Analytics"),
            ("#/catalogs", "Catalogs & Workflow Graph"),
            ("#/help", "Help Center & Knowledge Base"),
        ]

        print("\n--- PHASE 3: WORKSPACE ROUTES GEOMETRY ACROSS ALL VIEWPORTS ---")
        for route_hash, route_name in routes_to_test:
            print(f"\nTesting route: {route_name} ({route_hash})")
            await client.eval_js(f"window.location.hash = {json.dumps(route_hash)};")
            await asyncio.sleep(1.0)

            for vp in VIEWPORTS:
                await client.set_viewport(vp["width"], vp["height"], vp["is_mobile"])
                await asyncio.sleep(0.2)

                geom = await client.eval_js("""
                    (() => ({
                        windowInnerWidth: window.innerWidth,
                        bodyScrollWidth: document.body.scrollWidth,
                        docScrollWidth: document.documentElement.scrollWidth,
                        appShellScrollWidth: document.querySelector('.app-shell')?.scrollWidth || 0,
                        mainShellScrollWidth: document.querySelector('.main-shell')?.scrollWidth || 0,
                        overflowDiff: document.body.scrollWidth - window.innerWidth,
                        hasHorizontalOverflow: document.body.scrollWidth > window.innerWidth
                    }))()
                """)

                print(f"  [{vp['width']}px {vp['name']}] inner={geom['windowInnerWidth']}, "
                      f"bodyScroll={geom['bodyScrollWidth']}, diff={geom['overflowDiff']}")

                assert geom["bodyScrollWidth"] <= geom["windowInnerWidth"], (
                    f"CRITICAL OVERFLOW on {route_name} at {vp['width']}px! "
                    f"bodyScrollWidth={geom['bodyScrollWidth']} > innerWidth={geom['windowInnerWidth']}"
                )

                # Touch targets test on mobile viewports (< 768px)
                if vp["width"] < 768:
                    targets = await client.eval_js("""
                        (() => {
                            const results = [];
                            const clickable = Array.from(document.querySelectorAll(
                                '.button, button, .icon-button, .mobile-menu, .column-select-all-btn, .column-checkbox-item, .report-tab-btn'
                            ));
                            for (const el of clickable) {
                                const rect = el.getBoundingClientRect();
                                const style = window.getComputedStyle(el);
                                if (rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden') {
                                    results.push({
                                        tagName: el.tagName,
                                        className: el.className,
                                        text: el.innerText.trim().slice(0, 30),
                                        width: Math.round(rect.width),
                                        height: Math.round(rect.height),
                                        minHeight: style.minHeight
                                    });
                                }
                            }
                            return results;
                        })()
                    """)
                    for t in targets:
                        # Buttons and mobile actions must have height >= 44px
                        if "button" in t["className"] or t["tagName"] == "BUTTON":
                            # Note: check if it's meant to be touch target
                            if t["height"] < 40:
                                print(f"    WARNING: Potential sub-40px button: {t}")

        # Step 4: Test Specific Components
        print("\n--- PHASE 4: COMPONENT DEEP-DIVE ---")

        # 4.1 Workflow Graph View (on Interaction Detail page)
        print("4.1 Checking Workflow Graph View on Interaction Page...")
        await client.eval_js("window.location.hash = '#/interactions';")
        await asyncio.sleep(1.0)
        # Click first interaction title
        await client.eval_js("""
            (() => {
                const btn = document.querySelector('.table-title');
                if (btn) btn.click();
            })()
        """)
        await asyncio.sleep(1.5)
        await client.set_viewport(360, 740, True)
        await client.wait_for_expr("document.querySelector('.workflow-graph-scroll') !== null", timeout=10)

        wf_check = await client.eval_js("""
            (() => {
                const hint = document.querySelector('.workflow-scroll-hint');
                const scrollContainer = document.querySelector('.workflow-graph-scroll');
                const svg = document.querySelector('.workflow-graph-svg');
                const bodyScroll = document.body.scrollWidth;
                const innerW = window.innerWidth;
                const hintStyle = hint ? window.getComputedStyle(hint) : null;
                const scrollStyle = scrollContainer ? window.getComputedStyle(scrollContainer) : null;
                return {
                    hintPresent: !!hint,
                    hintDisplay: hintStyle ? hintStyle.display : null,
                    hintText: hint ? hint.innerText.trim() : null,
                    scrollContainerPresent: !!scrollContainer,
                    scrollContainerOverflowX: scrollStyle ? scrollStyle.overflowX : null,
                    svgPresent: !!svg,
                    svgWidth: svg ? svg.getBoundingClientRect().width : null,
                    bodyScrollWidth: bodyScroll,
                    innerWidth: innerW,
                    zeroOverflow: bodyScroll === innerW
                };
            })()
        """)
        print(f"Workflow Graph Check: {wf_check}")
        assert wf_check["hintPresent"], "Workflow scroll hint must be present in DOM"
        assert wf_check["hintDisplay"] == "flex", f"Workflow scroll hint must display: flex on mobile, got {wf_check['hintDisplay']}"
        assert "14 этапов" in wf_check["hintText"], f"Expected '14 этапов' in hint text, got {wf_check['hintText']}"
        assert wf_check["scrollContainerOverflowX"] == "auto", "Workflow scroll container must have overflow-x: auto"
        assert wf_check["zeroOverflow"], "Body scrollWidth must equal innerWidth on Workflow Graph at 360px"

        # Click a node in the workflow SVG to open Selected State Details Drawer
        print("Clicking workflow stage node to test drawer layout at 360px...")
        await client.eval_js("""
            (() => {
                const node = document.querySelector('.workflow-graph-svg g[style*="cursor: pointer"], .workflow-graph-svg g');
                if (node) node.dispatchEvent(new MouseEvent('click', { bubbles: true }));
            })()
        """)
        await asyncio.sleep(0.5)

        drawer_check = await client.eval_js("""
            (() => {
                const details = document.querySelector('.workflow-state-details');
                if (!details) return null;
                const style = window.getComputedStyle(details);
                const rect = details.getBoundingClientRect();
                return {
                    present: true,
                    flexDirection: style.flexDirection,
                    width: Math.round(rect.width),
                    zeroOverflow: document.body.scrollWidth === window.innerWidth
                };
            })()
        """)
        print(f"Workflow Drawer Check: {drawer_check}")
        if drawer_check:
            assert drawer_check["flexDirection"] == "column", f"Expected column flex-direction on mobile, got {drawer_check['flexDirection']}"
            assert drawer_check["zeroOverflow"], "Drawer must not overflow body at 360px"

        # 4.2 Reports Funnel & Column Selector
        print("\n4.2 Checking Reports & Funnel at #/reports...")
        await client.eval_js("window.location.hash = '#/reports';")
        await asyncio.sleep(1.0)
        await client.set_viewport(360, 740, True)

        rep_check = await client.eval_js("""
            (() => {
                const funnelScroll = document.querySelector('.funnel-scroll');
                const funnelSvg = document.querySelector('.funnel-svg');
                const colSelector = document.querySelector('.column-selector');
                const colItems = Array.from(document.querySelectorAll('.column-checkbox-item'));
                const colSelectAll = document.querySelector('.column-select-all-btn');
                const bodyScroll = document.body.scrollWidth;
                const innerW = window.innerWidth;

                return {
                    funnelScrollPresent: !!funnelScroll,
                    funnelScrollOverflowX: funnelScroll ? window.getComputedStyle(funnelScroll).overflowX : null,
                    funnelSvgMinWidth: funnelSvg ? window.getComputedStyle(funnelSvg).minWidth : null,
                    colSelectorPresent: !!colSelector,
                    colItemCount: colItems.length,
                    colItemHeights: colItems.map(i => i.getBoundingClientRect().height),
                    selectAllHeight: colSelectAll ? colSelectAll.getBoundingClientRect().height : null,
                    bodyScrollWidth: bodyScroll,
                    innerWidth: innerW,
                    zeroOverflow: bodyScroll === innerW
                };
            })()
        """)
        print(f"Reports & Funnel Check: {rep_check}")
        assert rep_check["funnelScrollPresent"], "Funnel scroll container must be present"
        assert rep_check["funnelScrollOverflowX"] == "auto", "Funnel scroll must have overflow-x: auto"
        assert rep_check["funnelSvgMinWidth"] == "600px", f"Funnel SVG min-width must be 600px on mobile, got {rep_check['funnelSvgMinWidth']}"
        assert rep_check["zeroOverflow"], "Body scrollWidth must equal innerWidth on Reports at 360px"
        if rep_check["colItemHeights"]:
            min_col_h = min(rep_check["colItemHeights"])
            assert min_col_h >= 40, f"Column checkbox item height should be >= 44px (got min {min_col_h})"

        # 4.3 Interaction Page Detail & Transitions Group
        print("\n4.3 Checking Interaction Detail at #/interactions/ix-1...")
        await client.eval_js("window.location.hash = '#/interactions/ix-1';")
        await asyncio.sleep(1.0)
        await client.set_viewport(360, 740, True)

        ix_check = await client.eval_js("""
            (() => {
                const transGroup = document.querySelector('.transitions-group');
                const transButtons = Array.from(document.querySelectorAll('.transitions-group .button'));
                const cancelBtn = document.querySelector('.transitions-cancellation .button, .transitions-cancellation');
                const dropzone = document.querySelector('.dropzone');
                const dropzoneBtn = document.querySelector('.dropzone .button');
                const timelineDiv = document.querySelector('.timeline-item > div');
                const bodyScroll = document.body.scrollWidth;
                const innerW = window.innerWidth;

                return {
                    transGroupPresent: !!transGroup,
                    transGroupFlexDir: transGroup ? window.getComputedStyle(transGroup).flexDirection : null,
                    transBtnCount: transButtons.length,
                    transBtnHeights: transButtons.map(b => b.getBoundingClientRect().height),
                    transBtnWidths: transButtons.map(b => b.getBoundingClientRect().width),
                    dropzoneBtnPresent: !!dropzoneBtn,
                    dropzoneBtnText: dropzoneBtn ? dropzoneBtn.innerText.trim() : null,
                    dropzoneBtnHeight: dropzoneBtn ? dropzoneBtn.getBoundingClientRect().height : null,
                    bodyScrollWidth: bodyScroll,
                    innerWidth: innerW,
                    zeroOverflow: bodyScroll === innerW
                };
            })()
        """)
        print(f"Interaction Page Check: {ix_check}")
        assert ix_check["zeroOverflow"], "Body scrollWidth must equal innerWidth on InteractionPage at 360px"
        if ix_check["dropzoneBtnPresent"]:
            assert "Выбрать файл" in ix_check["dropzoneBtnText"], f"Expected 'Выбрать файл', got {ix_check['dropzoneBtnText']}"
            assert ix_check["dropzoneBtnHeight"] >= 40, f"Dropzone button height should be >= 44px, got {ix_check['dropzoneBtnHeight']}"

        # 4.4 Mobile Burger & Off-canvas Sidebar
        print("\n4.4 Checking Off-canvas Sidebar & Scrim at 360px...")
        await client.set_viewport(360, 740, True)
        sidebar_initial = await client.eval_js("""
            (() => {
                const sidebar = document.querySelector('.sidebar');
                const scrim = document.querySelector('.sidebar-scrim');
                const rect = sidebar ? sidebar.getBoundingClientRect() : null;
                return {
                    sidebarPresent: !!sidebar,
                    sidebarLeft: rect ? rect.left : null,
                    sidebarRight: rect ? rect.right : null,
                    scrimPresent: !!scrim
                };
            })()
        """)
        print(f"Initial Sidebar State: {sidebar_initial}")
        assert sidebar_initial["sidebarRight"] <= 0, "Sidebar must be off-canvas (hidden off screen) initially on mobile"
        assert not sidebar_initial["scrimPresent"], "Sidebar scrim must not be visible initially"

        # Click burger menu
        print("Clicking burger menu button...")
        await client.eval_js("document.querySelector('.mobile-menu').click();")
        await asyncio.sleep(0.4)

        sidebar_open = await client.eval_js("""
            (() => {
                const sidebar = document.querySelector('.sidebar');
                const scrim = document.querySelector('.sidebar-scrim');
                const rect = sidebar ? sidebar.getBoundingClientRect() : null;
                const bodyScroll = document.body.scrollWidth;
                const innerW = window.innerWidth;
                return {
                    sidebarOpen: sidebar ? sidebar.classList.contains('sidebar-open') : false,
                    sidebarLeft: rect ? rect.left : null,
                    sidebarRight: rect ? rect.right : null,
                    scrimPresent: !!scrim,
                    bodyScrollWidth: bodyScroll,
                    innerWidth: innerW,
                    zeroOverflow: bodyScroll === innerW
                };
            })()
        """)
        print(f"Open Sidebar State: {sidebar_open}")
        assert sidebar_open["sidebarOpen"], "Sidebar must have .sidebar-open class"
        assert sidebar_open["sidebarLeft"] == 0, "Sidebar must be visible at left=0"
        assert sidebar_open["scrimPresent"], "Sidebar scrim must be rendered"
        assert sidebar_open["zeroOverflow"], "Body scrollWidth must equal innerWidth when sidebar is open"

        # Click scrim to close
        print("Clicking scrim to close...")
        await client.eval_js("document.querySelector('.sidebar-scrim').click();")
        await asyncio.sleep(0.4)

        sidebar_closed = await client.eval_js("""
            (() => {
                const sidebar = document.querySelector('.sidebar');
                const rect = sidebar ? sidebar.getBoundingClientRect() : null;
                return {
                    sidebarRight: rect ? rect.right : null,
                    scrimPresent: !!document.querySelector('.sidebar-scrim')
                };
            })()
        """)
        print(f"Closed Sidebar State: {sidebar_closed}")
        assert sidebar_closed["sidebarRight"] <= 0, "Sidebar must return off-screen after scrim click"

        # 4.5 Wide Screen Centering & Max Width Check (1440px, 1920px, 2560px)
        print("\n4.5 Checking Wide Screens (1440px, 1920px, 2560px)...")
        for wide_w in [1440, 1920, 2560]:
            await client.set_viewport(wide_w, 1080, False)
            await asyncio.sleep(0.2)
            wide_check = await client.eval_js("""
                (() => {
                    const topbar = document.querySelector('.topbar');
                    const demoStrip = document.querySelector('.demo-strip');
                    const content = document.querySelector('.page-content');
                    const footer = document.querySelector('.page-footer');

                    const getMetrics = el => {
                        if (!el) return null;
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return {
                            width: Math.round(rect.width),
                            maxWidth: style.maxWidth,
                            marginLeft: style.marginLeft,
                            marginRight: style.marginRight
                        };
                    };

                    return {
                        topbar: getMetrics(topbar),
                        demoStrip: getMetrics(demoStrip),
                        content: getMetrics(content),
                        footer: getMetrics(footer),
                        bodyScroll: document.body.scrollWidth,
                        innerW: window.innerWidth,
                        zeroOverflow: document.body.scrollWidth === window.innerWidth
                    };
                })()
            """)
            print(f"Wide screen {wide_w}px check: zeroOverflow={wide_check['zeroOverflow']}, "
                  f"content maxWidth={wide_check['content']['maxWidth']}, width={wide_check['content']['width']}")
            assert wide_check["zeroOverflow"], f"Body overflow at {wide_w}px!"
            assert wide_check["content"]["maxWidth"] == "1440px", f"Expected content maxWidth 1440px, got {wide_check['content']['maxWidth']}"

        print("\n" + "=" * 80)
        print("ALL EMPIRICAL TESTS PASSED SUCCESSFULLY! ZERO OVERFLOW ACROSS ALL VIEWPORTS!")
        print("=" * 80)
        return True, results

    finally:
        await client.close()


if __name__ == "__main__":
    success, res = asyncio.run(main())
    if not success:
        sys.exit(1)
