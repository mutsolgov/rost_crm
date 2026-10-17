from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def test_r6_code_splitting_in_app_tsx():
    """Verify App.tsx implements React.lazy and Suspense for heavy views."""
    app_tsx = ROOT / "frontend" / "src" / "App.tsx"
    assert app_tsx.exists(), "App.tsx must exist"
    content = app_tsx.read_text(encoding="utf-8")

    # 1. Verify React.lazy and Suspense imports
    assert "lazy" in content, "lazy must be imported from react in App.tsx"
    assert "Suspense" in content, "Suspense must be imported from react in App.tsx"

    # 2. Verify dynamic imports for heavy views
    assert "lazy(() => import('./views/InteractionPage')" in content, "InteractionPage must be lazy loaded"
    assert "lazy(() => import('./views/Reports')" in content, "Reports must be lazy loaded"
    assert "lazy(() => import('./views/IntegrationsView')" in content, "IntegrationsView must be lazy loaded"
    assert "lazy(() => import('./views/ReferenceViews')" in content, "ReferenceViews must be lazy loaded"

    # 3. Verify Suspense wrapper with Loading fallback
    assert '<Suspense fallback={<Loading label="Загружаем раздел…" />}>' in content, (
        "Suspense fallback must display loading indicator"
    )

    # 4. Verify topbar navigation and breadcrumb root outside Suspense
    assert 'className="topbar"' in content
    assert "sidebar" in content
    assert "breadcrumb-root" in content


def test_r6_lazy_workflow_graph_in_interaction_page():
    """Verify InteractionPage.tsx lazy-loads WorkflowGraphView with Suspense."""
    interaction_page = ROOT / "frontend" / "src" / "views" / "InteractionPage.tsx"
    assert interaction_page.exists(), "InteractionPage.tsx must exist"
    content = interaction_page.read_text(encoding="utf-8")

    # 1. Verify lazy and Suspense imports
    assert "lazy" in content
    assert "Suspense" in content

    # 2. Verify dynamic import for WorkflowGraphView
    assert "lazy(() => import('./WorkflowGraphView')" in content, "WorkflowGraphView must be lazy loaded"

    # 3. Verify Suspense wrapper
    assert '<Suspense fallback={<Loading label="Загружаем граф процесса…" />}>' in content
    assert "<WorkflowGraphView currentState={item.state} />" in content


def test_r6_url_hash_filter_synchronization():
    """Verify WorkspaceViews.tsx implements URL hash filter synchronization without Web Storage."""
    workspace_views = ROOT / "frontend" / "src" / "views" / "WorkspaceViews.tsx"
    assert workspace_views.exists(), "WorkspaceViews.tsx must exist"
    content = workspace_views.read_text(encoding="utf-8")

    # 1. 152-FZ Zero Web Storage Invariant
    assert "localStorage" not in content, "Forbidden localStorage in WorkspaceViews.tsx"
    assert "sessionStorage" not in content, "Forbidden sessionStorage in WorkspaceViews.tsx"
    assert ".setItem" not in content, "Forbidden .setItem in WorkspaceViews.tsx"
    assert ".getItem" not in content, "Forbidden .getItem in WorkspaceViews.tsx"

    # 2. Verify URL hash parsing
    assert "parseHashFilters" in content, "parseHashFilters helper must exist"
    assert "window.location.hash" in content
    assert "URLSearchParams" in content

    # 3. Verify replaceState and hash serialization
    assert "window.history.replaceState" in content
    assert "#/interactions" in content
    assert "targetHash" in content or "#/interactions?" in content

    # 4. Verify hashchange event listener
    assert "window.addEventListener('hashchange'" in content
    assert "window.removeEventListener('hashchange'" in content

    # 5. Verify reset button clears URL hash back to #/interactions
    assert "memoryFiltersCache = null" in content
    assert "'#/interactions'" in content


def test_r6_bundle_chunks_and_size_limits():
    """Verify frontend build emits separate chunks and main bundle is < 500 kB."""
    dist_assets = ROOT / "frontend" / "dist" / "assets"
    assert dist_assets.exists(), "frontend/dist/assets must exist. Run `npm run build` first."

    js_files = list(dist_assets.glob("*.js"))
    assert len(js_files) >= 5, f"Expected at least 5 split chunks, found {len(js_files)}"

    chunk_names = [f.name for f in js_files]
    assert any("WorkflowGraphView" in name for name in chunk_names), "WorkflowGraphView chunk missing"
    assert any("Reports" in name for name in chunk_names), "Reports chunk missing"
    assert any("InteractionPage" in name for name in chunk_names), "InteractionPage chunk missing"
    assert any("IntegrationsView" in name for name in chunk_names), "IntegrationsView chunk missing"
    assert any("ReferenceViews" in name for name in chunk_names), "ReferenceViews chunk missing"

    # Main index chunk must be strictly under 500 kB (512,000 bytes)
    index_chunks = [f for f in js_files if f.name.startswith("index-")]
    assert index_chunks, "Main index-*.js chunk missing"
    for chunk in index_chunks:
        size = chunk.stat().st_size
        assert size < 500 * 1024, f"Main chunk {chunk.name} exceeds 500 kB ({size} bytes)"
