"""1688 image URL extraction and download helpers."""

import urllib.request
from pathlib import Path

from base_alibaba.storage.paths import COOKIES_FILE, IMAGES_DIR
from base_alibaba.utils.text import sanitize_dirname

_IMG_EXTRACT_JS = """
() => {
    const seen = new Set();
    const result = [];
    const smallPat = /(_50x50|_100x100|_80x80|_60x60|favicon|logo)/i;
    document.querySelectorAll('img').forEach(el => {
        ['src','data-src','data-lazy','data-original'].forEach(attr => {
            const s = (el.getAttribute(attr) || '').split('?')[0];
            if (s.includes('alicdn') && /\\.(jpg|jpeg|png|webp)/i.test(s)
                && !smallPat.test(s) && !seen.has(s)) {
                seen.add(s);
                result.push(s);
            }
        });
    });
    return result.slice(0, 15);
}
"""


def _sanitize_dirname(name: str) -> str:
    return sanitize_dirname(name)

def _urllib_download(url: str, dest: Path) -> bool:
    """alicdn画像をurllib直接DL（ログイン不要）。2KB未満は失敗扱い。"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer":    "https://detail.1688.com/",
        })
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
      status: "ok" | "login_required" | "captcha" | "no_images" | "playwright_not_installed" | "error:..."
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], "playwright_not_installed"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="zh-CN", timezone_id="Asia/Shanghai",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            "window.chrome={runtime:{}};"
        )
        try:
            page.goto(product_url, wait_until="domcontentloaded", timeout=35000)
            page.wait_for_timeout(3000)

            cur = page.url
            if "login.taobao.com" in cur or "login.1688.com" in cur:
                return [], "login_required"
            if "punish" in cur or "验证码" in page.title():
                return [], "captcha"

            # スクロールで遅延読み込みを発火
            for y in [400, 800, 1200]:
                page.evaluate(f"window.scrollTo(0, {y})")
                page.wait_for_timeout(600)

            urls: list[str] = page.evaluate(_IMG_EXTRACT_JS) or []
            return (urls, "ok") if urls else ([], "no_images")

        except Exception as e:
            return [], f"error:{e}"
        finally:
            browser.close()

def _bulk_download(img_urls: list[str], save_dir: Path) -> int:
    """URLリストをurllib直接DLしてファイルに保存。成功枚数を返す。"""
    ok = 0
    for i, url in enumerate(img_urls, 1):
        ext  = next((e for e in ["png", "webp", "jpeg"] if f".{e}" in url.lower()), "jpg")
        dest = save_dir / f"{i:02d}.{ext}"
        if _urllib_download(url, dest):
            ok += 1
            print(f"   ✅ {dest.name}  ({dest.stat().st_size // 1024}KB)")
        else:
            print(f"   ❌ DL失敗: {url[:70]}...")
    return ok


def cmd_images_login(_args):
    print("この機能は未実装です。次に実装してください: 1688/TaobaoログインCookie保存")
    return


def _playwright_download(product_url: str, img_dir: Path, headless: bool = False, interactive: bool = False) -> tuple[int, str]:
    urls, status = _playwright_extract_urls(product_url, headless=headless)
    if status != "ok":
        return 0, status
    return _bulk_download(urls, img_dir), status


def _selenium_download(product_url: str, img_dir: Path) -> tuple[int, str]:
    print("   この機能は未実装です。次に実装してください: Selenium画像取得")
    return 0, "unimplemented"


def _dl_image(url: str, dest: Path) -> bool:
    return _urllib_download(url, dest)
