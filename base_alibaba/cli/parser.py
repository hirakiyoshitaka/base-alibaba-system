"""argparse setup and CLI dispatch."""

import argparse

from base_alibaba.cli.commands.image_commands import (
    cmd_images_add,
    cmd_images_download,
    cmd_images_list,
    cmd_images_login,
)
from base_alibaba.cli.commands.notion_commands import (
    cmd_notion_add,
    cmd_notion_list,
    cmd_notion_setup,
    cmd_notion_sync,
)
from base_alibaba.cli.commands.order_commands import (
    cmd_order_add,
    cmd_order_check,
    cmd_order_list,
    cmd_order_memo,
    cmd_order_update,
)
from base_alibaba.cli.commands.product_commands import (
    cmd_product_add,
    cmd_product_delete,
    cmd_product_list,
)
from base_alibaba.cli.commands.profit_commands import cmd_profit
from base_alibaba.cli.commands.rate_commands import cmd_rate
from base_alibaba.cli.commands.webhook_commands import (
    cmd_webhook_logs,
    cmd_webhook_setup,
    cmd_webhook_start,
    cmd_webhook_test,
)
from base_alibaba.storage.csv_store import init_data_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tool.py",
        description="BASE × アリババ ドロップシッピング管理ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使い方:
  python tool.py profit                          利益計算（対話式）
  python tool.py profit -p 80 -s 4980            利益計算（引数直接指定）
  python tool.py profit -p 80 -s 4980 --shipping 500 --tariff 5

  python tool.py product add                     商品追加
  python tool.py product list                    商品一覧
  python tool.py product delete 3                商品削除（ID指定）

  python tool.py order add                       注文追加（発注メモ自動生成）
  python tool.py order list                      注文一覧
  python tool.py order check                     配送遅延警告チェック
  python tool.py order update ORD-xxx --status shipped --tracking EMS12345
  python tool.py order memo ORD-xxx              発注メモ再表示

  python tool.py rate                            為替レート表示
  python tool.py rate --refresh                  為替レート強制更新

  python tool.py webhook setup                   シークレット・ポート設定
  python tool.py webhook start                   受信サーバー起動（Ctrl+Cで停止）
  python tool.py webhook start --port 9090       ポート指定で起動
  python tool.py webhook test                    テスト注文を送信（別ターミナルでstart後）
  python tool.py webhook test --product 商品名 --price 3980
  python tool.py webhook logs                    受信ログ表示

  python tool.py notion setup                    APIトークン設定・DB自動作成
  python tool.py notion sync                     products.csvをNotionに一括同期
  python tool.py notion add                      商品1件をNotionに追加
  python tool.py notion list                     NotionDB商品一覧表示

  python tool.py images login                    1688にQRログイン → Cookie保存（初回必須）
  python tool.py images download                 全商品の画像をダウンロード（ブラウザ起動）
  python tool.py images download --id 8          ID指定で1商品のみ
  python tool.py images download --headless      ヘッドレスモード（CAPTCHAで失敗する場合あり）
  python tool.py images download --force         ダウンロード済みも強制上書き
  python tool.py images add --id 8 URL1 URL2     画像URLを手動指定してDL
  python tool.py images list                     ダウンロード済み一覧

データ保存先: ~/.base_alibaba/
画像保存先:   ~/BASEアリババ/images/
""",
    )
    sub = parser.add_subparsers(dest="command")

    pp = sub.add_parser("profit", help="利益計算")
    pp.add_argument("-p", "--purchase", type=float, metavar="元", help="仕入れ価格（元）")
    pp.add_argument("-s", "--sell", type=float, metavar="円", help="販売価格（円）")
    pp.add_argument("--shipping", type=float, metavar="円", help="国際送料（円）")
    pp.add_argument("--tariff", type=float, metavar="%", help="関税率（%%）")
    pp.add_argument("-i", "--interactive", action="store_true", help="対話モード強制")
    pp.set_defaults(func=cmd_profit)

    prd = sub.add_parser("product", help="商品管理")
    prd_sub = prd.add_subparsers(dest="subcommand")
    prd.set_defaults(func=lambda _args: prd.print_help())
    prd_add = prd_sub.add_parser("add", help="商品追加")
    prd_add.add_argument("--name", help="商品名")
    prd_add.add_argument("--url", help="アリババURL")
    prd_add.add_argument("--price", type=float, metavar="元", help="仕入れ価格（元）")
    prd_add.add_argument("--sell", type=float, metavar="円", help="販売価格（円）")
    prd_add.add_argument("--shipping", type=float, metavar="円", help="国際送料（円）[0]")
    prd_add.add_argument("--tariff", type=float, metavar="%", help="関税率（%%）[0]")
    prd_add.add_argument("--stock", help="在庫ステータス [available]")
    prd_add.add_argument("--notes", help="メモ")
    prd_add.set_defaults(func=cmd_product_add)
    prd_sub.add_parser("list", help="商品一覧").set_defaults(func=cmd_product_list)
    pdel = prd_sub.add_parser("delete", help="商品削除")
    pdel.add_argument("id", type=int, help="商品ID")
    pdel.set_defaults(func=cmd_product_delete)

    ord_ = sub.add_parser("order", help="注文管理")
    ord_sub = ord_.add_subparsers(dest="subcommand")
    ord_.set_defaults(func=lambda _args: ord_.print_help())
    ord_sub.add_parser("add", help="注文追加（サプライヤー発注メモ自動生成）").set_defaults(func=cmd_order_add)
    ord_sub.add_parser("list", help="注文一覧").set_defaults(func=cmd_order_list)
    ord_sub.add_parser("check", help="配送遅延警告チェック（14日超え）").set_defaults(func=cmd_order_check)
    upd = ord_sub.add_parser("update", help="注文ステータス・追跡番号更新")
    upd.add_argument("order_id")
    upd.add_argument("--status", help="pending / ordered / shipped / delivered / cancelled")
    upd.add_argument("--tracking", help="追跡番号（EMS等）")
    upd.set_defaults(func=cmd_order_update)
    mem = ord_sub.add_parser("memo", help="発注メモ再表示")
    mem.add_argument("order_id")
    mem.set_defaults(func=cmd_order_memo)

    rt = sub.add_parser("rate", help="為替レート（CNY/JPY）")
    rt.add_argument("--refresh", action="store_true", help="キャッシュを無視して強制更新")
    rt.set_defaults(func=cmd_rate)

    img = sub.add_parser("images", help="1688商品画像ダウンロード")
    img_sub = img.add_subparsers(dest="subcommand")
    img.set_defaults(func=lambda _args: img.print_help())
    img_dl = img_sub.add_parser("download", help="全商品の画像をダウンロード")
    img_dl.add_argument("--id", type=int, help="特定商品ID のみ処理")
    img_dl.add_argument("--headless", action="store_true", help="ヘッドレスモード（CAPTCHAで失敗しやすい）")
    img_dl.add_argument("--force", action="store_true", help="ダウンロード済みも再取得")
    img_dl.set_defaults(func=cmd_images_download)
    img_add = img_sub.add_parser("add", help="画像URLを手動指定してダウンロード")
    img_add.add_argument("--id", type=int, required=True, help="商品ID")
    img_add.add_argument("--url", dest="url_flags", action="append", metavar="URL", help="画像URL（--url を複数回指定可）")
    img_add.add_argument("urls", nargs="*", metavar="URL", help="画像URL（位置引数、--urlと併用可）")
    img_add.set_defaults(func=cmd_images_add)
    img_sub.add_parser("login", help="1688/TaobaoにQRコードログイン → Cookieを保存").set_defaults(func=cmd_images_login)
    img_sub.add_parser("list", help="ダウンロード済み画像一覧").set_defaults(func=cmd_images_list)

    nt = sub.add_parser("notion", help="Notion連携")
    nt_sub = nt.add_subparsers(dest="subcommand")
    nt.set_defaults(func=lambda _args: nt.print_help())
    nt_setup = nt_sub.add_parser("setup", help="APIトークン設定・DB自動作成")
    nt_setup.add_argument("--token", help="Notion APIトークン（secret_xxx...）")
    nt_setup.add_argument("--parent", help="親ページのURL または ID")
    nt_setup.set_defaults(func=cmd_notion_setup)
    nt_sub.add_parser("sync", help="products.csvをNotionに一括同期（upsert）").set_defaults(func=cmd_notion_sync)
    nt_sub.add_parser("add", help="商品1件をNotionに追加").set_defaults(func=cmd_notion_add)
    nt_sub.add_parser("list", help="NotionDB商品一覧表示").set_defaults(func=cmd_notion_list)

    wh = sub.add_parser("webhook", help="BASE webhook連携")
    wh_sub = wh.add_subparsers(dest="subcommand")
    wh.set_defaults(func=lambda _args: wh.print_help())
    wh_sub.add_parser("setup", help="シークレット・ポート設定").set_defaults(func=cmd_webhook_setup)
    ws = wh_sub.add_parser("start", help="受信サーバー起動")
    ws.add_argument("--port", type=int, help="待受ポート（設定値を上書き）")
    ws.set_defaults(func=cmd_webhook_start)
    wt = wh_sub.add_parser("test", help="テスト注文をローカルサーバーに送信")
    wt.add_argument("--port", type=int, help="送信先ポート")
    wt.add_argument("--product", help="商品名（省略時: テスト商品）")
    wt.add_argument("--price", type=int, help="価格・円（省略時: 4980）")
    wt.set_defaults(func=cmd_webhook_test)
    wl = wh_sub.add_parser("logs", help="受信ログ表示")
    wl.add_argument("--limit", type=int, help="表示件数（デフォルト: 20）")
    wl.set_defaults(func=cmd_webhook_logs)

    return parser


def main(argv: list[str] | None = None):
    init_data_dir()
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
