"""Challenger 2 (Live Browser E2E & 152-FZ Verifier) for Stage 9 in rost_crm.

Empirical live browser verification of the running application on http://localhost:3000
using real headless Chromium driven via Chrome DevTools Protocol (CDP).

Verifies:
1. Manager Role (`manager-a` - Анна Смирнова):
   - Access «Справка / Регламенты» (#/help)
   - Verify strictly 3 visible tabs rendered: 'manager', 'errors', 'security'
   - Verify 'supervisor' and 'admin' tabs are absent from DOM
   - Verify default activeTab is 'manager' with funnel map (15 stages, 4 phases)
   - Test AC21 interactive error simulator:
     * Codes 404 (Zero-Oracle), 409 (CAS revision conflict), 422 (Validation), 500 (Server error)
     * Form inputs (title, comment) preserved without reset/reload
     * Correct error text, remediation advice, and canonical JSON envelope
2. Supervisor Role (`supervisor` - Елена Соколова):
   - Access «Справка / Регламенты» (#/help)
   - Verify strictly 4 visible tabs rendered: 'manager', 'supervisor', 'errors', 'security'
   - Verify 'admin' tab is absent from DOM
   - Verify default activeTab is 'supervisor' with supervisor guidance & SLA sections
3. Administrator Role (`administrator` - Администратор Демонстрационный):
   - Access «Справка / Регламенты» (#/help)
   - Verify all 5 visible tabs rendered: 'manager', 'supervisor', 'admin', 'errors', 'security'
   - Verify default activeTab is 'admin' with import, migration, and audit log sections
   - Switch to 'security' tab and verify 152-FZ / FSTEC #117 security policies
4. Security 152-FZ / FSTEC #117 Compliance across all sessions:
   - Zero JWT tokens in localStorage or sessionStorage (strictly in-memory)
   - Zero sensitive credentials or tokens in web storage
"""
import asyncio
import json
import re
import sys
import httpx
import websockets

CHROME_HOST = "test-chrome:9222"
APP_URL = "http://localhost:3000/"

USERS = {
    "manager": {
        "username": "manager-a",
        "password": "dev_only_manager_a_change_me",
        "expected_name": "Анна Смирнова",
        "expected_role_ui": "Менеджер",
        "expected_role_code": "manager",
        "expected_tab_count": 3,
        "expected_tab_names": ["Менеджер", "Справочник ошибок", "Безопасность 152-ФЗ"],
        "forbidden_tab_names": ["Руководитель", "Администратор"],
        "initial_tab": "manager",
    },
    "supervisor": {
        "username": "supervisor",
        "password": "dev_only_supervisor_change_me",
        "expected_name": "Елена Соколова",
        "expected_role_ui": "Руководитель",
        "expected_role_code": "supervisor",
        "expected_tab_count": 4,
        "expected_tab_names": ["Менеджер", "Руководитель", "Справочник ошибок", "Безопасность 152-ФЗ"],
        "forbidden_tab_names": ["Администратор"],
        "initial_tab": "supervisor",
    },
    "administrator": {
        "username": "administrator",
        "password": "dev_only_administrator_change_me",
        "expected_name": "Администратор Демонстрационный",
        "expected_role_ui": "Администратор",
        "expected_role_code": "administrator",
        "expected_tab_count": 5,
        "expected_tab_names": ["Менеджер", "Руководитель", "Администратор", "Справочник ошибок", "Безопасность 152-ФЗ"],
        "forbidden_tab_names": [],
        "initial_tab": "admin",
    },
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
        await self.send_cmd("Network.enable")

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

    async def wait_for_expr(self, expr: str, timeout: float = 15.0, poll_interval: float = 0.3):
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

    async def clear_session(self):
        await self.send_cmd("Network.clearBrowserCookies")
        await self.send_cmd("Storage.clearDataForOrigin", {
            "origin": "http://localhost:3000",
            "storageTypes": "all",
        })
        await self.send_cmd("Storage.clearDataForOrigin", {
            "origin": "http://localhost:8080",
            "storageTypes": "all",
        })

    async def close(self):
        if self.reader_task:
            self.reader_task.cancel()
        if self.ws:
            await self.ws.close()


async def verify_web_storage(client: CDPClient, role_label: str) -> dict:
    """Verifies 152-FZ / FSTEC #117 in-memory storage invariants."""
    ls_keys = await client.eval_js("Object.keys(window.localStorage)")
    ls_dump = await client.eval_js("JSON.stringify(window.localStorage)")
    ss_keys = await client.eval_js("Object.keys(window.sessionStorage)")
    ss_dump = await client.eval_js("JSON.stringify(window.sessionStorage)")

    # 1. No JWT tokens (pattern: eyJ...)
    jwt_pattern = r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    ls_jwt = re.search(jwt_pattern, ls_dump or "")
    ss_jwt = re.search(jwt_pattern, ss_dump or "")
    assert ls_jwt is None, f"CRITICAL 152-FZ VIOLATION: JWT found in localStorage for {role_label}: {ls_jwt.group(0)}"
    assert ss_jwt is None, f"CRITICAL 152-FZ VIOLATION: JWT found in sessionStorage for {role_label}: {ss_jwt.group(0)}"

    # 2. No session tokens, passwords or secrets
    forbidden = ["access_token", "id_token", "refresh_token", "password", "client_secret"]
    for k in (ls_keys or []):
        for f in forbidden:
            assert f not in k.lower(), f"Forbidden key in localStorage: {k}"
    for k in (ss_keys or []):
        for f in forbidden:
            assert f not in k.lower(), f"Forbidden key in sessionStorage: {k}"

    return {
        "role": role_label,
        "localStorage_keys": ls_keys,
        "sessionStorage_keys": ss_keys,
        "jwt_in_localStorage": False,
        "jwt_in_sessionStorage": False,
        "status": "PASS",
    }


async def login(client: CDPClient, user_conf: dict):
    """Logs into the application with the specified user credentials."""
    print(f"\nLogging in as {user_conf['username']} ({user_conf['expected_name']})...")
    await client.clear_session()
    await client.send_cmd("Page.navigate", {"url": APP_URL})
    await asyncio.sleep(1.5)

    # Check if we need to click "Войти через Keycloak"
    await client.wait_for_expr("""
        (() => {
            const btns = Array.from(document.querySelectorAll('button'));
            return btns.some(b => b.innerText.includes('Войти через Keycloak'));
        })()
    """, timeout=12)

    await client.eval_js("""
        (() => {
            const btns = Array.from(document.querySelectorAll('button'));
            const btn = btns.find(b => b.innerText.includes('Войти через Keycloak'));
            if (btn) btn.click();
        })()
    """)

    # Wait for Keycloak login form
    await client.wait_for_expr("document.getElementById('username') !== null", timeout=12)
    kc_url = await client.eval_js("window.location.href")
    print(f"Keycloak login page reached: {kc_url}")

    # Fill username and password and submit
    await client.eval_js(f"""
        document.getElementById('username').value = {json.dumps(user_conf['username'])};
        document.getElementById('password').value = {json.dumps(user_conf['password'])};
        document.getElementById('kc-login').click();
    """)

    # Wait for CRM application shell to mount
    await client.wait_for_expr(
        "document.querySelector('.account-text') !== null && document.querySelector('.main-nav') !== null",
        timeout=15
    )

    user_name = await client.eval_js("document.querySelector('.account-text strong').innerText")
    user_role = await client.eval_js("document.querySelector('.account-text small').innerText")
    print(f"Authenticated successfully: '{user_name}' ({user_role})")
    assert user_conf["expected_name"] in user_name, f"Expected {user_conf['expected_name']}, got {user_name}"


async def run_stage9_browser_e2e():
    print("=" * 80)
    print("STARTING LIVE STAGE 9 BROWSER E2E VERIFICATION (rost_crm)")
    print("=" * 80)

    # 1. Discover Chromium tab
    print("\n[Step 0] Discovering headless Chromium targets...")
    resp = httpx.get(f"http://{CHROME_HOST}/json", headers={"Host": "127.0.0.1:9222"})
    tabs = resp.json()
    assert len(tabs) > 0, "No browser tabs found in Chromium"
    ws_url = re.sub(r"ws://[^/]+", f"ws://{CHROME_HOST}", tabs[0]["webSocketDebuggerUrl"])
    print(f"Connecting to CDP endpoint: {ws_url}")
    client = CDPClient(ws_url)
    await client.connect()

    evidence = {
        "roles_tested": {},
        "ac21_simulator": {},
        "web_storage_152fz": {},
        "verdict": "UNKNOWN",
    }

    try:
        # ======================================================================
        # ROLE 1: manager-a (Анна Смирнова)
        # ======================================================================
        m_conf = USERS["manager"]
        await login(client, m_conf)

        print("\n[Role: manager-a] Navigating to «Справка / Регламенты» (#/help)...")
        await client.eval_js("window.location.hash = '#/help';")
        await client.wait_for_expr("document.querySelector('.help-center') !== null", timeout=10)

        # Check role badge
        role_chip = await client.eval_js("document.querySelector('.user-role-chip')?.innerText || ''")
        print(f"Role chip text: '{role_chip}'")
        assert "manager" in role_chip.lower(), f"Expected role chip to contain 'manager', got '{role_chip}'"

        # Check visible tabs
        tabs_info = await client.eval_js("""
            (() => {
                const buttons = Array.from(document.querySelectorAll('.help-tabs button[role="tab"]'));
                return buttons.map(b => ({
                    title: b.querySelector('span')?.innerText || '',
                    subtitle: b.querySelector('b')?.innerText || '',
                    active: b.classList.contains('active'),
                    ariaSelected: b.getAttribute('aria-selected') === 'true'
                }));
            })()
        """)
        tab_titles = [t["title"] for t in tabs_info]
        print(f"[Role: manager-a] Rendered tabs ({len(tabs_info)}): {tab_titles}")

        # Assert strictly 3 tabs rendered: manager, errors, security
        assert len(tabs_info) == 3, f"manager-a MUST have strictly 3 tabs, found {len(tabs_info)}: {tab_titles}"
        for exp in m_conf["expected_tab_names"]:
            assert exp in tab_titles, f"manager-a tab list missing expected tab '{exp}'"
        for fbd in m_conf["forbidden_tab_names"]:
            assert fbd not in tab_titles, f"CRITICAL: manager-a rendered forbidden tab '{fbd}'"

        # Check initial active tab
        active_tab_entry = next((t for t in tabs_info if t["active"]), None)
        assert active_tab_entry is not None, "No active tab found"
        assert active_tab_entry["title"] == "Менеджер", f"Expected active tab 'Менеджер', got '{active_tab_entry['title']}'"

        # Check manager tab content: Funnel map with 15 stages & 4 phases
        funnel_heading = await client.eval_js("document.querySelector('.funnel-map-panel h2')?.innerText || ''")
        print(f"[Role: manager-a] Funnel panel heading: '{funnel_heading}'")
        assert "15 этапов" in funnel_heading or "Карта воронки" in funnel_heading

        phases_count = await client.eval_js("document.querySelectorAll('.funnel-phase-card').length")
        assert phases_count == 4, f"Expected 4 phases in funnel map, got {phases_count}"

        # ----------------------------------------------------------------------
        # AC21 Error Simulator Testing under manager-a
        # ----------------------------------------------------------------------
        print("\n[AC21 Simulator] Switching to «Справочник ошибок» tab...")
        await client.eval_js("""
            (() => {
                const buttons = Array.from(document.querySelectorAll('.help-tabs button[role="tab"]'));
                const btn = buttons.find(b => b.querySelector('span')?.innerText.includes('Справочник ошибок'));
                if (btn) btn.click();
            })()
        """)
        await client.wait_for_expr("document.querySelector('.demo-test-form') !== null", timeout=10)

        # Test Error Codes: 404 (Zero-Oracle), 409 (CAS Conflict), 422 (Validation), 500 (Internal Server Error)
        test_cases = [
            {
                "code": "404",
                "custom_title": "Аудит 152-ФЗ: Прямой запрос к чужому ID",
                "custom_comment": "Проверка скрытия факта существования взаимодействия через Zero-Oracle",
                "expected_status": "HTTP 404 Not Found",
                "expected_remediation": "Политика Zero-Oracle (152-ФЗ / ФСТЭК №117)",
                "expected_envelope_code": "NOT_FOUND",
            },
            {
                "code": "409",
                "custom_title": "Аудит оптимистической блокировки (CAS)",
                "custom_comment": "Проверка конфликта ревизий при параллельном сохранении",
                "expected_status": "HTTP 409 Conflict: CAS revision mismatch",
                "expected_remediation": "Откройте карточку в соседней вкладке",
                "expected_envelope_code": "REVISION_CONFLICT",
            },
            {
                "code": "422",
                "custom_title": "Аудит валидации перехода воронки",
                "custom_comment": "Проверка обязательности связки программы и продукта перед передачей материалов",
                "expected_status": "HTTP 422 Unprocessable Entity",
                "expected_remediation": "свяжите валидную совместимую пару «программа + продукт»",
                "expected_envelope_code": "VALIDATION_ERROR",
            },
            {
                "code": "500",
                "custom_title": "Аудит отказоустойчивости сервера",
                "custom_comment": "Проверка сохранения данных формы при сбое ядра обработки",
                "expected_status": "HTTP 500 Internal Server Error",
                "expected_remediation": "Повторите попытку через несколько секунд",
                "expected_envelope_code": "INTERNAL_SERVER_ERROR",
            },
        ]

        ac21_results = []
        for tc in test_cases:
            print(f"\n[AC21 Simulator] Testing fault code {tc['code']}...")
            # Set input values
            await client.eval_js(f"""
                (() => {{
                    const form = document.querySelector('.demo-test-form');
                    const textInput = form.querySelector('input[type="text"]');
                    const textArea = form.querySelector('textarea');
                    const select = form.querySelector('select');

                    // Set title
                    const titleNativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    titleNativeSetter.call(textInput, {json.dumps(tc['custom_title'])});
                    textInput.dispatchEvent(new Event('input', {{ bubbles: true }}));

                    // Set comment
                    const commentNativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                    commentNativeSetter.call(textArea, {json.dumps(tc['custom_comment'])});
                    textArea.dispatchEvent(new Event('input', {{ bubbles: true }}));

                    // Set error code
                    const selectNativeSetter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
                    selectNativeSetter.call(select, {json.dumps(tc['code'])});
                    select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }})()
            """)

            # Submit the form
            await client.eval_js("""
                (() => {
                    const form = document.querySelector('.demo-test-form');
                    const submitBtn = form.querySelector('button[type="submit"]');
                    submitBtn.click();
                })()
            """)
            await asyncio.sleep(0.5)

            # Assert form inputs are PRESERVED without reset
            val_title = await client.eval_js("document.querySelector('.demo-test-form input[type=\"text\"]').value")
            val_comment = await client.eval_js("document.querySelector('.demo-test-form textarea').value")
            assert val_title == tc["custom_title"], f"Form input title reset! Expected '{tc['custom_title']}', got '{val_title}'"
            assert val_comment == tc["custom_comment"], f"Form input comment reset! Expected '{tc['custom_comment']}', got '{val_comment}'"

            # Check rendered alert
            alert_text = await client.eval_js("document.querySelector('.error-alert strong')?.innerText || ''")
            print(f"Rendered error alert: '{alert_text}'")
            assert tc["expected_status"] in alert_text, f"Expected alert '{tc['expected_status']}', got '{alert_text}'"

            # Check remediation
            remediation_text = await client.eval_js("document.querySelector('.action-hint-box')?.innerText || ''")
            print(f"Rendered remediation: '{remediation_text}'")
            assert tc["expected_remediation"] in remediation_text, f"Expected remediation '{tc['expected_remediation']}', got '{remediation_text}'"

            # Check envelope JSON
            envelope_raw = await client.eval_js("document.querySelector('.input-preservation-demo-panel details pre')?.textContent || ''")
            envelope_json = json.loads(envelope_raw)
            print(f"Rendered envelope error code: {envelope_json.get('error', {}).get('code')}")
            assert envelope_json.get("error", {}).get("code") == tc["expected_envelope_code"]

            ac21_results.append({
                "code": tc["code"],
                "input_preserved": True,
                "status_text_matched": True,
                "remediation_matched": True,
                "envelope_code": envelope_json.get("error", {}).get("code"),
                "status": "PASS",
            })

        evidence["ac21_simulator"] = ac21_results

        # Web storage check for manager
        st_mgr = await verify_web_storage(client, "manager-a")
        evidence["web_storage_152fz"]["manager-a"] = st_mgr

        evidence["roles_tested"]["manager-a"] = {
            "tab_count": len(tabs_info),
            "rendered_tabs": tab_titles,
            "supervisor_tab_rendered": "Руководитель" in tab_titles,
            "admin_tab_rendered": "Администратор" in tab_titles,
            "status": "PASS",
        }

        # ======================================================================
        # ROLE 2: supervisor (Елена Соколова)
        # ======================================================================
        s_conf = USERS["supervisor"]
        await login(client, s_conf)

        print("\n[Role: supervisor] Navigating to «Справка / Регламенты» (#/help)...")
        await client.eval_js("window.location.hash = '#/help';")
        await client.wait_for_expr("document.querySelector('.help-center') !== null", timeout=10)

        # Check role badge
        s_role_chip = await client.eval_js("document.querySelector('.user-role-chip')?.innerText || ''")
        print(f"Supervisor role chip text: '{s_role_chip}'")
        assert "supervisor" in s_role_chip.lower(), f"Expected role chip to contain 'supervisor', got '{s_role_chip}'"

        # Check visible tabs
        s_tabs_info = await client.eval_js("""
            (() => {
                const buttons = Array.from(document.querySelectorAll('.help-tabs button[role="tab"]'));
                return buttons.map(b => ({
                    title: b.querySelector('span')?.innerText || '',
                    subtitle: b.querySelector('b')?.innerText || '',
                    active: b.classList.contains('active'),
                    ariaSelected: b.getAttribute('aria-selected') === 'true'
                }));
            })()
        """)
        s_tab_titles = [t["title"] for t in s_tabs_info]
        print(f"[Role: supervisor] Rendered tabs ({len(s_tabs_info)}): {s_tab_titles}")

        # Assert strictly 4 tabs rendered: manager, supervisor, errors, security
        assert len(s_tabs_info) == 4, f"supervisor MUST have strictly 4 tabs, found {len(s_tabs_info)}: {s_tab_titles}"
        for exp in s_conf["expected_tab_names"]:
            assert exp in s_tab_titles, f"supervisor tab list missing expected tab '{exp}'"
        for fbd in s_conf["forbidden_tab_names"]:
            assert fbd not in s_tab_titles, f"CRITICAL: supervisor rendered forbidden tab '{fbd}'"

        # Check default active tab for supervisor: 'supervisor' (Руководитель)
        s_active_tab = next((t for t in s_tabs_info if t["active"]), None)
        assert s_active_tab is not None, "No active tab found for supervisor"
        assert s_active_tab["title"] == "Руководитель", f"Expected initial active tab 'Руководитель', got '{s_active_tab['title']}'"

        # Check supervisor tab content sections
        s_heading = await client.eval_js("document.querySelector('.help-tab-content h2')?.innerText || ''")
        print(f"[Role: supervisor] Active tab heading: '{s_heading}'")
        assert "Регламент руководителя" in s_heading

        s_sections = await client.eval_js("""
            (() => {
                const headings = Array.from(document.querySelectorAll('.help-tab-content h3'));
                return headings.map(h => h.innerText);
            })()
        """)
        print(f"[Role: supervisor] Section headings: {s_sections}")
        assert any("квотами" in h.lower() for h in s_sections), "Missing quota management section"
        assert any("переназначение" in h.lower() for h in s_sections), "Missing reassignment section"
        assert any("аналитический движок" in h.lower() for h in s_sections), "Missing analytics engine section"
        assert any("экспорт отчетов" in h.lower() for h in s_sections), "Missing report export section"
        assert any("zion" in h.lower() for h in s_sections), "Missing LMS Zion integration section"

        # Web storage check for supervisor
        st_sup = await verify_web_storage(client, "supervisor")
        evidence["web_storage_152fz"]["supervisor"] = st_sup

        evidence["roles_tested"]["supervisor"] = {
            "tab_count": len(s_tabs_info),
            "rendered_tabs": s_tab_titles,
            "admin_tab_rendered": "Администратор" in s_tab_titles,
            "initial_active_tab": s_active_tab["title"],
            "status": "PASS",
        }

        # ======================================================================
        # ROLE 3: administrator (Администратор Демонстрационный)
        # ======================================================================
        a_conf = USERS["administrator"]
        await login(client, a_conf)

        print("\n[Role: administrator] Navigating to «Справка / Регламенты» (#/help)...")
        await client.eval_js("window.location.hash = '#/help';")
        await client.wait_for_expr("document.querySelector('.help-center') !== null", timeout=10)

        # Check role badge
        a_role_chip = await client.eval_js("document.querySelector('.user-role-chip')?.innerText || ''")
        print(f"Administrator role chip text: '{a_role_chip}'")
        assert "administrator" in a_role_chip.lower(), f"Expected role chip to contain 'administrator', got '{a_role_chip}'"

        # Check visible tabs
        a_tabs_info = await client.eval_js("""
            (() => {
                const buttons = Array.from(document.querySelectorAll('.help-tabs button[role="tab"]'));
                return buttons.map(b => ({
                    title: b.querySelector('span')?.innerText || '',
                    subtitle: b.querySelector('b')?.innerText || '',
                    active: b.classList.contains('active'),
                    ariaSelected: b.getAttribute('aria-selected') === 'true'
                }));
            })()
        """)
        a_tab_titles = [t["title"] for t in a_tabs_info]
        print(f"[Role: administrator] Rendered tabs ({len(a_tabs_info)}): {a_tab_titles}")

        # Assert strictly 5 tabs rendered: all roles + topics
        assert len(a_tabs_info) == 5, f"administrator MUST have strictly 5 tabs, found {len(a_tabs_info)}: {a_tab_titles}"
        for exp in a_conf["expected_tab_names"]:
            assert exp in a_tab_titles, f"administrator tab list missing expected tab '{exp}'"

        # Check default active tab for administrator: 'admin' (Администратор)
        a_active_tab = next((t for t in a_tabs_info if t["active"]), None)
        assert a_active_tab is not None, "No active tab found for administrator"
        assert a_active_tab["title"] == "Администратор", f"Expected initial active tab 'Администратор', got '{a_active_tab['title']}'"

        # Check admin tab content sections
        a_heading = await client.eval_js("document.querySelector('.help-tab-content h2')?.innerText || ''")
        print(f"[Role: administrator] Active tab heading: '{a_heading}'")
        assert "Регламент администратора" in a_heading

        a_sections = await client.eval_js("""
            (() => {
                const headings = Array.from(document.querySelectorAll('.help-tab-content h3'));
                return headings.map(h => h.innerText);
            })()
        """)
        print(f"[Role: administrator] Section headings: {a_sections}")
        assert any("импорт" in h.lower() for h in a_sections), "Missing import staging section"
        assert any("reconciliation" in h.lower() or "интеграций" in h.lower() for h in a_sections), "Missing inbox section"
        assert any("мигратор" in h.lower() or "workflow" in h.lower() for h in a_sections), "Missing workflow migration section"
        assert any("матрицей" in h.lower() or "программ" in h.lower() for h in a_sections), "Missing program-product section"

        # Switch to 'security' tab under administrator
        print("\n[Role: administrator] Switching to «Безопасность 152-ФЗ» tab...")
        await client.eval_js("""
            (() => {
                const buttons = Array.from(document.querySelectorAll('.help-tabs button[role="tab"]'));
                const btn = buttons.find(b => b.querySelector('span')?.innerText.includes('Безопасность 152-ФЗ'));
                if (btn) btn.click();
            })()
        """)
        await asyncio.sleep(0.5)

        sec_heading = await client.eval_js("document.querySelector('.help-tab-content h2')?.innerText || ''")
        print(f"[Role: administrator] Security tab heading: '{sec_heading}'")
        assert "152-ФЗ" in sec_heading and "ФСТЭК" in sec_heading

        sec_content = await client.eval_js("document.querySelector('.help-tab-content')?.innerText || ''")
        assert "In-Memory" in sec_content, "Missing In-Memory token specification in security tab"
        assert "404" in sec_content, "Missing 404 Zero-Oracle specification in security tab"

        # Web storage check for administrator
        st_admin = await verify_web_storage(client, "administrator")
        evidence["web_storage_152fz"]["administrator"] = st_admin

        evidence["roles_tested"]["administrator"] = {
            "tab_count": len(a_tabs_info),
            "rendered_tabs": a_tab_titles,
            "initial_active_tab": a_active_tab["title"],
            "security_tab_content_verified": True,
            "status": "PASS",
        }

        evidence["verdict"] = "PASS"
        print("\n" + "=" * 80)
        print("ALL LIVE STAGE 9 BROWSER E2E TESTS PASSED (100% EMPIRICAL SUCCESS)")
        print("=" * 80)
        return True, evidence

    finally:
        await client.close()


if __name__ == "__main__":
    success, res = asyncio.run(run_stage9_browser_e2e())
    print("\nFINAL EMPIRICAL REPORT JSON:")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if not success:
        sys.exit(1)
