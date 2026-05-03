"""CLI commands for BASE webhook operations."""

import hashlib
import hmac
import http.server
import json
import urllib.request
from datetime import datetime

from base_alibaba.services.webhook_service import _WebhookHandler, load_webhook_config, save_webhook_config
from base_alibaba.storage.paths import WEBHOOK_CONFIG, WEBHOOK_LOG


def cmd_webhook_setup(_args):
    cfg = load_webhook_config()
    print("\n─── Webhook設定 ───")
    print(f"現在のポート  : {cfg.get('port', 8080)}")
    secret_disp = ("（設定済み）" if cfg.get("secret") else "（未設定）")
    print(f"現在のシークレット: {secret_disp}")
    print()

    port = input(f"受信ポート [{cfg.get('port', 8080)}]: ").strip()
    cfg["port"] = int(port) if port else cfg.get("port", 8080)

    print("\nBASE App管理画面 → webhook設定画面のシークレットキーを入力してください。")
    print("（空Enterで変更なし）")
    secret = input("シークレットキー: ").strip()
    if secret:
        cfg["secret"] = secret

    save_webhook_config(cfg)
    print(f"\n✅ 設定を保存しました: {WEBHOOK_CONFIG}")
    print(f"   ポート   : {cfg['port']}")
    print(f"   シークレット: {'（設定済み）' if cfg['secret'] else '（未設定 — 開発中は署名検証スキップ）'}")
    print(f"\n次のステップ:")
    print(f"  1. python tool.py webhook start")
    print(f"  2. ngrok等でポート {cfg['port']} を公開してBASEに登録")
    print(f"     例: ngrok http {cfg['port']}")

def cmd_webhook_start(args):
    cfg  = load_webhook_config()
    port = args.port or cfg.get("port", 8080)

    _WebhookHandler.secret = cfg.get("secret", "")
    if not _WebhookHandler.secret:
        print("⚠️  シークレット未設定 — 署名検証をスキップします（開発中のみ許容）")
        print("   本番前に: python tool.py webhook setup")

    server = http.server.HTTPServer(("0.0.0.0", port), _WebhookHandler)
    print(f"\n🚀 Webhook受信サーバー起動")
    print(f"   URL  : http://localhost:{port}/")
    print(f"   ログ : {WEBHOOK_LOG}")
    print(f"   停止 : Ctrl+C\n")
    if not _WebhookHandler.secret:
        print("   ※ ngrok等で公開後、BASEのApp管理画面に登録してください")
        print(f"      例: ngrok http {port}")
    print("─" * 50)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nサーバーを停止しました。")
    finally:
        server.server_close()

def cmd_webhook_test(args):
    """ローカル動作テスト用サンプルpayloadを送信"""
    cfg  = load_webhook_config()
    port = args.port or cfg.get("port", 8080)
    url  = f"http://localhost:{port}/"

    payload = {
        "event": "order",
        "order_item": {
            "unique_key": f"TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "ordered": int(datetime.now().timestamp()),
            "order_status": "ordered",
            "payment_method": "credit",
            "customer": {
                "name": "テスト 太郎",
                "zip_code": "150-0001",
                "pref": "東京都",
                "address": "渋谷区テスト1-2-3",
                "address2": "テストマンション101",
                "mail": "test@example.com",
                "tel": "0901234567",
            },
            "order_items": [
                {
                    "item_id": "item_test001",
                    "title": args.product or "テスト商品",
                    "detail": "",
                    "amount": 1,
                    "price": args.price or 4980,
                }
            ],
            "total": args.price or 4980,
        },
    }

    body = json.dumps(payload, ensure_ascii=False).encode()
    secret = cfg.get("secret", "")
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest() if secret else ""

    req = urllib.request.Request(
        url, data=body,
        headers={
            "Content-Type": "application/json",
            "X-Base-Hmac-Sha256": sig,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"✅ テスト送信成功: HTTP {resp.status}")
            print(f"   送信先: {url}")
            print(f"   商品名: {payload['order_item']['order_items'][0]['title']}")
            print(f"   金額:   ¥{payload['order_item']['order_items'][0]['price']:,}")
    except Exception as e:
        print(f"❌ 送信失敗: {e}")
        print(f"   先に別ターミナルで: python tool.py webhook start")

def cmd_webhook_logs(args):
    if not WEBHOOK_LOG.exists() or WEBHOOK_LOG.stat().st_size == 0:
        print("ログがありません。")
        return
    lines = WEBHOOK_LOG.read_text(encoding="utf-8").strip().splitlines()
    limit = args.limit or 20
    print(f"\n─── Webhookログ（直近{limit}件）───")
    for line in lines[-limit:]:
        try:
            e = json.loads(line)
            ids = ", ".join(e.get("orders", []))
            print(f"  {e['ts'][:19]}  {e['event']:<12}  {ids}")
        except Exception:
            print(f"  {line[:80]}")
    print(f"\n合計: {len(lines)} 件  |  ログ: {WEBHOOK_LOG}")
