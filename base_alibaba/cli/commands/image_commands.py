"""CLI commands for 1688 product images."""

import sys

from base_alibaba.services.image_service import (
    COOKIES_FILE,
    IMAGES_DIR,
    _dl_image,
    _playwright_download,
    _sanitize_dirname,
    _selenium_download,
    cmd_images_login,
)
from base_alibaba.services.product_service import read_products


def cmd_images_download(args):
    products = read_products()
    if not products:
        print("商品がありません。先に product add で登録してください。")
        return

    if getattr(args, 'id', None):
        products = [p for p in products if p["id"] == str(args.id)]
        if not products:
            print(f"ID {args.id} の商品が見つかりません。")
            return

    headless    = getattr(args, 'headless', False)
    force       = getattr(args, 'force', False)
    interactive = sys.stdin.isatty()

    if not COOKIES_FILE.exists():
        print("❌ 1688にログインしていません。先に以下を実行してください:")
        print("   python tool.py images login")
        return

    print("🌐 認証済みCookieでブラウザを起動します\n")
    total_ok = total_ng = 0

    for p in products:
        name    = p.get("name", "unknown")
        ali_url = p.get("alibaba_url", "")
        img_dir = IMAGES_DIR / _sanitize_dirname(name)

        if "selloffer/offerlist" in ali_url or not ali_url.startswith("http"):
            print(f"  ⚠️  スキップ（詳細URL未設定）: {name}")
            print( "      → detail.1688.com/offer/XXXXXX.html 形式のURLに変更してください")
            continue

        existing = list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")) + list(img_dir.glob("*.webp"))
        if existing and not force:
            print(f"  ⏭  スキップ（{len(existing)}枚DL済み）: {name}")
            total_ok += len(existing)
            continue

        img_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n📦 {name}")
        print(f"   {ali_url}")

        import importlib.util
        # 1. Playwright（セッション内DLで認証Cookie付き）
        ok, status = _playwright_download(ali_url, img_dir,
                                          headless=headless, interactive=interactive) \
            if importlib.util.find_spec("playwright") else (0, "playwright_not_installed")

        # 2. Selenium fallback
        if ok == 0 and status not in ("captcha_unsolved", "session_expired"):
            if importlib.util.find_spec("selenium"):
                print("   Playwrightで取得できず → Seleniumで再試行...")
                ok, status = _selenium_download(ali_url, img_dir)

        print(f"   → {ok}枚保存: {img_dir}")
        total_ok += ok
        if ok == 0:
            total_ng += 1
            if status in ("session_expired", "not_logged_in"):
                print("   ⚠️  セッション期限切れ → python tool.py images login で再ログインしてください")
            else:
                print(f"   手動登録: python tool.py images add --id {p['id']} URL1 URL2 ...")

    print(f"\n{'─'*54}")
    print(f"✅ 完了: 合計 {total_ok}枚  |  保存先: {IMAGES_DIR}")
    if total_ng:
        print(f"⚠️  {total_ng}商品で失敗しました")

def cmd_images_add(args):
    """CAPTCHAブロック時などに画像URLを手動で指定してダウンロード"""
    products = read_products()
    p = next((x for x in products if x["id"] == str(args.id)), None)
    if not p:
        print(f"ID {args.id} の商品が見つかりません。")
        return

    name    = p.get("name", "unknown")
    img_dir = IMAGES_DIR / _sanitize_dirname(name)
    img_dir.mkdir(parents=True, exist_ok=True)

    ok = 0
    for i, url in enumerate(args.urls, 1):
        ext  = next((e for e in ['png','webp','jpeg'] if f'.{e}' in url.lower()), 'jpg')
        dest = img_dir / f"{i:02d}.{ext}"
        if _dl_image(url, dest):
            ok += 1
            print(f"✅ {dest.name}  ({dest.stat().st_size//1024}KB)")
        else:
            print(f"❌ DL失敗: {url}")
    print(f"\n{ok}/{len(args.urls)}枚保存: {img_dir}")

def cmd_images_list(_args):
    if not IMAGES_DIR.exists():
        print("images/フォルダがありません。先に images download を実行してください。")
        return
    total = 0
    print(f"\n{'商品名':<30}  枚数  パス")
    print("─" * 70)
    for d in sorted(IMAGES_DIR.iterdir()):
        if d.is_dir():
            imgs = list(d.glob("*.jpg")) + list(d.glob("*.png")) + list(d.glob("*.webp"))
            print(f"  {d.name[:28]:<28}  {len(imgs):>3}枚  {d}")
            total += len(imgs)
    print(f"\n合計: {total}枚  |  {IMAGES_DIR}")
