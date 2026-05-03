"""CLI commands for 1688 product images."""

import shutil
import tempfile
from pathlib import Path

from base_alibaba.services.image_service import (
    CHROME_PROFILE_DIR,
    COOKIES_FILE,
    IMAGES_DIR,
    _bulk_download,
    _dl_image,
    _is_1688_detail_url,
    _playwright_download,
    _playwright_download_with_profile,
    _sanitize_dirname,
    batch_download_with_profile,
    cmd_images_login,
)
from base_alibaba.services.product_service import read_products


_STATUS_MESSAGES = {
    "profile_not_found":              "ログイン未実施 → python tool.py images login を実行してください",
    "not_logged_in":                  "ログイン未実施 → python tool.py images login を実行してください",
    "login_required":                 "ログイン未実施 → python tool.py images login を実行してください",
    "session_expired":                "セッション期限切れ → python tool.py images login で再ログインしてください",
    "captcha":                        "CAPTCHA検出。python tool.py images login で再ログインしてください",
    "not_detail_url":                 "detail.1688.com/offer/XXXXXX.html 形式のURLに変更してください",
    "no_images":                      "画像URLが見つかりませんでした",
    "download_failed":                "URLは取得できましたが画像保存に失敗しました",
    "playwright_not_installed":       "Playwright未導入: pip install playwright",
    "playwright_browser_not_installed": "Chromium未導入: python -m playwright install chromium",
}


def _print_image_failure(status: str, product_id: str):
    message = _STATUS_MESSAGES.get(status)
    if status.startswith("error:"):
        message = f"予期しないエラー: {status[6:]}"
    if message:
        print(f"   ⚠️  {message}")
    else:
        print(f"   ⚠️  取得失敗: {status}")

    if status == "playwright_not_installed":
        print("      python -m pip install playwright")
        print("      python -m playwright install chromium")
    elif status == "playwright_browser_not_installed":
        print("      python -m playwright install chromium")
    elif status not in ("not_logged_in", "login_required", "session_expired"):
        print(f"      手動登録: python tool.py images add --id {product_id} URL1 URL2 ...")


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

    force = getattr(args, 'force', False)

    # ログイン状態チェック
    has_profile = CHROME_PROFILE_DIR.exists()
    has_cookies = COOKIES_FILE.exists()
    if not has_profile and not has_cookies:
        print("❌ ログイン未実施です。先に以下を実行してください:")
        print("   python tool.py images login")
        return

    print("🌐 1688から商品画像を自動取得します\n")
    total_ok = total_ng = 0

    # スキップ判定 & バッチ対象を分離
    skip_ok = 0
    tasks: list[tuple] = []  # (product, img_dir, target_dir, temp_dir)
    for p in products:
        name    = p.get("name", "unknown")
        ali_url = p.get("alibaba_url", "")
        img_dir = IMAGES_DIR / _sanitize_dirname(name)

        if not _is_1688_detail_url(ali_url):
            print(f"  ⚠️  スキップ（無効URL）: {name}")
            print("      → detail.1688.com/offer/XXXXXX.html 形式に変更してください")
            total_ng += 1
            continue

        existing = list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")) + list(img_dir.glob("*.webp"))
        if existing and not force:
            print(f"  ⏭  スキップ（{len(existing)}枚DL済み）: {name}")
            skip_ok += len(existing)
            continue

        temp_dir = None
        target_dir = img_dir
        if existing and force:
            temp_dir = Path(tempfile.mkdtemp(prefix=f"{img_dir.name}.", dir=IMAGES_DIR))
            target_dir = temp_dir

        tasks.append((p, ali_url, img_dir, target_dir, temp_dir, existing))

    total_ok += skip_ok

    if not tasks:
        print(f"\n{'─'*54}")
        print(f"✅ 完了: 合計 {total_ok}枚  |  保存先: {IMAGES_DIR}")
        if total_ng:
            print(f"⚠️  {total_ng}商品で失敗しました")
        return

    # 1回のブラウザセッションで全商品を処理
    batch_tasks = [(ali_url, target_dir) for _, ali_url, _, target_dir, _, _ in tasks]
    results = batch_download_with_profile(batch_tasks)

    # Cookie JSONフォールバック（プロファイル未設定時）
    if all(s == "profile_not_found" for _, s in results) and has_cookies:
        print("   プロファイル未設定 → Cookie方式でフォールバック")
        results = [_playwright_download(ali_url, target_dir) for _, ali_url, _, target_dir, _, _ in tasks]

    for (p, ali_url, img_dir, target_dir, temp_dir, existing), (ok, status) in zip(tasks, results):
        name = p.get("name", "unknown")
        print(f"\n📦 {name}")
        print(f"   {ali_url}")

        if temp_dir:
            if ok > 0:
                img_dir.mkdir(parents=True, exist_ok=True)
                for f in existing:
                    try:
                        f.unlink()
                    except OSError:
                        pass
                for f in sorted(temp_dir.iterdir()):
                    shutil.move(str(f), str(img_dir / f.name))
            shutil.rmtree(temp_dir, ignore_errors=True)

        print(f"   → {ok}枚保存: {img_dir}")
        total_ok += ok
        if ok == 0:
            total_ng += 1
            _print_image_failure(status, p["id"])

    print(f"\n{'─'*54}")
    print(f"✅ 完了: 合計 {total_ok}枚  |  保存先: {IMAGES_DIR}")
    if total_ng:
        print(f"⚠️  {total_ng}商品で失敗しました")

def cmd_images_add(args):
    """画像URLを手動指定してダウンロード（--url フラグまたは位置引数）"""
    products = read_products()
    p = next((x for x in products if x["id"] == str(args.id)), None)
    if not p:
        print(f"ID {args.id} の商品が見つかりません。")
        return

    # --url フラグ と 位置引数を統合
    urls = list(args.url_flags or []) + list(args.urls or [])
    if not urls:
        print("エラー: URLを指定してください。例: --url https://cbu01.alicdn.com/...")
        return

    name    = p.get("name", "unknown")
    img_dir = IMAGES_DIR / _sanitize_dirname(name)
    img_dir.mkdir(parents=True, exist_ok=True)

    # 既存ファイル番号の続きから保存
    existing = sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.png")) + sorted(img_dir.glob("*.webp"))
    start_i = len(existing) + 1

    ok = 0
    for i, url in enumerate(urls, start_i):
        url = url.strip()
        ext = next((e for e in ['png', 'webp', 'jpeg'] if f'.{e}' in url.lower()), 'jpg')
        if ext == 'jpeg':
            ext = 'jpg'
        dest = img_dir / f"{i:02d}.{ext}"
        try:
            import urllib.request as _ur
            req = _ur.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
                "Referer": "https://detail.1688.com/",
            })
            with _ur.urlopen(req, timeout=30) as resp:
                data = resp.read()
            dest.write_bytes(data)
            ok += 1
            print(f"✅ {dest.name}  ({dest.stat().st_size // 1024}KB)")
        except Exception as e:
            print(f"❌ DL失敗: {url[:80]}  ({e})")
    print(f"\n{ok}/{len(urls)}枚保存: {img_dir}")

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
