"""1688 image URL extraction and download helpers."""

import json
import random
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from base_alibaba.storage.paths import CHROME_PROFILE_DIR, COOKIES_FILE, IMAGES_DIR
from base_alibaba.utils.text import sanitize_dirname

_IMG_EXTRACT_JS = """
() => {
    const seen = new Set();
    const result = [];
    const skipPat = /(_50x50|_60x60|_80x80|_100x100|favicon|logo|avatar|iconfont|icon|\.ico)/i;
    const imgPat = /(https?:)?\\/\\/[^"'<>\\s]+alicdn\\.com[^"'<>\\s]+?\\.(?:jpg|jpeg|png|webp)(?:\\?[^"'<>\\s]*)?/ig;

    function normalize(raw) {
        if (!raw) return null;
        let s = String(raw)
            .replace(/&amp;/g, '&')
            .replace(/\\\\u002F/g, '/')
            .replace(/\\\\\\//g, '/')
            .trim();
        s = s.split(/\\s+/)[0];  // srcset 対応
        if (s.startsWith('//')) s = 'https:' + s;
        if (!/^https?:\\/\\//i.test(s)) return null;
        s = s.split('#')[0].split('?')[0];
        if (!/alicdn\\.com/i.test(s) || !/\\.(jpg|jpeg|png|webp)$/i.test(s)) return null;
        if (skipPat.test(s)) return null;
        return s;
    }

    function add(raw) {
        const s = normalize(raw);
        if (s && !seen.has(s)) {
            seen.add(s);
            result.push(s);
        }
    }

    // ① 1688 商品ギャラリー専用セレクタ（最優先）
    const gallerySels = [
        '.detail-gallery-img img',
        '.gallery-image img',
        '.img-gallery img',
        '[class*="gallery"] img',
        '[class*="swiper"] img',
        '.detail-main-img-wrap img',
        '.main-images img',
        '.product-image img',
        '[class*="main-img"] img',
        '[class*="pic-box"] img',
        '.J_ImgBooth',
        '[data-gallery-image]',
    ];
    for (const sel of gallerySels) {
        document.querySelectorAll(sel).forEach(el => {
            ['src','data-src','data-lazy','data-original','data-img'].forEach(attr => {
                add(el.getAttribute(attr) || '');
            });
        });
    }

    // ② naturalWidth >= 400 px の img のみ（ロゴ・アイコン排除）
    if (result.length < 3) {
        document.querySelectorAll('img').forEach(el => {
            const w = el.naturalWidth || el.width || 0;
            if (w >= 400) {
                ['src','data-src','data-lazy','data-original','data-img'].forEach(attr => {
                    add(el.getAttribute(attr) || '');
                });
            }
        });
    }

    // ③ HTML全体からalicdn URL抽出（フォールバック）
    if (result.length < 3) {
        const html = document.documentElement.innerHTML;
        let match;
        while ((match = imgPat.exec(html)) !== null) add(match[0]);
        // サイズ付きURLを優先
        const large = result.filter(u => /_(\\d{3,4}x\\d{3,4}|800|1000|900)/.test(u));
        if (large.length >= 3) return large.slice(0, 15);
    }

    return result.slice(0, 15);
}
"""

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15",
]
_ACCEPT_LANGUAGE = "zh-CN,zh;q=0.9,ja-JP;q=0.8,ja;q=0.7,en-US;q=0.6,en;q=0.5"
_SMALL_IMG_PAT = re.compile(
    r'(_50x50|_60x60|_80x80|_100x100|_120x120|favicon|/logo|/icon|avatar|iconfont)',
    re.IGNORECASE,
)
_ALICDN_HTML_PAT = re.compile(
    r'(https?:)?//[^\s"\'<>\\]+?alicdn\.com[^\s"\'<>\\]+?\.(?:jpg|jpeg|png|webp)',
    re.IGNORECASE,
)
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
    // webdriver を完全に消す
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
        configurable: true,
    });
    try { delete navigator.__proto__.webdriver; } catch(_) {}

    // 自動化フラグを消す
    delete window.__nightmare;
    delete window._phantom;
    delete window.callPhantom;
    delete window.__selenium_evaluate;
    delete window.__webdriver_evaluate;
    delete window.__driver_evaluate;
    delete window.__webdriver_script_func;
    delete window.__webdriverFunc;
    delete window.domAutomation;
    delete window.domAutomationController;

    // navigator プロパティ偽装
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'ja-JP', 'ja', 'en-US', 'en'] });
    Object.defineProperty(navigator, 'platform', { get: () => 'MacIntel' });
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
    Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 0 });
    Object.defineProperty(navigator, 'appVersion', {
        get: () => '5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
    });
    Object.defineProperty(navigator, 'vendor', { get: () => 'Google Inc.' });

    // plugins を本物らしく偽装
    const makePlugin = (name, filename, description, mimeTypes) => {
        const plugin = Object.create(Plugin.prototype);
        Object.defineProperty(plugin, 'name', { get: () => name });
        Object.defineProperty(plugin, 'filename', { get: () => filename });
        Object.defineProperty(plugin, 'description', { get: () => description });
        Object.defineProperty(plugin, 'length', { get: () => mimeTypes.length });
        return plugin;
    };
    const fakePlugins = [
        makePlugin('PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format', ['application/pdf']),
        makePlugin('Chrome PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format', ['application/pdf']),
        makePlugin('Chromium PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format', ['application/pdf']),
        makePlugin('Microsoft Edge PDF Viewer', 'internal-pdf-viewer', 'Portable Document Format', ['application/pdf']),
        makePlugin('WebKit built-in PDF', 'internal-pdf-viewer', 'Portable Document Format', ['application/pdf']),
    ];
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const arr = [...fakePlugins];
            arr.__proto__ = PluginArray.prototype;
            Object.defineProperty(arr, 'item', { value: (i) => arr[i] });
            Object.defineProperty(arr, 'namedItem', { value: (n) => arr.find(p => p.name === n) || null });
            Object.defineProperty(arr, 'refresh', { value: () => {} });
            Object.defineProperty(arr, 'length', { get: () => fakePlugins.length });
            return arr;
        },
    });

    // chrome オブジェクトを本物らしく
    const chrome = {
        app: {
            isInstalled: false,
            InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
            RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
        },
        runtime: {
            OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install', SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
            OnRestartRequiredReason: { APP_UPDATE: 'app_update', GC_POLICY: 'gc_policy', OS_UPDATE: 'os_update' },
            PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64', X86_32: 'x86-32', X86_64: 'x86-64' },
            PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux', MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
            RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled', UPDATE_AVAILABLE: 'update_available' },
        },
        csi: () => ({ onloadT: Date.now(), pageT: Date.now(), startE: Date.now(), tran: 15 }),
        loadTimes: () => ({
            commitLoadTime: Date.now() / 1000 - 0.5,
            connectionInfo: 'h2',
            finishDocumentLoadTime: Date.now() / 1000 - 0.1,
            finishLoadTime: Date.now() / 1000,
            firstPaintAfterLoadTime: 0,
            firstPaintTime: Date.now() / 1000 - 0.3,
            navigationType: 'Other',
            npnNegotiatedProtocol: 'h2',
            requestTime: Date.now() / 1000 - 1,
            startLoadTime: Date.now() / 1000 - 1,
            wasAlternateProtocolAvailable: false,
            wasFetchedViaSpdy: true,
            wasNpnNegotiated: true,
        }),
    };
    if (!window.chrome) window.chrome = chrome;
    else Object.assign(window.chrome, chrome);

    // permissions.query の通知チェックを無害化
    const origQuery = window.navigator.permissions && window.navigator.permissions.query.bind(window.navigator.permissions);
    if (origQuery) {
        window.navigator.permissions.query = (params) =>
            params && params.name === 'notifications'
                ? Promise.resolve({ state: 'default', onchange: null })
                : origQuery(params);
    }

    // WebGL レンダラー偽装
    if (window.WebGLRenderingContext) {
        const getParam = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(p) {
            if (p === 37445) return 'Intel Inc.';
            if (p === 37446) return 'Intel Iris Pro OpenGL Engine';
            return getParam.call(this, p);
        };
    }
    if (window.WebGL2RenderingContext) {
        const getParam2 = WebGL2RenderingContext.prototype.getParameter;
        WebGL2RenderingContext.prototype.getParameter = function(p) {
            if (p === 37445) return 'Intel Inc.';
            if (p === 37446) return 'Intel Iris Pro OpenGL Engine';
            return getParam2.call(this, p);
        };
    }

    // Notification を偽装
    try {
        Object.defineProperty(Notification, 'permission', { get: () => 'default' });
    } catch(_) {}
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


_CHROME_EXECUTABLE = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

_CHROME_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-infobars",
    "--no-first-run",
    "--no-default-browser-check",
    "--lang=zh-CN",
    "--window-size=1366,768",
]
_IGNORE_DEFAULT_ARGS = ["--enable-automation", "--enable-blink-features=IdleDetection"]


def _browser_launch_args(headless: bool) -> dict:
    options = {
        "headless": headless,
        "args": _CHROME_LAUNCH_ARGS,
        "ignore_default_args": _IGNORE_DEFAULT_ARGS,
    }
    if not headless:
        options["slow_mo"] = random.randint(50, 130)
    return options


def _launch_chromium(playwright, headless: bool):
    """Playwrightバンドル Chromium を起動する。
    macOS では既存 Chrome との singleton 競合が起きるため、
    real Chrome / channel='chrome' は使わない。
    """
    options = _browser_launch_args(headless)
    return playwright.chromium.launch(**options)


def _apply_stealth(page):
    try:
        from playwright_stealth import Stealth
        Stealth().apply_stealth_sync(page)
    except Exception:
        pass
    page.add_init_script(_STEALTH_INIT_SCRIPT)


def _human_wait(page, min_ms: int = 700, max_ms: int = 1800):
    import time as _t
    _t.sleep(random.randint(min_ms, max_ms) / 1000)


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
    """alicdn画像をurllib直接DL。20KB未満は失敗扱い（ロゴ・プレースホルダー排除）。"""
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
        if len(data) < 20_000:
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


def _persistent_context_options() -> dict:
    """launch_persistent_context 共通オプション。"""
    return {
        "headless": False,
        "args": _CHROME_LAUNCH_ARGS,
        "ignore_default_args": _IGNORE_DEFAULT_ARGS,
        "slow_mo": random.randint(60, 150),
        **_browser_context_options(),
    }


def _clear_chrome_profile_locks():
    """起動前に古い SingletonLock 等を削除してプロファイル競合を防ぐ。"""
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket", "RunningChromeVersion"):
        p = CHROME_PROFILE_DIR / name
        try:
            if p.is_symlink() or p.exists():
                p.unlink()
        except OSError:
            pass


def _launch_persistent_ctx(playwright):
    """本物のChromeで persistent context を起動する。なければ Chromium。"""
    import os
    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _clear_chrome_profile_locks()
    opts = _persistent_context_options()
    if os.path.exists(_CHROME_EXECUTABLE):
        try:
            return playwright.chromium.launch_persistent_context(
                str(CHROME_PROFILE_DIR), executable_path=_CHROME_EXECUTABLE, **opts
            )
        except Exception as e:
            print(f"   [Chrome] 起動失敗、Chromiumにフォールバック: {e!s:.120}")
    try:
        return playwright.chromium.launch_persistent_context(
            str(CHROME_PROFILE_DIR), channel="chrome", **opts
        )
    except Exception:
        pass
    return playwright.chromium.launch_persistent_context(str(CHROME_PROFILE_DIR), **opts)


def cmd_images_login(_args):
    """永続Chromeプロファイルでログインし、以降の自動取得を可能にする。"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwrightが未導入です:")
        print("   pip install playwright && python -m playwright install chromium")
        return

    print("🌐 1688ログイン用ブラウザを起動します。")
    print("   ① QRコードをスキャン or パスワードでログイン")
    print("   ② ログイン完了後、このターミナルで Enter を押してください\n")

    with sync_playwright() as p:
        try:
            ctx = _launch_persistent_ctx(p)
        except Exception as e:
            if _is_playwright_browser_missing_error(e):
                print("❌ Chromiumが未導入です: python -m playwright install chromium")
            else:
                print(f"❌ ブラウザを起動できませんでした: {e}")
            return

        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            _apply_stealth(page)

            # セッション実検証：www.1688.com にアクセスしてログイン済みか確認
            session_valid = False
            try:
                page.goto("https://www.1688.com/", wait_until="domcontentloaded", timeout=30000)
                _sleep(random.uniform(2.0, 3.0))
                cur = page.url
                if "login.taobao.com" not in cur and "login.1688.com" not in cur and _has_auth_cookie(ctx.cookies()):
                    session_valid = True
            except Exception:
                pass

            if session_valid:
                print("✅ すでにログイン済みです。python tool.py images download を実行してください。")
                COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
                ctx.storage_state(path=str(COOKIES_FILE))
                return

            print("   セッション期限切れ。ログインページへ移動します…")

            # ログインページへ
            login_url = (
                "https://login.taobao.com/member/login.jhtml"
                "?redirectURL=https%3A%2F%2Fwww.1688.com%2F"
            )
            try:
                page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
                _human_wait(page, 2500, 4000)
                _reload_blank_login_page(page, "login")
            except Exception as e:
                print(f"⚠️  ログインページの読み込みに失敗しました: {e}")
                _save_login_debug_screenshot(page, "login_goto_failed")

            if sys.stdin.isatty():
                try:
                    input("ログインが完了したら Enter を押してください: ")
                except EOFError:
                    print("❌ 標準入力が閉じられました。通常のターミナルで再実行してください。")
                    return
            else:
                import time as _time
                print("   ブラウザでQRコードをスキャンしてください（最大180秒）…")
                deadline = _time.monotonic() + 180
                while _time.monotonic() < deadline:
                    _time.sleep(2)
                    try:
                        page.evaluate("null")
                    except Exception:
                        print("   ⚠️ ブラウザが閉じられました")
                        break
                    # ログイン済みになったら早期終了
                    try:
                        if _has_auth_cookie(ctx.cookies()):
                            print("   ✅ ログイン検出、続行します")
                            break
                    except Exception:
                        break

            # ログイン確認
            try:
                page.goto("https://www.1688.com/", wait_until="domcontentloaded", timeout=30000)
                _human_wait(page, 1500, 2500)
            except Exception:
                pass

            cookies = ctx.cookies()
            cur = page.url
            title = ""
            try:
                title = page.title()
            except Exception:
                pass

            captcha = "punish" in cur or "验证码" in title or "captcha" in title.lower()
            still_login = "login.1688.com" in cur or "login.taobao.com" in cur

            if captcha:
                print("❌ CAPTCHA検出。ブラウザで解除後、再度 images login を実行してください。")
                _save_login_debug_screenshot(page, "captcha")
                return

            if still_login or not _has_auth_cookie(cookies):
                print("❌ ログイン完了を確認できませんでした。QRログイン後にもう一度実行してください。")
                _save_login_debug_screenshot(page, "not_confirmed")
                return

            # プロファイルはpersistent contextが自動保存。JSONも念のため保存。
            COOKIES_FILE.parent.mkdir(parents=True, exist_ok=True)
            ctx.storage_state(path=str(COOKIES_FILE))
            print(f"✅ ログイン完了。プロファイル: {CHROME_PROFILE_DIR}")
            print("   次に実行: python tool.py images download")

        finally:
            ctx.close()


def _sleep(seconds: float):
    import time as _t
    _t.sleep(seconds)


def _fetch_one_product(page, product_url: str, img_dir: Path) -> tuple[int, str]:
    """既存のページオブジェクトで1商品を取得する（バッチ処理内部用）。"""
    try:
        page.goto(product_url, wait_until="domcontentloaded", timeout=45000)
    except Exception as e:
        return 0, f"error:{e}"
    _sleep(random.uniform(3.0, 5.0))

    cur = page.url
    if "login.taobao.com" in cur or "login.1688.com" in cur:
        return 0, "session_expired"

    title = page.title()
    if "punish" in cur or "验证码" in title or "captcha" in title.lower():
        print("   🔒 CAPTCHAが表示されました。ブラウザで解除後、Enterを押してください。")
        try:
            input("   ブラウザでCAPTCHAを解除したら Enter: ")
        except EOFError:
            print("   120秒待機します（ブラウザで解除してください）…")
            _sleep(120)
        _sleep(random.uniform(2.0, 3.0))
        cur = page.url
        title = page.title()
        if "punish" in cur or "验証码" in title or "captcha" in title.lower():
            return 0, "captcha"

    for y in [400, 800, 1200, 1600]:
        page.evaluate(f"window.scrollTo(0, {y})")
        _sleep(random.uniform(0.6, 1.4))

    urls: list[str] = page.evaluate(_IMG_EXTRACT_JS) or []
    urls = [u for u in (_normalize_image_url(u) for u in urls) if u]
    if not urls:
        return 0, "no_images"

    img_dir.mkdir(parents=True, exist_ok=True)
    ok = _bulk_download(urls, img_dir)
    return ok, ("ok" if ok else "download_failed")


def batch_download_with_profile(
    tasks: list[tuple[str, Path]],
) -> list[tuple[int, str]]:
    """1つのブラウザセッションで複数商品を順番にダウンロードする。

    persistent_context は macOS で既存 Chrome と衝突するため使わず、
    regular launch + storage_state (COOKIES_FILE) を使う。
    """
    if not COOKIES_FILE.exists() and not CHROME_PROFILE_DIR.exists():
        return [(0, "profile_not_found")] * len(tasks)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [(0, "playwright_not_installed")] * len(tasks)

    results: list[tuple[int, str]] = []

    with sync_playwright() as p:
        # regular launch — プロファイル競合なし
        try:
            browser = _launch_chromium(p, headless=False)
        except Exception as e:
            status = "playwright_browser_not_installed" if _is_playwright_browser_missing_error(e) else f"error:{e}"
            return [(0, status)] * len(tasks)

        try:
            ctx_opts = _browser_context_options()
            if COOKIES_FILE.exists():
                try:
                    ctx = browser.new_context(storage_state=str(COOKIES_FILE), **ctx_opts)
                except Exception:
                    ctx = browser.new_context(**ctx_opts)
            else:
                ctx = browser.new_context(**ctx_opts)

            page = ctx.new_page()
            _apply_stealth(page)

            import time as _time
            for i, (url, img_dir) in enumerate(tasks):
                if not _is_1688_detail_url(url):
                    results.append((0, "not_detail_url"))
                    continue

                if i > 0:
                    wait_s = random.uniform(3.0, 6.0)
                    print(f"   ⏳ {wait_s:.1f}秒待機中…")
                    _time.sleep(wait_s)

                ok, status = _fetch_one_product(page, url, img_dir)
                results.append((ok, status))

        except Exception as e:
            while len(results) < len(tasks):
                results.append((0, f"error:{e}"))
        finally:
            try:
                browser.close()
            except Exception:
                pass

    return results


def _playwright_download_with_profile(product_url: str, img_dir: Path) -> tuple[int, str]:
    """単一商品用ラッパー（後方互換）。"""
    res = batch_download_with_profile([(product_url, img_dir)])
    return res[0]


def _playwright_download(product_url: str, img_dir: Path, headless: bool = False, interactive: bool = False) -> tuple[int, str]:
    """Cookie JSONを使った旧方式ダウンロード（フォールバック用）。"""
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


def _dl_image(url: str, dest: Path) -> bool:
    return _urllib_download(url, dest)


def _extract_images_from_html(html: str) -> list[str]:
    """HTML文字列からalicdn.com商品画像URLを抽出して返す。"""
    seen: set[str] = set()
    result: list[str] = []

    for match in _ALICDN_HTML_PAT.finditer(html):
        raw = match.group(0)
        # JSON内のエスケープ (\/) を修正
        raw = raw.replace("\\/", "/").replace("\\u002F", "/")
        url = _normalize_image_url(raw)
        if url and url not in seen and not _SMALL_IMG_PAT.search(url):
            seen.add(url)
            result.append(url)

    # サイズ付き（_720x720 等）を優先。なければ全件
    large = [u for u in result if re.search(r'_\d{3,4}x\d{3,4}', u)]
    return (large or result)[:15]


def _requests_extract_images(product_url: str) -> tuple[list[str], str]:
    """requestsで1688商品ページを取得し画像URLを抽出する（ログイン不要・CAPTCHA回避）。

    Returns:
        (image_urls, status)  status: "ok" | "login_required" | "captcha" |
                              "no_images" | "not_detail_url" | "requests_not_installed" |
                              "http_NNN" | "error:..."
    """
    if not _is_1688_detail_url(product_url):
        return [], "not_detail_url"

    try:
        import requests as _req
    except ImportError:
        return [], "requests_not_installed"

    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,ja;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Referer": "https://www.1688.com/",
    }

    # 保存済みCookieがあれば付与
    req_cookies: dict[str, str] = {}
    if COOKIES_FILE.exists():
        try:
            cookie_list = _cookie_list_from_state(_load_saved_cookie_state())
            parsed = urllib.parse.urlparse(product_url)
            host = parsed.hostname or ""
            for c in cookie_list:
                domain = str(c.get("domain", "")).lstrip(".")
                n, v = c.get("name"), c.get("value")
                if domain and n and v is not None:
                    if host == domain or host.endswith(f".{domain}"):
                        req_cookies[n] = str(v)
        except Exception:
            pass

    try:
        session = _req.Session()
        resp = session.get(
            product_url,
            headers=headers,
            cookies=req_cookies or None,
            timeout=30,
            allow_redirects=True,
        )
    except Exception as e:
        return [], f"error:{e}"

    if resp.status_code != 200:
        return [], f"http_{resp.status_code}"

    final_url = resp.url
    html = resp.text

    if "login.taobao.com" in final_url or "login.1688.com" in final_url:
        return [], "login_required"
    if any(x in html for x in ["验证码", "punish", "captcha"]):
        return [], "captcha"

    urls = _extract_images_from_html(html)
    return (urls, "ok") if urls else ([], "no_images")
