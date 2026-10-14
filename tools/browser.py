from config import BROWSER_ENABLED, BROWSER_HEADLESS, BROWSER_PROFILE_DIR, MAX_READ_CHARS

_SESSION = None


def _browser():
    global _SESSION
    if _SESSION is not None:
        return _SESSION, None
    if not BROWSER_ENABLED:
        return None, "Browser access is disabled. Set RUBI_BROWSER_ENABLED=true to enable it."
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "Browser access needs Playwright. Install the browser dependencies first."
    playwright = sync_playwright().start()
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(str(BROWSER_PROFILE_DIR), headless=BROWSER_HEADLESS)
    page = context.pages[0] if context.pages else context.new_page()
    _SESSION = (playwright, context, page)
    return _SESSION, None


def close_browser():
    global _SESSION
    if _SESSION is None:
        return "The Rubi browser is not open."
    playwright, context, _page = _SESSION
    try:
        context.close()
        playwright.stop()
    finally:
        _SESSION = None
    return "Rubi browser closed."


def open_browser(url):
    if not str(url).startswith(("http://", "https://")):
        return "Error: browser URLs must start with http:// or https://."
    browser, error = _browser()
    if error:
        return error
    playwright, context, page = browser
    try:
        response = page.goto(str(url), wait_until="domcontentloaded", timeout=30000)
        return f"Opened {page.url} (HTTP {response.status if response else 'unknown'})."
    except Exception as exc:
        return f"Browser error: {exc}"


def read_browser_page(url):
    if not str(url).startswith(("http://", "https://")):
        return "Error: browser URLs must start with http:// or https://."
    browser, error = _browser()
    if error:
        return error
    playwright, context, page = browser
    try:
        page.goto(str(url), wait_until="domcontentloaded", timeout=30000)
        text = " ".join(page.locator("body").inner_text(timeout=10000).split())
        return f"Page: {page.title()}\nURL: {page.url}\n\n{text[:MAX_READ_CHARS]}"
    except Exception as exc:
        return f"Browser error: {exc}"
