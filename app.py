import streamlit as st
import pandas as pd
import numpy as np
import re

# ==========================================
# 1. ページ設定 & デザイン
# ==========================================
st.set_page_config(
    page_title="地方競馬AI分析ツール",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS（スマホ表示の最適化・カード風スタイル）
st.markdown("""
<style>
    .main-header {
        font-size: 24px;
        font-weight: bold;
        color: #1E3A8A;
        margin-bottom: 10px;
    }
    .sub-text {
        font-size: 14px;
        color: #4B5563;
    }
    .metric-card {
        background-color: #F3F4F6;
        padding: 12px;
        border-radius: 8px;
        border-left: 5px solid #2563EB;
        margin-bottom: 15px;
    }
    .stDataFrame {
        font-size: 14px;
    }
</style>
""", unsafe_allow_capacity=True)

# ==========================================
# 2. パスワード保護（ログイン認証）
# ==========================================
def check_password():
    """自分専用の認証チェック機能"""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 自分専用 地方競馬AI分析アプリ")
        st.write("アクセスするにはパスワードを入力してください。")
        
        password_input = st.text_input("パスワード", type="password")
        
        # 設定するパスワード（必要に応じて変更してください）
        SECRET_PASSWORD = "keiba"  # デフォルトパスワード: keiba
        
        if st.button("ログイン"):
            if password_input == SECRET_PASSWORD:
                st.session_state["authenticated"] = True
                st.success("ログイン成功！分析画面に移動します...")
                st.rerun()
            else:
                st.error("パスワードが正しくありません。")
        return False
    return True

if not check_password():
    st.stop()

# ==========================================
# 3. 分析エンジン & ロジック関数
# ==========================================

# 1角位置から脚質を判定
def get_style(avg_pos):
    if avg_pos <= 2.0:
        return "【逃】", "逃げ型"
    elif avg_pos <= 4.5:
        return "【先】", "先行型"
    elif avg_pos <= 7.5:
        return "【差】", "差し型"
    else:
        return "【追】", "追込型"

# 上昇度トレンド判定（前走着差 vs 過去平均）
def get_trend(m1, m_avg):
    diff = m_avg - m1
    if diff >= 0.5:
        return "↗ 急上昇"
    elif diff <= -0.5:
        return "↘ 下降"
    else:
        return "→ 平行"

# 展開シミュレーション
def analyze_pace(df):
    escape_count = sum(df["脚質タグ"] == "【逃】")
    ahead_count = sum(df["脚質タグ"].isin(["【逃】", "【先】"]))
    
    if escape_count <= 1:
        pace = "【単騎マイペース・スロー】"
        desc = "逃げ馬が少ないスローペース予想。前残り・先行馬が圧倒的有利！"
    elif ahead_count >= 5:
        pace = "【同型競闘・ハイペース】"
        desc = "先行争いが激しくなるハイペース予想。前崩れによる差し馬急襲に警戒！"
    else:
        pace = "【ミドルペース・平均展開】"
        desc = "標準的な展開。先行馬の粘り込みと好位差しが中心。"
    return pace, desc

# 8大ファクター総合計算ロジック
def process_data(df_input):
    df = df_input.copy()
    
    # 直近加重着差計算（前走40%, 2走前25%, 3走前15%, 4走前10%, 5走前10%）
    weights = [0.40, 0.25, 0.15, 0.10, 0.10]
    
    weighted_margins = []
    simple_margins = []
    trends = []
    styles = []
    
    for _, row in df.iterrows():
        margins = [row["1走前着差"], row["2走前着差"], row["3走前着差"], row["4走前着差"], row["5走前着差"]]
        w_avg = sum(m * w for m, w in zip(margins, weights))
        s_avg = sum(margins) / len(margins)
        
        weighted_margins.append(round(w_avg, 2))
        simple_margins.append(round(s_avg, 2))
        trends.append(get_trend(row["1走前着差"], s_avg))
        
        tag, _ = get_style(row["平均1角位置"])
        styles.append(tag)
        
    df["直近加重着差(s)"] = weighted_margins
    df["5走均等着差(s)"] = simple_margins
    df["トレンド"] = trends
    df["脚質タグ"] = styles
    
    # 総合スコア算出 (最大100pt + 騎手補正)
    # 着差pt (最大30pt): 30 - 加重着差*10
    df["着差pt"] = df["直近加重着差(s)"].apply(lambda x: max(0, 30 - x * 10))
    # 上がりpt (最大20pt): 20 - (上がり - 36)*2
    df["上がりpt"] = df["上がり3F平均"].apply(lambda x: max(0, 20 - (x - 36) * 2))
    # 騎手pt
    jockey_map = {"S": 10, "A": 5, "B": 0}
    df["騎手pt"] = df["騎手ランク"].map(jockey_map).fillna(0)
    
    # スコア合計
    df["総合スコア"] = (
        df["着差pt"] + df["上がりpt"] + df["クラス実績pt"] + 
        df["同舞台pt"] + df["枠適性pt"] + df["騎手pt"]
    ).round(1)
    
    return df

# ==========================================
# 4. サンプルデータ
# ==========================================
SAMPLE_RACE = pd.DataFrame([
    {"馬番": 1, "馬名": "オッピポイカ", "1走前着差": 2.6, "2走前着差": 0.1, "3走前着差": 1.2, "4走前着差": 1.8, "5走前着差": 3.0, "上がり3F平均": 37.98, "平均1角位置": 2.8, "クラス実績pt": 12, "同舞台pt": 16, "枠適性pt": 8, "騎手ランク": "B", "平均人気": 7.8, "主な実績": "3歳C2 1着 / 盛岡1200m 1勝"},
    {"馬番": 2, "馬名": "ドリタル", "1走前着差": 2.9, "2走前着差": 2.1, "3走前着差": 2.5, "4走前着差": 2.8, "5走前着差": 2.0, "上がり3F平均": 38.72, "平均1角位置": 3.2, "クラス実績pt": 20, "同舞台pt": 12, "枠適性pt": 8, "騎手ランク": "S", "平均人気": 7.6, "主な実績": "A一組・特別出走 (格上)"},
    {"馬番": 3, "馬名": "キンカメクオリア", "1走前着差": 4.5, "2走前着差": 3.8, "3走前着差": 4.2, "4走前着差": 4.0, "5走前着差": 4.2, "上がり3F平均": 40.50, "平均1角位置": 8.0, "クラス実績pt": 8, "同舞台pt": 8, "枠適性pt": 8, "騎手ランク": "B", "平均人気": 9.8, "主な実績": "2歳新馬1着"},
    {"馬番": 4, "馬名": "ラスダシャン", "1走前着差": 3.6, "2走前着差": 1.2, "3走前着差": 1.5, "4走前着差": 1.8, "5走前着差": 1.8, "上がり3F平均": 40.26, "平均1角位置": 5.6, "クラス実績pt": 16, "同舞台pt": 20, "枠適性pt": 8, "騎手ランク": "B", "平均人気": 4.8, "主な実績": "盛岡1200m 2勝 (最速1:12.8)"},
    {"馬番": 5, "馬名": "スチョウプリンセス", "1走前着差": 0.5, "2走前着差": 1.2, "3走前着差": 2.0, "4走前着差": 2.5, "5走前着差": 2.6, "上がり3F平均": 36.70, "平均1角位置": 1.2, "クラス実績pt": 16, "同舞台pt": 20, "枠適性pt": 10, "騎手ランク": "S", "平均人気": 1.0, "主な実績": "盛岡1200m 1勝 (1:12.8 圧勝)"},
    {"馬番": 6, "馬名": "グラスアラバニーユ", "1走前着差": 1.8, "2走前着差": 1.5, "3走前着差": 1.6, "4走前着差": 1.7, "5走前着差": 1.5, "上がり3F平均": 39.58, "平均1角位置": 6.2, "クラス実績pt": 12, "同舞台pt": 12, "枠適性pt": 8, "騎手ランク": "B", "平均人気": 4.6, "主な実績": "川崎C2・盛岡C2上位"},
    {"馬番": 7, "馬名": "ライヴモヒート", "1走前着差": 2.2, "2走前着差": 2.5, "3走前着差": 2.1, "4走前着差": 2.8, "5走前着差": 2.2, "上がり3F平均": 40.92, "平均1角位置": 7.5, "クラス実績pt": 4, "同舞台pt": 8, "枠適性pt": 8, "騎手ランク": "B", "平均人気": 9.2, "主な実績": "園田C3出走"},
    {"馬番": 8, "馬名": "ジーティーウブラブ", "1走前着差": 3.2, "2走前着差": 2.8, "3走前着差": 3.0, "4走前着差": 3.1, "5走前着差": 3.0, "上がり3F平均": 39.92, "平均1角位置": 7.0, "クラス実績pt": 12, "同舞台pt": 12, "枠適性pt": 8, "騎手ランク": "A", "平均人気": 8.6, "主な実績": "3歳C1出走 / 1:13.9"},
    {"馬番": 9, "馬名": "ディーファンクス", "1走前着差": 2.3, "2走前着差": 1.8, "3走前着差": 1.9, "4走前着差": 2.0, "5走前着差": 1.8, "上がり3F平均": 38.56, "平均1角位置": 3.6, "クラス実績pt": 8, "同舞台pt": 16, "枠適性pt": 8, "騎手ランク": "A", "平均人気": 6.4, "主な実績": "盛岡1200m 1:13.6 (2着)"},
    {"馬番": 10, "馬名": "トモエナゲ", "1走前着差": 2.8, "2走前着差": 2.2, "3走前着差": 2.5, "4走前着差": 2.4, "5走前着差": 2.5, "上がり3F平均": 39.26, "平均1角位置": 6.8, "クラス実績pt": 8, "同舞台pt": 12, "枠適性pt": 8, "騎手ランク": "B", "平均人気": 7.8, "主な実績": "3歳C2 3着 / 1:14.9"},
    {"馬番": 11, "馬名": "グレイスルーラー", "1走前着差": 2.1, "2走前着差": 2.0, "3走前着差": 1.9, "4走前着差": 2.1, "5走前着差": 2.0, "上がり3F平均": 38.94, "平均1角位置": 7.2, "クラス実績pt": 12, "同舞台pt": 8, "枠適性pt": 8, "騎手ランク": "S", "平均人気": 9.0, "主な実績": "JRA未勝利 / 高松亮鞍上"}
])

# ==========================================
# 5. メインUIレイアウト
# ==========================================

st.markdown("<div class='main-header'>🏇 地方競馬AI分析 ＆ 基準比較ツール</div>", unsafe_allow_html=True)

# サイドバー: データ読み込み & 設定
st.sidebar.header("⚙️ レース設定 & データ入力")

input_mode = st.sidebar.radio("データ入力方法", ["サンプルレース(盛岡5R)", "テキストコピペ入力"])

if input_mode == "サンプルレース(盛岡5R)":
    raw_df = SAMPLE_RACE
else:
    st.sidebar.info("出馬表データテキストを入力・貼り付けしてください")
    pasted_text = st.sidebar.text_area("テキスト貼り付け", height=150)
    # デフォルトでサンプル使用
    raw_df = SAMPLE_RACE

# データ加工実行
processed_df = process_data(raw_df)

# 展開シミュレーション表示
pace_type, pace_desc = analyze_pace(processed_df)

st.markdown(f"""
<div class='metric-card'>
    <h4>🏁 レース展開シミュレーション</h4>
    <p><b>想定ペース</b>: <span style='color:#D97706; font-size:18px;'>{pace_type}</span></p>
    <p style='color:#374151;'>{pace_desc}</p>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------
# 基準馬（ベンチマーク）選択コントロール
# ------------------------------------------
st.subheader("🎯 基準馬（軸馬）の選択と比較")

horse_list = processed_df["馬番"].astype(str) + "番 " + processed_df["馬名"]
selected_horse_str = st.selectbox(
    "比較の『基準』にする馬を選択してください（直近着差や上がりが自動で勝敗差分表示されます）:",
    horse_list,
    index=4 # デフォルト: 5番スチョウプリンセス
)

# 基準馬データの取得
selected_num = int(selected_horse_str.split("番")[0])
ref_horse = processed_df[processed_df["馬番"] == selected_num].iloc[0]

# 差分計算
processed_df["対基準・着差差分(s)"] = (processed_df["直近加重着差(s)"] - ref_horse["直近加重着差(s)"]).round(2)
processed_df["対基準・上がり差分(s)"] = (processed_df["上がり3F平均"] - ref_horse["上がり3F平均"]).round(2)

# 表示用の成形
display_df = processed_df.copy()

def format_margin_diff(val):
    if val == 0:
        return "基準 (±0.00)"
    elif val < 0:
        return f"−{abs(val):.2f}s (勝)"
    else:
        return f"＋{val:.2f}s (負)"

def format_上がり_diff(val):
    if val == 0:
        return "基準 (±0.00)"
    elif val < 0:
        return f"−{abs(val):.2f}s (速)"
    else:
        return f"＋{val:.2f}s (遅)"

display_df["対基準・着差"] = display_df["対基準・着差差分(s)"].apply(format_margin_diff)
display_df["対基準・上がり"] = display_df["対基準・上がり差分(s)"].apply(format_上がり_diff)

# 表示カラムの選定
final_cols = [
    "馬番", "馬名", "総合スコア", "脚質タグ", "トレンド", 
    "対基準・着差", "対基準・上がり", "1走前着差", "直近加重着差(s)", 
    "上がり3F平均", "平均人気", "主な実績"
]

show_table = display_df[final_cols]

# ------------------------------------------
# ソート機能コントロール
# ------------------------------------------
col1, col2 = st.columns([2, 1])
with col1:
    sort_key = st.selectbox(
        "並び替え順（ワンタップ変更）:",
        ["総合スコア", "対基準・着差差分(s)", "上がり3F平均", "1走前着差", "馬番"]
    )
with col2:
    sort_order = st.radio("順序", ["降順(大きい順)", "昇順(小さい順)"], index=0 if sort_key in ["総合スコア"] else 1)

is_ascending = (sort_order == "昇順(小さい順)")

if sort_key in display_df.columns:
    show_table = display_df.sort_values(by=sort_key, ascending=is_ascending)[final_cols]

# 表のメイン表示
st.dataframe(
    show_table,
    use_container_width=True,
    height=420
)

# ------------------------------------------
# 個別サマリー解説カード
# ------------------------------------------
st.markdown("---")
st.subheader("💡 1位基準比較による狙い目ピックアップ")

top_score = processed_df.sort_values(by="総合スコア", ascending=False).iloc[0]
best_margin = processed_df.sort_values(by="直近加重着差(s)", ascending=True).iloc[0]
best_agari = processed_df.sort_values(by="上がり3F平均", ascending=True).iloc[0]

c1, c2, c3 = st.columns(3)
with c1:
    st.info(f"🏆 **総合スコア 1位**\n\n**{top_score['馬番']}番 {top_score['馬名']}** ({top_score['総合スコア']}点)\n\n全指標バランス最高値の軸馬")
with c2:
    st.success(f"📈 **直近着差安定 1位**\n\n**{best_margin['馬番']}番 {best_margin['馬名']}** (加重{best_margin['直近加重着差(s)']}s)\n\n直近の着差が最も小さい安定馬")
with c3:
    st.warning(f"⚡ **末脚・上がり 1位**\n\n**{best_agari['馬番']}番 {best_agari['馬名']}** (3F {best_agari['上がり3F平均']}s)\n\n直線での切れ味最速馬")

st.caption("※ 本アプリは個人使用専用にパスワード保護されています。")
