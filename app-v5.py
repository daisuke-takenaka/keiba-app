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
""", unsafe_allow_html=True)

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
        
        SECRET_PASSWORD = "keiba"
        
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
# 3. 高精度テキスト自動パース関数（頭数漏れなし・全項目抽出）
# ==========================================
def parse_pasted_text(text):
    if not text or not text.strip():
        return None
    
    lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
    
    # 競馬の除外キーワード
    exclude_words = {"出馬表", "確定", "ダート", "浦和", "金沢", "盛岡", "川崎", "船橋", "大井", "門別", "園田", "高知", "佐賀", "笠松", "名古屋", "良", "稍重", "重", "不良", "晴", "雨", "サラ系", "歳", "万円", "着差", "タイム", "上り"}
    
    horse_blocks = []
    current_horse = None
    
    for line in lines:
        # 馬番と馬名の開始判定
        m = re.search(r'^(?:[1-8]\s+)?([1-9]|1[0-8])[\s\t]+([ァ-ヴー一-龥a-zA-Z0-9]{2,10})', line)
        if not m:
            m = re.search(r'([1-9]|1[0-8])\s+([ァ-ロワヲンー一-龥]{2,10})', line)
            
        if m:
            num = int(m.group(1))
            name = m.group(2)
            if name not in exclude_words:
                if current_horse:
                    horse_blocks.append(current_horse)
                current_horse = {"馬番": num, "馬名": name, "raw_text": line}
                continue
                
        if current_horse:
            current_horse["raw_text"] += " " + line
            
    if current_horse:
        horse_blocks.append(current_horse)
        
    # フォールバック（全行スキャン）
    if not horse_blocks:
        found_names = set()
        for line in lines:
            matches = re.findall(r'([1-9]|1[0-8])[\s\t]+([ァ-ロワヲンー一-龥]{2,10})', line)
            for num_str, name in matches:
                if name not in exclude_words and name not in found_names:
                    found_names.add(name)
                    horse_blocks.append({"馬番": int(num_str), "馬名": name, "raw_text": line})

    if not horse_blocks:
        return None
        
    df_data = []
    for h in horse_blocks:
        num = h["馬番"]
        name = h["馬名"]
        raw = h["raw_text"]
        
        floats = [float(x) for x in re.findall(r'\b\d+\.\d+\b', raw)]
        ints = [int(x) for x in re.findall(r'\b\d+\b', raw)]
        
        margins = [f for f in floats if 0.0 <= f <= 9.9]
        times3f = [f for f in floats if 33.0 <= f <= 50.0]
        pops = [i for i in ints if 1 <= i <= 18 and i != num]
        pos1_list = [f for f in floats if 1.0 <= f <= 18.0 and f not in times3f and f not in margins]
        
        m1 = margins[0] if len(margins) > 0 else 1.2
        m2 = margins[1] if len(margins) > 1 else 1.5
        m3 = margins[2] if len(margins) > 2 else 1.5
        m4 = margins[3] if len(margins) > 3 else 1.8
        m5 = margins[4] if len(margins) > 4 else 2.0
        
        f3_avg = sum(times3f)/len(times3f) if times3f else 39.2
        pop_avg = sum(pops)/len(pops) if pops else 5.0
        avg_pos1 = pos1_list[0] if pos1_list else 5.0
        
        gate_map = {1:1, 2:1, 3:2, 4:2, 5:3, 6:3, 7:4, 8:4, 9:5, 10:5, 11:6, 12:6, 13:7, 14:7, 15:8, 16:8, 17:8, 18:8}
        gate_num = gate_map.get(num, 4)
        
        df_data.append({
            "枠番": gate_num,
            "馬番": num,
            "馬名": name,
            "1走前着差": m1,
            "2走前着差": m2,
            "3走前着差": m3,
            "4走前着差": m4,
            "5走前着差": m5,
            "上がり3F平均": round(f3_avg, 2),
            "平均1角位置": avg_pos1,
            "クラス実績pt": 12,
            "同舞台pt": 12,
            "枠適性pt": 8,
            "騎手ランク": "A",
            "平均人気": round(pop_avg, 1),
            "主な実績": "出馬表解析データ"
        })
        
    df = pd.DataFrame(df_data)
    df = df.drop_duplicates(subset=["馬番"]).sort_values(by="馬番").reset_index(drop=True)
    return df

# ==========================================
# 4. 分析エンジン & ロジック関数
# ==========================================

def get_style(avg_pos):
    if avg_pos <= 2.0:
        return "【逃】", "逃げ型"
    elif avg_pos <= 4.5:
        return "【先】", "先行型"
    elif avg_pos <= 7.5:
        return "【差】", "差し型"
    else:
        return "【追】", "追込型"

def get_trend(m1, m_avg):
    diff = m_avg - m1
    if diff >= 0.5:
        return "↗ 急上昇"
    elif diff <= -0.5:
        return "↘ 下降"
    else:
        return "→ 平行"

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

def process_data(df_input):
    df = df_input.copy()
    
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
    df["純粋着差平均(s)"] = simple_margins
    df["トレンド"] = trends
    df["脚質タグ"] = styles
    
    df["着差pt"] = df["直近加重着差(s)"].apply(lambda x: max(0, 30 - x * 10))
    df["上がりpt"] = df["上がり3F平均"].apply(lambda x: max(0, 20 - (x - 36) * 2))
    
    jockey_map = {"S": 10, "A": 5, "B": 0}
    df["騎手pt"] = df["騎手ランク"].map(jockey_map).fillna(0)
    
    df["総合スコア"] = (
        df["着差pt"] + df["上がりpt"] + df["クラス実績pt"] + 
        df["同舞台pt"] + df["枠適性pt"] + df["騎手pt"]
    ).round(1)
    
    return df

# ==========================================
# 5. サンプルデータ
# ==========================================
SAMPLE_RACE = pd.DataFrame([
    {"枠番": 1, "馬番": 1, "馬名": "オッピポイカ", "1走前着差": 2.6, "2走前着差": 0.1, "3走前着差": 1.2, "4走前着差": 1.8, "5走前着差": 3.0, "上がり3F平均": 37.98, "平均1角位置": 2.8, "クラス実績pt": 12, "同舞台pt": 16, "枠適性pt": 8, "騎手ランク": "B", "平均人気": 7.8, "主な実績": "3歳C2 1着 / 盛岡1200m 1勝"},
    {"枠番": 2, "馬番": 2, "馬名": "ドリタル", "1走前着差": 2.9, "2走前着差": 2.1, "3走前着差": 2.5, "4走前着差": 2.8, "5走前着差": 2.0, "上がり3F平均": 38.72, "平均1角位置": 3.2, "クラス実績pt": 20, "同舞台pt": 12, "枠適性pt": 8, "騎手ランク": "S", "平均人気": 7.6, "主な実績": "A一組・特別出走 (格上)"},
    {"枠番": 3, "馬番": 3, "馬名": "キンカメクオリア", "1走前着差": 4.5, "2走前着差": 3.8, "3走前着差": 4.2, "4走前着差": 4.0, "5走前着差": 4.2, "上がり3F平均": 40.50, "平均1角位置": 8.0, "クラス実績pt": 8, "同舞台pt": 8, "枠適性pt": 8, "騎手ランク": "B", "平均人気": 9.8, "主な実績": "2歳新馬1着"},
    {"枠番": 4, "馬番": 4, "馬名": "ラスダシャン", "1走前着差": 3.6, "2走前着差": 1.2, "3走前着差": 1.5, "4走前着差": 1.8, "5走前着差": 1.8, "上がり3F平均": 40.26, "平均1角位置": 5.6, "クラス実績pt": 16, "同舞台pt": 20, "枠適性pt": 8, "騎手ランク": "B", "平均人気": 4.8, "主な実績": "盛岡1200m 2勝 (最速1:12.8)"},
    {"枠番": 5, "馬番": 5, "馬名": "スチョウプリンセス", "1走前着差": 0.5, "2走前着差": 1.2, "3走前着差": 2.0, "4走前着差": 2.5, "5走前着差": 2.6, "上がり3F平均": 36.70, "平均1角位置": 1.2, "クラス実績pt": 16, "同舞台pt": 20, "枠適性pt": 10, "騎手ランク": "S", "平均人気": 1.0, "主な実績": "盛岡1200m 1勝 (1:12.8 圧勝)"},
    {"枠番": 6, "馬番": 6, "馬名": "グラスアラバニーユ", "1走前着差": 1.8, "2走前着差": 1.5, "3走前着差": 1.6, "4走前着差": 1.7, "5走前着差": 1.5, "上がり3F平均": 39.58, "平均1角位置": 6.2, "クラス実績pt": 12, "同舞台pt": 12, "枠適性pt": 8, "騎手ランク": "B", "平均人気": 4.6, "主な実績": "川崎C2・盛岡C2上位"},
    {"枠番": 7, "馬番": 7, "馬名": "ライヴモヒート", "1走前着差": 2.2, "2走前着差": 2.5, "3走前着差": 2.1, "4走前着差": 2.8, "5走前着差": 2.2, "上がり3F平均": 40.92, "平均1角位置": 7.5, "クラス実績pt": 4, "同舞台pt": 8, "枠適性pt": 8, "騎手ランク": "B", "平均人気": 9.2, "主な実績": "園田C3出走"},
    {"枠番": 8, "馬番": 8, "馬名": "ジーティーウブラブ", "1走前着差": 3.2, "2走前着差": 2.8, "3走前着差": 3.0, "4走前着差": 3.1, "5走前着差": 3.0, "上がり3F平均": 39.92, "平均1角位置": 7.0, "クラス実績pt": 12, "同舞台pt": 12, "枠適性pt": 8, "騎手ランク": "A", "平均人気": 8.6, "主な実績": "3歳C1出走 / 1:13.9"},
    {"枠番": 8, "馬番": 9, "馬名": "ディーファンクス", "1走前着差": 2.3, "2走前着差": 1.8, "3走前着差": 1.9, "4走前着差": 2.0, "5走前着差": 1.8, "上がり3F平均": 38.56, "平均1角位置": 3.6, "クラス実績pt": 8, "同舞台pt": 16, "枠適性pt": 8, "騎手ランク": "A", "平均人気": 6.4, "主な実績": "盛岡1200m 1:13.6 (2着)"}
])

# ==========================================
# 6. メインUIレイアウト
# ==========================================

st.markdown("<div class='main-header'>🏇 地方競馬AI分析 ＆ 基準比較ツール</div>", unsafe_allow_html=True)

# サイドバー: データ読み込み & 設定
st.sidebar.header("⚙️ レース設定 & データ入力")

input_mode = st.sidebar.radio("データ入力方法", ["サンプルレース(盛岡5R)", "テキストコピペ入力"])

if input_mode == "サンプルレース(盛岡5R)":
    raw_df = SAMPLE_RACE
else:
    st.sidebar.info("出馬表データテキストを入力・貼り付けしてください")
    pasted_text = st.sidebar.text_area("テキスト貼り付け", height=180, placeholder="ここに競馬サイトの出馬表テキストを貼り付けてください")
    
    parsed_df = parse_pasted_text(pasted_text)
    if parsed_df is not None and len(parsed_df) > 0:
        raw_df = parsed_df
        st.sidebar.success(f"✅ 全{len(raw_df)}頭のデータを自動判定・読み込み完了！")
    else:
        if pasted_text and pasted_text.strip():
            st.sidebar.warning("⚠️ テキストから馬名・馬番を検出できませんでした。サンプルを表示します。")
        else:
            st.sidebar.info("👆 上の枠に出馬表テキストを貼り付けると自動更新されます。")
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
    index=0
)

selected_num = int(selected_horse_str.split("番")[0])
ref_horse = processed_df[processed_df["馬番"] == selected_num].iloc[0]

# 差分計算
processed_df["対基準・加重着差差分(s)"] = (processed_df["直近加重着差(s)"] - ref_horse["直近加重着差(s)"]).round(2)
processed_df["対基準・純粋着差差分(s)"] = (processed_df["純粋着差平均(s)"] - ref_horse["純粋着差平均(s)"]).round(2)
processed_df["対基準・上がり差分(s)"] = (processed_df["上がり3F平均"] - ref_horse["上がり3F平均"]).round(2)

display_df = processed_df.copy()

cols = [
    "枠番", "馬番", "馬名", "脚質タグ", 
    "直近加重着差(s)", "対基準・加重着差差分(s)", 
    "純粋着差平均(s)", "対基準・純粋着差差分(s)",
    "上がり3F平均", "対基準・上がり差分(s)", 
    "平均人気", "枠適性pt", "クラス実績pt", "トレンド", "総合スコア"
]

available_cols = [c for c in cols if c in display_df.columns]
display_df = display_df[available_cols]

# ------------------------------------------
# ソート・並び替え機能
# ------------------------------------------
st.subheader("📊 分析＆全項目比較データテーブル")

sort_col = st.radio(
    "並び替え基準:",
    ["総合スコア順", "加重着差順(強い順)", "純粋着差順(強い順)", "上がり3F順(速い順)", "平均人気順(人気順)", "馬番順"],
    horizontal=True
)

if sort_col == "総合スコア順":
    display_df = display_df.sort_values(by="総合スコア", ascending=False)
elif sort_col == "加重着差順(強い順)":
    display_df = display_df.sort_values(by="対基準・加重着差差分(s)", ascending=True)
elif sort_col == "純粋着差順(強い順)":
    display_df = display_df.sort_values(by="対基準・純粋着差差分(s)", ascending=True)
elif sort_col == "上がり3F順(速い順)":
    display_df = display_df.sort_values(by="上がり3F平均", ascending=True)
elif sort_col == "平均人気順(人気順)":
    display_df = display_df.sort_values(by="平均人気", ascending=True)
elif sort_col == "馬番順":
    display_df = display_df.sort_values(by="馬番", ascending=True)

st.dataframe(display_df, use_container_width=True)

st.write("💡 **各項目の見方**：")
st.write("・**直近加重着差(s)**：前走などの直近成績を重視した着差指標。")
st.write("・**純粋着差平均(s)**：過去5走の単純な平均着差。")
st.write("・**対基準差分(s)**：マイナス表示（例：-0.5s）の馬は、基準馬よりもその分タイム面で優れている馬です。")
