"""1688 image URL extraction and download helpers."""

import json
import random
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from base_alibaba.storage.paths import COOKIES_FILE, IMAGES_DIR
from base_alibaba.utils.text import sanitize_dirname

_IMG_EXTRACT_JS = """
() => {
    const seen = new Set();
    const result = [];
    const smallPat = /(_50x50|_60x60|_80x80|_100x100|favicon|logo|avatar|iconfont)/i;
    const imgPat = /(https?:)?\\/\\/[^"'<>\\s]+alicdn\\.com[^"'<>\\s]+?\\.(?:jpg|jpeg|png|webp)(?:\\?[^"'<>\\s]*)?/ig;

    function normalize(raw) {
        if (!raw) return null;
        let s = String(raw)
            .replace(/&amp;/g, '&')
            .replace(/\\\\u002F/g, '/')
            .replace(/\\\\\\//g, '/')
            .trim();
        if (s.startsWith('//')) s = 'https:' + s;
        if (!/^https?:\\/\\//i.test(s)) return null;
        s = s.split('#')[0].split('?')[0];
        if (!/alicdn\\.com/i.test(s) || !/\\.(jpg|jpeg|png|webp)$/i.test(s)) return null;
        if (smallPat.test(s)) return null;
        return s;
    }

    function add(raw) {
        const s = normalize(raw);
        if (s && !seen.has(s)) {
            seen.add(s);
            result.push(s);
        }
    }

    document.querySelectorAll('img, source').forEach(el => {
        ['src','data-src','data-lazy','data-original','data-img','srcset'].forEach(attr => {
            const value = el.getAttribute(attr) || '';
            value.split(',').forEach(part => add(part.trim().split(/\\s+/)[0]));
        });
    });

    document.querySelectorAll('[style]').forEach(el => {
        const style = el.getAttribute('style') || '';
        let match;
        while ((match = imgPat.exec(style)) !== null) add(match[0]);
    });

    const html = document.documentElement.innerHTML;
    let match;
    while ((match = imgPat.exec(html)) !== null) add(match[0]);

    return result.slice(0, 15);
}
"""

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)
_ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,ja-JP;q=0.8,ja;q=0.7,en-US;q=0.6,en;q=0.5"
_IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp")
_AUTH_COOKIE_NAMES = {
    "_nk_",
    "cookie2",
    "cookie17",
    "lgc",
    "lid",
    "login_aliyunid_ticket",
    "munb",
    "sgcookie",
    "skt",
    "t",
    "tracknick",
    "uc1",
    "uc3",
    "unb",
}
_STEALTH_INIT_SCRIPT = """
(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'ja-JP', 'ja', 'en-US', 'en'] });
    Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            { name: 'Chrome PDF Plugin' },
            { name: 'Chrome PDF Viewer' },
            { name: 'Native Client' },
        ],
    });

    window.chrome = window.chrome || {};
    window.chrome.runtime = window.chrome.runtime || {};
    window.chrome.app = window.chrome.app || {};

    const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
    if (originalQuery) {
        window.navigator.permissions.query = (parameters) => (
            parameters && parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery.call(window.navigator.permissions, parameters)
        );
    }

    if (window.WebGLRenderingContext) {
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter.call(this, parameter);
        };
    }
})();
"""


def _sanitize_dirname(name: str) -> str:
    return sanitize_dirname(name)


def _is_1688_detail_url(url: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    return host.endswith("1688.com") and "/offer/" in path and path.endswith(".html")


def _normalize_image_url(url: str) -> str | None:
    url = url.strip().replace("&amp;", "&")
    if url.startswith("//"):
        url = "https:" + url
    if not url.startswith(("http://", "https://")):
        return None
    url = url.split("#")[0].split("?")[0]
    if "alicdn.com" not in url.lower():
        return None
    if not re.search(r"\.(jpg|jpeg|png|webp)$", url, re.IGNORECASE):
        return None
    return url


def _browser_context_options() -> dict:
    return {
        "user_agent": _USER_AGENT,
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "viewport": {"width": 1366, "height": 768},
        "screen": {"width": 1440, "height": 900},
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
        "java_script_enabled": True,
        "extra_http_headers": {
            "Accept-Language": _ACCEPT_LANGUAGE,
            "Upgrade-Insecure-Requests": "1",
        },
    }


def _browser_launch_args(headless: bool) -> dict:
    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-popup-blocking",
        "--disable-notifications",
        "--disable-extensions",
        "--no-first-run",
        "--no-default-browser-check",
        "--lang=zh-CN",
        "--window-size=1366,768",
    ]
    options = {
        "headless": headless,
        "args": args,
        "ignore_default_args": ["--enable-automation"],
    }
    if not headless:
        options["slow_mo"] = random.randint(40, 110)
    return options


def _launch_chromium(playwright, headless: bool):
    """Prefer the user's normal Chrome for login, then fall back to bundled Chromium."""
    options = _browser_launch_args(headless)
    if not headless:
        try:
            return playwright.chromium.launch(channel="chrome", **options)
        except Exception:
            pass
    return playwright.chromium.launch(**options)


def _apply_stealth(page):
    page.add_init_script(_STEALTH_INIT_SCRIPT)


def _human_wait(page, min_ms: int = 700, max_ms: int = 1800):
    page.wait_for_timeout(random.randint(min_ms, max_ms))


def _debug_login_path() -> Path:
    return IMAGES_DIR.parent / "debug_login.png"


def _page_html_head(page, limit: int = 200) -> str:
    try:
        html = page.content()
    except Exception as e:
        return f"<HTML取得失敗: {e}>"
    return " ".join(html[:limit].split())


def _log_page_state(page, label: str):
    try:
        title = page.title()
    except Exception as e:
        title = f"<取得失敗: {e}>"
    try:
        current_url = page.url
    except Exception as e:
        current_url = f"<取得失敗: {e}>"
    print(f"   [{label}] title: {title}")
    print(f"   [{label}] url: {current_url}")
    print(f"   [{label}] html[0:200]: {_page_html_head(page)}")


def _is_blank_page(page) -> bool:
    try:
        state = page.evaluate(
            """() => ({
                htmlLength: document.documentElement.outerHTML.length,
                bodyTextLength: (document.body && document.body.innerText || '').trim().length,
                bodyChildren: document.body ? document.body.children.length : 0,
            })"""
        )
    except Exception:
        return False
    return (
        int(state.get("htmlLength", 0)) < 300
        or (int(state.get("bodyTextLength", 0)) == 0 and int(state.get("bodyChildren", 0)) == 0)
    )


def _save_login_debug_screenshot(page, reason: str):
    path = _debug_login_path()
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"   📸 debug screenshot saved: {path} ({reason})")
    except Exception as e:
        print(f"   ⚠️  debug screenshot保存失敗: {e} ({reason})")


def _reload_blank_login_page(page, label: str, timeout_ms: int = 90000) -> bool:
    if not _is_blank_page(page):
        return False
    print(f"   ⚠️  {label}: 真っ白ページの可能性があります。reloadを1回試します。")
    try:
        page.reload(wait_until="domcontentloaded", timeout=timeout_ms)
        _human_wait(page, 2500, 3500)
        _log_page_state(page, f"{label} reload後")
        return True
    except Exception as e:
        print(f"   ❌ reload失敗: {e}")
        _save_login_debug_screenshot(page, "reload_failed")
        return False


def _new_context_with_saved_cookies(browser):
    """Create a context from Playwright storage_state or legacy cookie-list JSON."""
    state = _load_saved_cookie_state()
    if isinstance(state, dict):
        return browser.new_context(storage_state=str(COOKIES_FILE), **_browser_context_options())

    if isinstance(state, list):
        ctx = browser.new_context(**_browser_context_options())
        ctx.add_cookies(state)
        return ctx

    raise RuntimeError("invalid_cookie_file:unsupported format")


def _load_saved_cookie_state():
    try:
        with open(COOKIES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise RuntimeError(f"invalid_cookie_file:{e}") from e


def _cookie_list_from_state(state) -> list[dict]:
    if isinstance(state, dict):
        cookies = state.get("cookies", [])
        return cookies if isinstance(cookies, list) else []
    if isinstance(state, list):
        return state
    return []


def _has_auth_cookie(cookies: list[dict]) -> bool:
    names = {str(cookie.get("name", "")).lower() for cookie in cookies}
    return bool(names & _AUTH_COOKIE_NAMES)


def _saved_cookie_header_for_url(url: str) -> str:
    if not COOKIES_FILE.exists():
        return ""
    try:
        cookies = _cookie_list_from_state(_load_saved_cookie_state())
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return ""

    host = parsed.hostname or ""
    pairs = []
    for cookie in cookies:
        domain = str(cookie.get("domain", "")).lstrip(".")
        name = cookie.get("name")
        value = cookie.get("value")
        if not domain or not name or value is None:
            continue
        if host == domain or host.endswith(f".{domain}"):
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _is_cookie_state_error(error: Exception) -> bool:
    text = str(error)
    return "storage_state" in text or "JSON" in text or "invalid_cookie_file" in text


def _is_playwright_browser_missing_error(error: Exception) -> bool:
    text = str(error)
    return "Executable doesn't exist" in text or "playwright install" in text

def _urllib_download(url: str, dest: Path) -> bool:
    """alicdn画像をurllib直接DL（ログイン不要）。2KB未満は失敗扱い。"""
    try:
        normalized = _normalize_image_url(url)
        if not normalized:
            return False
        headers = {
            "User-Agent": _USER_AGENT,
            "Referer":    "https://detail.1688.com/",
        }
        cookie_header = _saved_cookie_header_for_url(normalized)
        if cookie_header:
            headers["Cookie"] = cookie_header
        req = urllib.request.Request(normalized, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
        if len(data) < 2000:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False

def _playwright_extract_urls(product_url: str, headless: bool = True) -> tuple[list[str], str]:
    """Playwrightでページを描画しalicdn画像URLを抽出する。
    URL抽出のみ担当。DLはurllib（_urllib_download）で行う。
    返り値: (image_urls, status)
      status: "ok" | "login_required" | "session_expired" | "captcha" |
              "not_detail_url" | "no_images" | "playwright_not_installed" | "error:..."
    """
    if not _is_1688_detail_url(product_url):
        return [], "not_detail_url"
    if not COOKIES_FILE.exists():
        return [], "not_logged_in"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], "playwright_not_installed"

    with sync_playwright() as p:
        browser = None
        try:
            browser = _launch_chromium(p, headless=headless)
            ctx = _new_context_with_saved_cookies(browser)
            page = ctx.new_page()
            _apply_stealth(page)
            _human_wait(page)
            page.goto(product_url, wait_until="domcontentloaded", timeout=35000)
            _human_wait(page, 2500, 4500)

            cur = page.url
            if "login.taobao.com" in cur or "login.1688.com" in cur:
                return [], "session_expired"
            title = page.title()
            if "punish" in cur or "验证码" in title or "captcha" in title.lower():
                return [], "captcha"

            # スクロールで遅延読み込みを発火
            for y in [400, 800, 1200]:
                page.evaluate(f"window.scrollTo(0, {y})")
                _human_wait(page, 500, 1300)

            urls: list[str] = page.evaluate(_IMG_EXTRACT_JS) or []
            urls = [u for u in (_normalize_image_url(url) for url in urls) if u]
            return (urls, "ok") if urls else ([], "no_images")

        except Exception as e:
            if _is_playwright_browser_missing_error(e):
                return [], "playwright_browser_not_installed"
            if _is_cookie_state_error(e):
                return [], "session_expired"
            return [], f"error:{e}"
        finally:
            if browser:
                browser.close()

def _bulk_download(img_urls: list[str], save_dir: Path) -> int:
    """URLリストをurllib直接DLしてファイルに保存。成功枚数を返す。"""
    ok = 0
    for i, url in enumerate(img_urls, 1):
        ext = next((e for e in _IMAGE_EXTENSIONS if url.lower().endswith(f".{e}")), "jpg")
        if ext == "jpeg":
            ext = "jpg"
        dest = save_dir / f"{i:02d}.{ext}"
        if _urllib_download(url, dest):
            ok += 1
            print(f"   ✅ {dest.name}  ({dest.stat().st_size // 1024}KB)")
        else:
            print(f"   ❌ DL失敗: {url[:70]}...")
    return ok


def cmd_images_login(_args):
    """Open a browser for QR login and save Playwright storage_state."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwrightが未導入です。以下を実行してください:")
        print("   python -m pip install playwright")
        print("   python -m playwright install chromium")
        return

    COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    print("🌐 1688ログイン用ブラウザを開きます。QRコードでログインしてください。")
    print("   ログイン完了後、このターミナルで Enter を押すとCookieを保存します。")

    with sync_playwright() as p:
        browser = None
        try:
            browser = _launch_chromium(p, headless=False)
            ctx = browser.new_context(
                **_browser_context_options(),
            )
            page = ctx.new_page()
            _apply_stealth(page)
        except Exception as e:
            if browser:
                browser.close()
            if _is_playwright_browser_missing_error(e):
                print("❌ PlaywrightのChromiumブラウザが未導入です。以下を実行してください:")
                print("   python -m playwright install chromium")
            else:
                print(f"❌ ブラウザを起動できませんでした: {e}")
            return

        try:
            page.goto("https://www.1688.com/", wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(3000)
            _log_page_state(page, "1688トップ")
            _reload_blank_login_page(page, "1688トップ")

            login_url = "https://login.taobao.com/member/login.jhtml?redirectURL=https%3A%2F%2Fwww.1688.com%2F"
            page.goto(login_url, wait_until="domcontentloaded", timeout=90000)
            _human_wait(page, 3000, 4500)
            _log_page_state(page, "taobaoログイン")
            _reload_blank_login_page(page, "taobaoログイン")
        except PlaywrightTimeoutError:
            print("⚠️  ログインページの読み込みがタイムアウトしました。表示済みならそのままログインしてください。")
            _log_page_state(page, "timeout")
            _save_login_debug_screenshot(page, "timeout")
        except Exception as e:
            print(f"❌ ログインページを開けませんでした: {e}")
            _log_page_state(page, "goto_failed")
            _save_login_debug_screenshot(page, "goto_failed")
            browser.close()
            return

        if sys.stdin.isatty():
            try:
                input("ログインが完了したら Enter を押してください: ")
            except EOFError:
                print("❌ 入力が閉じられたため、Cookie保存前に終了します。通常のターミナルで再実行してください。")
                _save_login_debug_screenshot(page, "stdin_eof")
                browser.close()
                return
        else:
            print("   非対話環境のため、最大180秒ログイン完了を待ちます。")
            page.wait_for_timeout(180000)

        try:
            page.goto("https://www.1688.com/", wait_until="domcontentloaded", timeout=90000)
            _human_wait(page, 1500, 3000)
            _log_page_state(page, "ログイン確認")
            _reload_blank_login_page(page, "ログイン確認")
        except Exception:
            _log_page_state(page, "ログイン確認失敗")
            _save_login_debug_screenshot(page, "post_login_check_failed")

        cur = page.url
        title = ""
        try:
            title = page.title()
        except Exception:
            pass
        cookies = ctx.cookies()
        has_auth_cookie = _has_auth_cookie(cookies)
        still_login = "login.1688.com" in cur or "login.taobao.com" in cur
        captcha = "punish" in cur or "验证码" in title or "captcha" in title.lower()

        if captcha:
            print("❌ CAPTCHA/ブロック画面を検出しました。ブラウザで解除後、再度 images login を実行してください。")
            _save_login_debug_screenshot(page, "captcha")
            browser.close()
            return
        if still_login or not has_auth_cookie:
            print("❌ ログイン完了を確認できませんでした。QRログイン後にもう一度実行してください。")
            _save_login_debug_screenshot(page, "login_not_confirmed")
            browser.close()
            return

        ctx.storage_state(path=str(COOKIES_FILE))
        browser.close()
        print(f"✅ Cookieを保存しました: {COOKIES_FILE}")
        print("   次に実行: python tool.py images download")


def _playwright_download(product_url: str, img_dir: Path, headless: bool = False, interactive: bool = False) -> tuple[int, str]:
    try:
        urls, status = _playwright_extract_urls(product_url, headless=headless)
        if status != "ok":
            return 0, status
        ok = _bulk_download(urls, img_dir)
        return ok, "ok" if ok else "download_failed"
    except Exception as e:
        if _is_playwright_browser_missing_error(e):
            return 0, "playwright_browser_not_installed"
        if _is_cookie_state_error(e):
            return 0, "session_expired"
        return 0, f"error:{e}"


def _selenium_download(product_url: str, img_dir: Path) -> tuple[int, str]:
    print("   この機能は未実装です。次に実装してください: Selenium画像取得")
    return 0, "unimplemented"


def _dl_image(url: str, dest: Path) -> bool:
    return _urllib_download(url, dest)
