"""CLI commands for Notion integration."""

from base_alibaba.services.notion_service import (
    _create_notion_db,
    _load_notion_cfg,
    _notion_id,
    _notion_req,
    _query_all_pages,
    _read_prop,
    _save_notion_cfg,
    _title_of,
    _to_notion_props,
)
from base_alibaba.services.product_service import read_products
from base_alibaba.services.profit_service import calc_profit
from base_alibaba.services.rate_service import get_cny_jpy_rate
from base_alibaba.storage.paths import NOTION_CONFIG


def cmd_notion_setup(args):
    cfg = _load_notion_cfg()
    print("\n─── Notion連携セットアップ ───")
    print("① https://www.notion.so/my-integrations でインテグレーションを作成")
    print("② 「インテグレーショントークン」を取得")
    print("③ DBを置く親ページで「…」→「コネクト」→ インテグレーションを接続\n")

    # トークン（引数 > 対話 > 既存）
    cur_tok = cfg.get("token", "")
    if getattr(args, "token", None):
        token = args.token
    else:
        hint  = f"（設定済 {cur_tok[:12]}...）" if cur_tok else "（未設定）"
        token = input(f"APIトークン {hint}: ").strip() or cur_tok
    if not token:
        print("トークンが必要です。")
        return

    # トークン検証
    try:
        me = _notion_req("GET", "users/me", token)
        print(f"✅ 認証OK: {me.get('name') or me.get('type', '接続済')}")
    except RuntimeError as e:
        print(f"❌ 認証失敗: {e}")
        return

    # 既存DB再利用（--parent未指定かつDB設定済みの場合のみ確認）
    cur_db = cfg.get("database_id", "")
    if cur_db and not getattr(args, "parent", None):
        print(f"\n既存DB ID: {cur_db}")
        if input("既存DBを再利用しますか？ [Y/n]: ").strip().lower() != "n":
            cfg["token"] = token
            _save_notion_cfg(cfg)
            print("✅ トークンを更新しました（DBは既存のまま）。")
            return

    # 親ページID（引数 > 対話）
    if getattr(args, "parent", None):
        parent_raw = args.parent
    else:
        print("\nDBを作成する親ページのURLまたはIDを入力してください。")
        parent_raw = input("親ページ URL or ID: ").strip()
    if not parent_raw:
        print("親ページIDが必要です。")
        return
    parent_id = _notion_id(parent_raw)

    # DB作成
    print("\n「BASEアリババ商品管理」DBを作成中...")
    try:
        db_id = _create_notion_db(token, parent_id)
    except RuntimeError as e:
        print(f"❌ DB作成失敗: {e}")
        print("\nヒント: 親ページでインテグレーションを接続しましたか？")
        return

    cfg.update({"token": token, "database_id": db_id, "parent_page_id": parent_id})
    _save_notion_cfg(cfg)
    print(f"✅ DB作成成功！")
    print(f"   DB ID: {db_id}")
    print(f"   設定:  {NOTION_CONFIG}")
    print(f"\n次: python tool.py notion sync  →  商品CSVを一括同期")

def cmd_notion_sync(_args):
    cfg   = _load_notion_cfg()
    token = cfg.get("token")
    db_id = cfg.get("database_id")
    if not token or not db_id:
        print("先に notion setup を実行してください。")
        return

    products = read_products()
    if not products:
        print("商品がありません。先に product add で登録してください。")
        return

    print(f"\n🔄 Notion同期開始（{len(products)} 件）...")
    print("  既存ページを取得中...")
    try:
        existing = _query_all_pages(token, db_id)
    except RuntimeError as e:
        print(f"❌ 取得失敗: {e}")
        return
    name_to_id = {_title_of(p): p["id"] for p in existing}

    created = updated = errors = 0
    for p in products:
        name  = str(p.get("name", ""))
        props = _to_notion_props(p)
        try:
            if name in name_to_id:
                _notion_req("PATCH", f"pages/{name_to_id[name]}", token, {"properties": props})
                print(f"  ↑ 更新: {name}")
                updated += 1
            else:
                _notion_req("POST", "pages", token,
                            {"parent": {"database_id": db_id}, "properties": props})
                print(f"  ＋ 追加: {name}")
                created += 1
        except RuntimeError as e:
            print(f"  ❌ 失敗: {name} — {e}")
            errors += 1

    print(f"\n✅ 同期完了  追加:{created}  更新:{updated}  エラー:{errors}")

def cmd_notion_add(_args):
    cfg   = _load_notion_cfg()
    token = cfg.get("token")
    db_id = cfg.get("database_id")
    if not token or not db_id:
        print("先に notion setup を実行してください。")
        return

    products = read_products()
    print("\n─── Notion商品追加 ───")

    matched = None
    if products:
        print("登録済み商品（CSVから選択）:")
        for p in products:
            print(f"  [{p['id']}] {p['name']}")
        pid     = input("商品ID（手動入力は空欄）: ").strip()
        matched = next((p for p in products if p["id"] == pid), None)

    if matched:
        p = matched.copy()
    else:
        rate = get_cny_jpy_rate()
        p = {
            "name":               input("商品名: "),
            "alibaba_url":        input("アリババURL: "),
            "purchase_price_cny": input("仕入れ価格（元）: "),
            "sell_price_jpy":     input("販売価格（円）: "),
            "stock_status":       input("販売状況 [available]: ").strip() or "available",
            "notes":              input("メモ: "),
        }
        try:
            r = calc_profit(float(p["purchase_price_cny"]),
                            float(p["sell_price_jpy"]), 0, 0, rate)
            p["profit_rate"] = round(r["profit_rate"], 1)
        except Exception:
            p["profit_rate"] = 0

    # Notion専用フィールドを追加入力
    p["base_url"]  = input("BASE商品URL [空欄でスキップ]: ").strip()
    p["category"]  = (input(
        "カテゴリ（ファッション/雑貨/美容・健康/家電・ガジェット/その他）[その他]: "
    ).strip() or "その他")

    props = _to_notion_props(p)
    try:
        result   = _notion_req("POST", "pages", token,
                               {"parent": {"database_id": db_id}, "properties": props})
        page_url = result.get("url", "")
        print(f"\n✅ Notionに追加: {p['name']}")
        if page_url:
            print(f"   {page_url}")
    except RuntimeError as e:
        print(f"❌ 追加失敗: {e}")

def cmd_notion_list(_args):
    cfg   = _load_notion_cfg()
    token = cfg.get("token")
    db_id = cfg.get("database_id")
    if not token or not db_id:
        print("先に notion setup を実行してください。")
        return

    print("\n🔍 Notionから取得中...")
    try:
        pages = _query_all_pages(token, db_id)
    except RuntimeError as e:
        print(f"❌ 取得失敗: {e}")
        return

    if not pages:
        print("DBにページがありません。")
        return

    print(f"\n{'商品名':<24}  {'販売価格(円)':>10}  {'仕入(元)':>8}  "
          f"{'利益率':>6}  {'販売状況':<8}  カテゴリ")
    print("─" * 85)
    for pg in pages:
        props    = pg.get("properties", {})
        name     = _read_prop(props, "商品名")
        sell     = _read_prop(props, "販売価格(円)")
        purchase = _read_prop(props, "仕入れ価格(元)")
        rate_val = _read_prop(props, "利益率")          # 0.486 = 48.6%
        status   = _read_prop(props, "販売状況")
        category = _read_prop(props, "カテゴリ")
        pct_str  = f"{float(rate_val or 0)*100:.1f}%" if rate_val else "─"
        print(f"{name[:24]:<24}  ¥{int(float(sell or 0)):>9,}  "
              f"{float(purchase or 0):>8.2f}元  {pct_str:>6}  {status:<8}  {category}")
    print(f"\n合計: {len(pages)} 件  |  DB: {db_id[:8]}...")
