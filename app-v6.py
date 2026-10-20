import streamlit as st
import pandas as pd
import numpy as np
import re

# ==========================================
# 1. ページ設定 & デザイン
# ==========================================
st.set_page_config(
    page_title="地方競馬AI分析 ＆ 基準比較ツール",
    page_icon="🏇",
    layout="wide",
    initial_sidebar_state="expanded"
)

# カスタムCSS（スマホ表示・カード風デザイン）
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
        padding: 14px;
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
    """自分専用認証機能"""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False

    if not st.session_state["authenticated"]:
        st.title("🔒 自分専用 地方競馬AI分析アプリ")
        st.write("アクセスするにはパスワードを入力してください。")
        
        password_input = st.text_input("パスワード", type="password")
        SECRET_PASSWORD = "keiba"  # デフォルトパスワード: keiba
        
        if st.button("ログイン", type="primary"):
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
# 3. 高精度出馬表テキスト解析エンジン (keiba.go.jp / netkeiba / コピペ対応)
# ==========================================
def parse_pasted_text(raw_text):
    if not raw_text or not raw_text.strip():
        return None
    
    text = raw_text.strip()
    
    # マークダウンリンク・HTMLタグ除去 ([馬名](url) -> 馬名)
    text_clean = re.sub(r'\]\([^\)]+\)', ']', text)
    text_clean = re.sub(r'\[(.*?)\]', r'\1', text_clean)
    
    # ------------------------------------------
    # パターン1: 地方競馬情報サイト (keiba.go.jp) 形式
    # ------------------------------------------
    header_pattern = r'(?:^|\n|\s)(\d{1,2})\s+(\d{1,2})\s+([ァ-ロワヲンー一-龥a-zA-Z0-9]{2,12})(?:\s*([ァ-ロワヲンー一-龥a-zA-Z0-9\s（）]+))?\s*(?:\d+\.\d+)?\s*(?:\((\d{1,2})人気\))?'
    
    matches = list(re.finditer(header_pattern, text_clean))
    
    valid_matches = []
    for m in matches:
        waku = int(m.group(1))
        num = int(m.group(2))
        name = m.group(3)
        if 1 <= waku <= 8 and 1 <= num <= 18 and name not in ["出馬表", "確定", "ダート", "浦和", "金沢", "盛岡", "良", "稍重", "重", "不良", "晴", "雨", "枠番", "馬番"]:
            valid_matches.append(m)
            
    horses = []
    if len(valid_matches) >= 2:
        for i, m in enumerate(valid_matches):
            waku = int(m.group(1))
            num = int(m.group(2))
            name = m.group(3)
            jockey = m.group(4).strip() if m.group(4) else "未設定"
            pop = int(m.group(5)) if m.group(5) else None
            
            start = m.start()
            end = valid_matches[i+1].start() if i+1 < len(valid_matches) else len(text_clean)
            block = text_clean[start:end]
            
            # 1. 人気の補完
            if pop is None:
                past_pops = [int(x) for x in re.findall(r'(\d{1,2})人気', block) or re.findall(r'(\d{1,2})人', block)]
                pop = past_pops[0] if past_pops else 5
                
            # 2. 上がり3Fタイム (33.0〜48.0s)
            times3f = [float(x) for x in re.findall(r'\b(3[3-9]\.\d|4[0-8]\.\d)\b', block)]
            f3_avg = sum(times3f) / len(times3f) if times3f else 39.5
            
            # 3. 着差 (0.0〜9.9s)
            margin_matches = re.findall(r'\b([0-9]\.\d)\s+[ァ-ロワヲンー一-龥a-zA-Z]', block)
            if not margin_matches:
                all_floats = [float(x) for x in re.findall(r'\b([0-9]\.\d)\b', block)]
                margin_matches = [f for f in all_floats if f <= 9.0]
            
            margins = [float(x) for x in margin_matches][:5]
            while len(margins) < 5:
                margins.append(margins[-1] if margins else 1.5)
                
            # 4. コーナー通過順 (1角位置)
            corner_matches = re.findall(r'\b(\d{1,2}(?:-\d{1,2}){1,3})\b', block)
            pos1_list = [int(c.split('-')[0]) for c in corner_matches if c.split('-')[0].isdigit()]
            avg_pos1 = sum(pos1_list) / len(pos1_list) if pos1_list else 5.0
            
            horses.append({
                "枠番": waku,
                "馬番": num,
                "馬名": name,
                "騎手": jockey,
                "平均人気": float(pop),
                "1走前着差": margins[0],
                "2走前着差": margins[1],
                "3走前着差": margins[2],
                "4走前着差": margins[3],
                "5走前着差": margins[4],
                "上がり3F平均": round(f3_avg, 2),
                "平均1角位置": round(avg_pos1, 1),
                "クラス実績pt": 12,
                "同舞台pt": 12,
                "枠適性pt": 8,
                "騎手ランク": "A" if pop <= 3 else "B",
                "主な実績": "出馬表自動解析データ"
            })

    # ------------------------------------------
    # パターン2: 行単位 / タブ区切り汎用フォールバック
    # ------------------------------------------
    if not horses:
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        for line in lines:
            parts = re.split(r'[\t,]+|\s{2,}', line)
            if len(parts) < 2:
                parts = line.split()
            if not parts:
                continue
                
            num = None
            name = None
            floats = []
            
            for p in parts:
                if num is None and re.match(r'^\d{1,2}$', p):
                    v = int(p)
                    if 1 <= v <= 18:
                        num = v
                        continue
                if name is None and re.match(r'^[ァ-ロワヲンー一-龥a-zA-Z0-9]{2,10}$', p) and not re.match(r'^\d+$', p):
                    if p not in ["出馬表", "確定", "ダート", "浦和", "金沢", "盛岡", "良", "稍重", "重", "不良", "晴", "雨"]:
                        name = p
                        continue
                if re.match(r'^\d+\.\d+$', p):
                    floats.append(float(p))
                    
            if num is not None and name is not None:
                margins = [f for f in floats if f < 10.0]
                times3f = [f for f in floats if 33.0 <= f <= 50.0]
                
                m1 = margins[0] if len(margins) > 0 else 1.5
                m2 = margins[1] if len(margins) > 1 else m1
                m3 = margins[2] if len(margins) > 2 else m2
                m4 = margins[3] if len(margins) > 3 else m3
                m5 = margins[4] if len(margins) > 4 else m4
                
                f3_avg = sum(times3f)/len(times3f) if times3f else 39.5
                waku = (num - 1) // 2 + 1
                
                horses.append({
                    "枠番": min(8, waku),
                    "馬番": num,
                    "馬名": name,
                    "騎手": "未設定",
                    "平均人気": 5.0,
                    "1走前着差": m1,
                    "2走前着差": m2,
                    "3走前着差": m3,
                    "4走前着差": m4,
                    "5走前着差": m5,
                    "上がり3F平均": round(f3_avg, 2),
                    "平均1角位置": 5.0,
                    "クラス実績pt": 12,
                    "同舞台pt": 12,
                    "枠適性pt": 8,
                    "騎手ランク": "B",
                    "主な実績": "出馬表解析データ"
                })

    if not horses:
        return None
        
    df = pd.DataFrame(horses)
    df = df.drop_duplicates(subset=["馬番"]).sort_values("馬番").reset_index(drop=True)
    return df

# ==========================================
# 4. 分析ロジック ＆ 指標算出
# ==========================================

# 1角位置から脚質を判定
def get_style(avg_pos):
    if avg_pos <= 2.2:
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

# レース展開シミュレーション
def analyze_pace(df):
    escape_count = sum(df["脚質タグ"] == "【逃】")
    ahead_count = sum(df["脚質タグ"].isin(["【逃】", "【先】"]))
    
    if escape_count <= 1:
        pace = "【単騎マイペース・スロー】"
        desc = "逃げ馬が少なくペースが上がらないスロー予想。前残り・先行馬が圧倒的有利！"
    elif ahead_count >= 5:
        pace = "【同型競闘・ハイペース】"
        desc = "先行争いが激しくなるハイペース予想。前崩れによる差し・追込馬の急襲に警戒！"
    else:
        pace = "【ミドルペース・平均展開】"
        desc = "標準的な展開。先行馬の粘り込みと好位からの差しが中心。"
    return pace, desc

# データ加工処理
def process_data(df_input):
    df = df_input.copy()
    
    # 重み付け（直近重視: 前走40%, 2走前25%, 3走前15%, 4走前10%, 5走前10%）
    weights = [0.40, 0.25, 0.15, 0.10, 0.10]
    
    weighted_margins = []
    simple_margins = []
    trends = []
    styles = []
    
    for _, row in df.iterrows():
        m_list = [row["1走前着差"], row["2走前着差"], row["3走前着差"], row["4走前着差"], row["5走前着差"]]
        w_avg = sum(m * w for m, w in zip(m_list, weights))
        s_avg = sum(m_list) / len(m_list)
        
        weighted_margins.append(round(w_avg, 2))
        simple_margins.append(round(s_avg, 2))
        trends.append(get_trend(row["1走前着差"], s_avg))
        
        tag, _ = get_style(row["平均1角位置"])
        styles.append(tag)
        
    df["直近加重着差(s)"] = weighted_margins
    df["純粋着差平均(s)"] = simple_margins
    df["トレンド"] = trends
    df["脚質タグ"] = styles
    
    # 総合スコア計算 (最大100pt)
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
# 5. サンプルレースデータ (盛岡5R)
# ==========================================
SAMPLE_RACE = pd.DataFrame([
    {"枠番": 1, "馬番": 1, "馬名": "オッピポイカ", "騎手": "鈴木祐", "平均人気": 2.0, "1走前着差": 2.6, "2走前着差": 0.1, "3走前着差": 1.2, "4走前着差": 1.8, "5走前着差": 3.0, "上がり3F平均": 37.98, "平均1角位置": 2.8, "クラス実績pt": 12, "同舞台pt": 16, "枠適性pt": 8, "騎手ランク": "B", "主な実績": "3歳C2 1着 / 盛岡1200m 1勝"},
    {"枠番": 2, "馬番": 2, "馬名": "ドリタル", "騎手": "菅原辰", "平均人気": 3.0, "1走前着差": 2.9, "2走前着差": 2.1, "3走前着差": 2.5, "4走前着差": 2.8, "5走前着差": 2.0, "上がり3F平均": 38.72, "平均1角位置": 3.2, "クラス実績pt": 20, "同舞台pt": 12, "枠適性pt": 8, "騎手ランク": "S", "主な実績": "A一組・特別出走 (格上)"},
    {"枠番": 3, "馬番": 3, "馬名": "キンカメクオリア", "騎手": "坂井瑛", "平均人気": 8.0, "1走前着差": 4.5, "2走前着差": 3.8, "3走前着差": 4.2, "4走前着差": 4.0, "5走前着差": 4.2, "上がり3F平均": 40.50, "平均1角位置": 8.0, "クラス実績pt": 8, "同舞台pt": 8, "枠適性pt": 8, "騎手ランク": "B", "主な実績": "2歳新馬1着"},
    {"枠番": 4, "馬番": 4, "馬名": "ラスダシャン", "騎手": "関本玲", "平均人気": 5.0, "1走前着差": 3.6, "2走前着差": 1.2, "3走前着差": 1.5, "4走前着差": 1.8, "5走前着差": 1.8, "上がり3F平均": 40.26, "平均1角位置": 5.6, "クラス実績pt": 16, "同舞台pt": 20, "枠適性pt": 8, "騎手ランク": "B", "主な実績": "盛岡1200m 2勝 (最速1:12.8)"},
    {"枠番": 5, "馬番": 5, "馬名": "スチョウプリンセス", "騎手": "村上忍", "平均人気": 1.0, "1走前着差": 0.5, "2走前着差": 1.2, "3走前着差": 2.0, "4走前着差": 2.5, "5走前着差": 2.6, "上がり3F平均": 36.70, "平均1角位置": 1.2, "クラス実績pt": 16, "同舞台pt": 20, "枠適性pt": 10, "騎手ランク": "S", "主な実績": "盛岡1200m 1勝 (1:12.8 圧勝)"},
    {"枠番": 6, "馬番": 6, "馬名": "グラスアラバニーユ", "騎手": "山本政", "平均人気": 4.0, "1走前着差": 1.8, "2走前着差": 1.5, "3走前着差": 1.6, "4走前着差": 1.7, "5走前着差": 1.5, "上がり3F平均": 39.58, "平均1角位置": 6.2, "クラス実績pt": 12, "同舞台pt": 12, "枠適性pt": 8, "騎手ランク": "B", "主な実績": "川崎C2・盛岡C2上位"},
    {"枠番": 7, "馬番": 7, "馬名": "ライヴモヒート", "騎手": "塚本涼", "平均人気": 10.0, "1走前着差": 2.2, "2走前着差": 2.5, "3走前着差": 2.1, "4走前着差": 2.8, "5走前着差": 2.2, "上がり3F平均": 40.92, "平均1角位置": 7.5, "クラス実績pt": 4, "同舞台pt": 8, "枠適性pt": 8, "騎手ランク": "B", "主な実績": "園田C3出走"},
    {"枠番": 8, "馬番": 8, "馬名": "ジーティーウブラブ", "騎手": "阿部英", "平均人気": 11.0, "1走前着差": 3.2, "2走前着差": 2.8, "3走前着差": 3.0, "4走前着差": 3.1, "5走前着差": 3.0, "上がり3F平均": 39.92, "平均1角位置": 7.0, "クラス実績pt": 12, "同舞台pt": 12, "枠適性pt": 8, "騎手ランク": "A", "主な実績": "3歳C1出走 / 1:13.9"},
    {"枠番": 8, "馬番": 9, "馬名": "ディーファンクス", "騎手": "齋藤友", "平均人気": 9.0, "1走前着差": 2.3, "2走前着差": 1.8, "3走前着差": 1.9, "4走前着差": 2.0, "5走前着差": 1.8, "上がり3F平均": 38.56, "平均1角位置": 3.6, "クラス実績pt": 8, "同舞台pt": 16, "枠適性pt": 8, "騎手ランク": "A", "主な実績": "盛岡1200m 1:13.6 (2着)"},
    {"枠番": 8, "馬番": 10, "馬名": "トモエナゲ", "騎手": "山本紀", "平均人気": 7.0, "1走前着差": 2.8, "2走前着差": 2.2, "3走前着差": 2.5, "4走前着差": 2.4, "5走前着差": 2.5, "上がり3F平均": 39.26, "平均1角位置": 6.8, "クラス実績pt": 8, "同舞台pt": 12, "枠適性pt": 8, "騎手ランク": "B", "主な実績": "3歳C2 3着 / 1:14.9"},
    {"枠番": 8, "馬番": 11, "馬名": "グレイスルーラー", "騎手": "高松亮", "平均人気": 6.0, "1走前着差": 2.1, "2走前着差": 2.0, "3走前着差": 1.9, "4走前着差": 2.1, "5走前着差": 2.0, "上がり3F平均": 38.94, "平均1角位置": 7.2, "クラス実績pt": 12, "同舞台pt": 8, "枠適性pt": 8, "騎手ランク": "S", "主な実績": "JRA未勝利 / 高松亮鞍上"}
])

# ==========================================
# 6. メインUIレイアウト
# ==========================================

st.markdown("<div class='main-header'>🏇 地方競馬AI分析 ＆ 基準比較ツール</div>", unsafe_allow_html=True)

# サイドバー設定
st.sidebar.header("⚙️ レース設定 & データ入力")

input_mode = st.sidebar.radio("データ入力モード", ["サンプルデータ(盛岡5R)", "出馬表テキストを貼り付け"])

if input_mode == "サンプルデータ(盛岡5R)":
    raw_df = SAMPLE_RACE
else:
    st.sidebar.info("競馬サイトの出馬表テキストを下にコピペしてください。")
    pasted_text = st.sidebar.text_area("出馬表テキスト貼り付け欄", height=200, placeholder="ここに地方競馬情報サイト等の出馬表テキストをそのままコピペしてください")
    
    parsed_df = parse_pasted_text(pasted_text)
    if parsed_df is not None and len(parsed_df) > 0:
        raw_df = parsed_df
        st.sidebar.success(f"✅ 全{len(raw_df)}頭のデータを自動解析・読み込み完了！")
    else:
        if pasted_text and pasted_text.strip():
            st.sidebar.warning("⚠️ 馬番・馬名を自動検出できませんでした。サンプルを表示します。")
        else:
            st.sidebar.info("👆 テキストを入力すると自動更新されます。")
        raw_df = SAMPLE_RACE

# データ加工
processed_df = process_data(raw_df)

# レース展開カード表示
pace_type, pace_desc = analyze_pace(processed_df)

st.markdown(f"""
<div class='metric-card'>
    <h4>🏁 レース展開シミュレーション</h4>
    <p><b>想定ペース</b>: <span style='color:#D97706; font-size:18px;'>{pace_type}</span></p>
    <p style='color:#374151;'>{pace_desc}</p>
</div>
""", unsafe_allow_html=True)

# ------------------------------------------
# 基準馬（軸馬）選択
# ------------------------------------------
st.subheader("🎯 基準馬（軸馬）の選択と比較")

horse_list = processed_df["馬番"].astype(str) + "番 " + processed_df["馬名"]
selected_horse_str = st.selectbox(
    "比較の基準（軸馬）にする馬を選択してください（直近着差・純粋着差・上がりタイムの差分が自動算出されます）:",
    horse_list,
    index=0
)

# 基準馬データ取得
selected_num = int(selected_horse_str.split("番")[0])
ref_horse = processed_df[processed_df["馬番"] == selected_num].iloc[0]

# 差分算出
processed_df["対基準・加重着差差分(s)"] = (processed_df["直近加重着差(s)"] - ref_horse["直近加重着差(s)"]).round(2)
processed_df["対基準・純粋着差差分(s)"] = (processed_df["純粋着差平均(s)"] - ref_horse["純粋着差平均(s)"]).round(2)
processed_df["対基準・上がり差分(s)"] = (processed_df["上がり3F平均"] - ref_horse["上がり3F平均"]).round(2)

# 表示テーブル調整
display_df = processed_df.copy()

cols = [
    "枠番", "馬番", "馬名", "脚質タグ", "直近加重着差(s)", "対基準・加重着差差分(s)",
    "純粋着差平均(s)", "対基準・純粋着差差分(s)", "上がり3F平均", "対基準・上がり差分(s)",
    "トレンド", "平均人気", "総合スコア"
]
display_df = display_df[cols]

# ------------------------------------------
# ソートコントロール
# ------------------------------------------
st.subheader("📊 分析＆差分比較データテーブル")

sort_col = st.radio(
    "並び替え基準:",
    ["総合スコア順", "対基準・加重着差順(強い順)", "対基準・純粋着差順(強い順)", "上がり3F順(速い順)", "人気順", "馬番順"],
    horizontal=True
)

if sort_col == "総合スコア順":
    display_df = display_df.sort_values(by="総合スコア", ascending=False)
elif sort_col == "対基準・加重着差順(強い順)":
    display_df = display_df.sort_values(by="対基準・加重着差差分(s)", ascending=True)
elif sort_col == "対基準・純粋着差順(強い順)":
    display_df = display_df.sort_values(by="対基準・純粋着差差分(s)", ascending=True)
elif sort_col == "上がり3F順(速い順)":
    display_df = display_df.sort_values(by="上がり3F平均", ascending=True)
elif sort_col == "人気順":
    display_df = display_df.sort_values(by="平均人気", ascending=True)
elif sort_col == "馬番順":
    display_df = display_df.sort_values(by="馬番", ascending=True)

st.dataframe(display_df, use_container_width=True)

st.write("💡 **見方ガイド**: 差分が**マイナス（数値が小さい）**の馬は、基準馬よりも優秀な成績を残している馬です。")
