"""BASEアリババ管理ツール — Streamlit Web UI"""

import sys
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import pandas as pd
from datetime import date

from base_alibaba.storage.csv_store import (
    init_data_dir, read_products, write_products,
    read_orders, write_orders,
)
from base_alibaba.services.product_service import next_product_id
from base_alibaba.services.profit_service import calc_profit
from base_alibaba.services.rate_service import get_cny_jpy_rate
from base_alibaba.config import PRODUCT_FIELDS, ORDER_FIELDS
from base_alibaba.storage.paths import IMAGES_DIR

# ────────────────────────────────────────────────────────────
# 初期化
# ────────────────────────────────────────────────────────────
init_data_dir()

st.set_page_config(
    page_title="BASEアリババ管理",
    page_icon="🛒",
    layout="wide",
)

# ────────────────────────────────────────────────────────────
# サイドバー — ナビゲーション
# ────────────────────────────────────────────────────────────
st.sidebar.title("🛒 BASEアリババ管理")
page = st.sidebar.radio(
    "メニュー",
    ["📦 商品一覧", "➕ 商品登録", "📋 注文一覧", "➕ 注文登録", "💰 利益シミュレーター"],
    label_visibility="collapsed",
)

# 為替レートをセッションにキャッシュ
if "rate" not in st.session_state:
    with st.spinner("為替レートを取得中..."):
        try:
            st.session_state.rate = get_cny_jpy_rate()
        except Exception:
            st.session_state.rate = 21.5

rate = st.session_state.rate
st.sidebar.metric("💱 1元 = 円", f"¥{rate:.2f}")
if st.sidebar.button("レート更新"):
    try:
        st.session_state.rate = get_cny_jpy_rate(force_refresh=True)
        st.rerun()
    except Exception as e:
        st.sidebar.error(str(e))

# ────────────────────────────────────────────────────────────
# ページ: 商品一覧
# ────────────────────────────────────────────────────────────
if page == "📦 商品一覧":
    st.title("📦 商品一覧")
    products = read_products()

    if not products:
        st.info("商品が登録されていません。「商品登録」から追加してください。")
    else:
        df = pd.DataFrame(products)
        # 数値変換
        for col in ["purchase_price_cny", "sell_price_jpy", "intl_shipping_jpy",
                    "profit_jpy", "profit_rate", "tariff_rate"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # サマリーカード
        c1, c2, c3 = st.columns(3)
        c1.metric("登録商品数", len(df))
        c2.metric("平均利益", f"¥{df['profit_jpy'].mean():,.0f}")
        c3.metric("黒字商品", f"{(df['profit_jpy'] > 0).sum()} / {len(df)}")

        st.divider()

        # 検索フィルター
        q = st.text_input("🔍 商品名で検索", placeholder="キーワード")
        if q:
            df = df[df["name"].str.contains(q, case=False, na=False)]

        # テーブル表示
        display_cols = {
            "id": "ID",
            "name": "商品名",
            "purchase_price_cny": "仕入(元)",
            "sell_price_jpy": "販売価格(円)",
            "profit_jpy": "利益(円)",
            "profit_rate": "利益率(%)",
            "stock_status": "在庫",
        }
        styled = df[list(display_cols.keys())].rename(columns=display_cols)
        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            column_config={
                "利益(円)": st.column_config.NumberColumn(format="¥%,.0f"),
                "販売価格(円)": st.column_config.NumberColumn(format="¥%,.0f"),
                "利益率(%)": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )

        # 詳細 & 削除
        st.divider()
        st.subheader("商品詳細 / 削除")
        ids = [p["id"] for p in products]
        sel_id = st.selectbox("IDを選択", ids)
        sel = next((p for p in products if p["id"] == sel_id), None)
        if sel:
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**商品名:** {sel['name']}")
                st.write(f"**アリババURL:** {sel['alibaba_url']}")
                st.write(f"**仕入価格:** {sel['purchase_price_cny']} 元")
                st.write(f"**販売価格:** ¥{float(sel['sell_price_jpy']):,.0f}")
                st.write(f"**国際送料:** ¥{float(sel['intl_shipping_jpy']):,.0f}")
            with col2:
                st.write(f"**関税率:** {float(sel['tariff_rate'])*100:.1f}%")
                st.write(f"**利益:** ¥{float(sel['profit_jpy']):,.0f}")
                st.write(f"**利益率:** {sel['profit_rate']}%")
                st.write(f"**在庫:** {sel['stock_status']}")
                st.write(f"**メモ:** {sel['notes']}")

            # 画像表示
            img_dir = IMAGES_DIR / sel_id
            if img_dir.exists():
                imgs = list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")) + list(img_dir.glob("*.webp"))
                if imgs:
                    st.image([str(i) for i in imgs[:5]], width=120)

            if st.button("🗑️ この商品を削除", type="secondary"):
                updated = [p for p in products if p["id"] != sel_id]
                write_products(updated)
                st.success(f"商品 #{sel_id} を削除しました")
                st.rerun()

# ────────────────────────────────────────────────────────────
# ページ: 商品登録
# ────────────────────────────────────────────────────────────
elif page == "➕ 商品登録":
    st.title("➕ 商品登録")

    with st.form("add_product", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input("商品名 *", placeholder="例: シルクスカーフ 60×60cm")
            url  = st.text_input("アリババURL", placeholder="https://detail.1688.com/...")
            purchase_cny  = st.number_input("仕入れ価格（元）", min_value=0.0, step=0.5, format="%.2f")
            sell_jpy      = st.number_input("販売価格（円）", min_value=0, step=100)
            intl_shipping = st.number_input("国際送料（円）", min_value=0, step=100)

        with col2:
            tariff_pct = st.number_input("関税率（%）", min_value=0.0, max_value=100.0, step=0.5, value=0.0)
            stock = st.selectbox("在庫ステータス", ["available", "low_stock", "out_of_stock", "discontinued"])
            notes = st.text_area("メモ", height=100)

            # リアルタイム利益プレビュー
            if purchase_cny > 0 and sell_jpy > 0:
                r = calc_profit(purchase_cny, sell_jpy, intl_shipping, tariff_pct / 100, rate)
                profit_color = "green" if r["profit"] > 0 else "red"
                st.metric("利益（予測）", f"¥{r['profit']:,.0f}", delta=f"{r['profit_rate']:.1f}%")

        submitted = st.form_submit_button("登録する", type="primary", use_container_width=True)

    if submitted:
        if not name:
            st.error("商品名は必須です")
        else:
            products = read_products()
            new_id = next_product_id(products)
            r = calc_profit(purchase_cny, sell_jpy, intl_shipping, tariff_pct / 100, rate)
            products.append({
                "id": new_id,
                "name": name,
                "alibaba_url": url,
                "purchase_price_cny": purchase_cny,
                "sell_price_jpy": sell_jpy,
                "intl_shipping_jpy": intl_shipping,
                "tariff_rate": tariff_pct / 100,
                "profit_jpy": round(r["profit"]),
                "profit_rate": round(r["profit_rate"], 1),
                "stock_status": stock,
                "notes": notes,
            })
            write_products(products)
            st.success(f"✅ 商品 #{new_id}「{name}」を登録しました！（利益 ¥{r['profit']:,.0f} / {r['profit_rate']:.1f}%）")

# ────────────────────────────────────────────────────────────
# ページ: 注文一覧
# ────────────────────────────────────────────────────────────
elif page == "📋 注文一覧":
    st.title("📋 注文一覧")
    orders = read_orders()

    if not orders:
        st.info("注文がありません。「注文登録」から追加してください。")
    else:
        df = pd.DataFrame(orders)

        # ステータスフィルター
        statuses = ["すべて"] + sorted(df["status"].dropna().unique().tolist())
        sel_status = st.selectbox("ステータスで絞込", statuses)
        if sel_status != "すべて":
            df = df[df["status"] == sel_status]

        # カード表示
        c1, c2, c3 = st.columns(3)
        c1.metric("注文数", len(df))
        pending = (df["status"] == "pending").sum()
        c2.metric("発送待ち", pending)
        shipped = (df["status"] == "shipped").sum()
        c3.metric("発送済み", shipped)

        st.divider()
        st.dataframe(df, use_container_width=True, hide_index=True)

        # ステータス更新
        st.subheader("ステータス更新")
        order_ids = [o["order_id"] for o in orders]
        sel_oid = st.selectbox("注文IDを選択", order_ids)
        new_status = st.selectbox("新ステータス", ["pending", "ordered", "shipped", "delivered", "cancelled"])
        tracking = st.text_input("追跡番号（任意）")

        if st.button("更新する", type="primary"):
            updated = []
            for o in orders:
                if o["order_id"] == sel_oid:
                    o["status"] = new_status
                    if tracking:
                        o["tracking_number"] = tracking
                updated.append(o)
            write_orders(updated)
            st.success(f"注文 {sel_oid} のステータスを「{new_status}」に更新しました")
            st.rerun()

# ────────────────────────────────────────────────────────────
# ページ: 注文登録
# ────────────────────────────────────────────────────────────
elif page == "➕ 注文登録":
    st.title("➕ 注文登録")
    products = read_products()

    with st.form("add_order", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            order_id   = st.text_input("注文ID *", placeholder="例: BASE-20260504-001")
            order_date = st.date_input("注文日", value=date.today())
            buyer_name = st.text_input("購入者氏名 *")
            buyer_addr = st.text_area("購入者住所 *", height=80)

        with col2:
            if products:
                prod_opts = {f"#{p['id']} {p['name']}": p for p in products}
                sel_label = st.selectbox("商品を選択 *", list(prod_opts.keys()))
                sel_prod  = prod_opts[sel_label]
            else:
                st.warning("先に商品を登録してください")
                sel_prod = None
                sel_label = ""

            quantity = st.number_input("数量", min_value=1, step=1, value=1)
            status   = st.selectbox("ステータス", ["pending", "ordered", "shipped", "delivered"])
            tracking = st.text_input("追跡番号（任意）")
            notes    = st.text_input("メモ（任意）")

        submitted = st.form_submit_button("注文登録", type="primary", use_container_width=True)

    if submitted:
        if not order_id or not buyer_name or not buyer_addr or not sel_prod:
            st.error("必須項目（*）を入力してください")
        else:
            orders = read_orders()
            orders.append({
                "order_id": order_id,
                "order_date": str(order_date),
                "buyer_name": buyer_name,
                "buyer_address": buyer_addr,
                "product_id": sel_prod["id"],
                "product_name": sel_prod["name"],
                "quantity": quantity,
                "sell_price_jpy": sel_prod["sell_price_jpy"],
                "alibaba_url": sel_prod["alibaba_url"],
                "purchase_price_cny": sel_prod["purchase_price_cny"],
                "status": status,
                "tracking_number": tracking,
                "notes": notes,
            })
            write_orders(orders)
            st.success(f"✅ 注文「{order_id}」を登録しました")

# ────────────────────────────────────────────────────────────
# ページ: 利益シミュレーター
# ────────────────────────────────────────────────────────────
elif page == "💰 利益シミュレーター":
    st.title("💰 利益シミュレーター")
    st.caption(f"現在の為替レート: 1元 = ¥{rate:.2f}")

    col1, col2 = st.columns(2)
    with col1:
        sim_purchase = st.number_input("仕入れ価格（元）", min_value=0.0, step=0.5, value=50.0, format="%.2f")
        sim_sell     = st.number_input("販売価格（円）",  min_value=0, step=100, value=3000)
        sim_shipping = st.number_input("国際送料（円）",  min_value=0, step=100, value=500)
        sim_tariff   = st.number_input("関税率（%）",    min_value=0.0, max_value=100.0, step=0.5, value=0.0)

    with col2:
        r = calc_profit(sim_purchase, sim_sell, sim_shipping, sim_tariff / 100, rate)

        st.subheader("計算結果")
        profit_delta = f"{r['profit_rate']:.1f}%"
        st.metric("利益", f"¥{r['profit']:,.0f}", delta=profit_delta,
                  delta_color="normal" if r["profit"] > 0 else "inverse")

        breakdown = {
            "項目": ["仕入原価（円換算）", "関税", "国際送料", "BASE手数料", "合計コスト", "損益分岐点"],
            "金額（円）": [
                f"¥{r['purchase_jpy']:,.0f}",
                f"¥{r['tariff_jpy']:,.0f}",
                f"¥{sim_shipping:,.0f}",
                f"¥{r['base_fee']:,.0f}",
                f"¥{r['total_cost']:,.0f}",
                f"¥{r['bep']:,.0f}",
            ],
        }
        st.table(pd.DataFrame(breakdown))

    # 販売価格スライダーで感度分析
    st.divider()
    st.subheader("販売価格感度分析")
    price_range = st.slider(
        "販売価格レンジ（円）",
        min_value=500, max_value=50000,
        value=(max(500, sim_sell - 2000), min(50000, sim_sell + 2000)),
        step=100,
    )
    prices = list(range(price_range[0], price_range[1] + 1, 100))
    profits = [calc_profit(sim_purchase, p, sim_shipping, sim_tariff / 100, rate)["profit"] for p in prices]
    chart_df = pd.DataFrame({"販売価格（円）": prices, "利益（円）": profits})
    st.line_chart(chart_df.set_index("販売価格（円）"))
