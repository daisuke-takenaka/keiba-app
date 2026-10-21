import re
import unicodedata

import pandas as pd
import streamlit as st

# =====================================================
# 解析部分（keiba.go.jp 出馬表ページを全選択コピーしたテキスト用）
# =====================================================
MARKS = "▲△☆★◇♢"
CLASSES = ["A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3"]  # 左ほど格上
TH_FRONT = 0.34  # 1角が頭数の上位1/3以内なら「先行」

HEADER = re.compile(r"^(\d+)\s+(?:(\d+)\s+)?(\S+)\s+(\S+[（(]\S+[）)])\s+(\S+)$")
POP = re.compile(r"^[（(]\s*(\d+)\s*人気\s*[）)]")
PAST1 = re.compile(r"^(.*?)(\d{2}\.\d{2}\.\d{2})\s+(\S+)\s+(\d+)頭$")
PAST2 = re.compile(r"^(\S+)\s+(\S+)\s+(\d+)番$")
SEX = re.compile(r"^(?:牡|牝|セン|セ|騸)\d+")
WCHG = re.compile(r"^[（(][+\-＋－±]?\d*[）)]")


def to_float(x):
    try:
        return float(x)
    except Exception:
        return None


def class_ranks(name):
    s = unicodedata.normalize("NFKC", name or "")
    found = [c for c in re.findall(r"(?<![A-Za-z])([ABC][1-3])", s) if c in CLASSES]
    return [CLASSES.index(c) for c in found], found


def parse_race_info(lines):
    info = {"venue": "", "no": "", "title": "", "cond": "", "class": None}
    for i, l in enumerate(lines):
        s = unicodedata.normalize("NFKC", l)
        m = re.search(r"\d{4}年\d+月\d+日\(.\)\s*(.+?)\s*第(\d+)競走", s)
        if not m:
            continue
        info["venue"] = m.group(1).replace(" ", "")
        info["no"] = m.group(2)
        title = []
        for l2 in lines[i + 1:i + 8]:
            s2 = unicodedata.normalize("NFKC", l2).strip()
            if re.match(r"^(ダート|芝)", s2):
                info["cond"] = s2
                break
            if s2:
                title.append(s2)
        info["title"] = " ".join(title)
        ranks, found = class_ranks(info["title"])
        if ranks:
            info["class"] = CLASSES[min(ranks)]
        break
    return info


def parse_horse(block, prev_waku):
    m = HEADER.match(block[0].strip())
    g1, g2, name, jockey, odds = m.groups()
    waku, umaban = (int(g1), int(g2)) if g2 else (prev_waku, int(g1))
    pop = int(POP.match(block[1].strip()).group(1))

    j = next(k for k in range(2, len(block)) if SEX.match(block[k].strip()))
    w = next(k for k in range(j + 1, len(block)) if WCHG.match(block[k].strip()))

    # 過去走の基本情報（日付・着順・頭数・コース）
    past, i = [], 2
    while i < j - 1 and len(past) < 5:
        a = PAST1.match(block[i].strip())
        b = PAST2.match(block[i + 1].strip()) if a else None
        if a and b:
            fin = a.group(1).strip()
            dist = re.search(r"(\d{3,4})", b.group(2))
            past.append({
                "日付": a.group(2),
                "着順": int(fin) if fin.isdigit() else None,
                "馬場": a.group(3),
                "頭数": int(a.group(4)),
                "場": b.group(1),
                "コース": b.group(2),
                "距離": int(dist.group(1)) if dist else None,
            })
            i += 2
        else:
            i += 1

    # 性齢・斤量・過去5走のレース名
    toks = block[j].split("\t")
    wm = re.search(r"([▲△☆★◇♢]?)\s*(\d{2}\.\d)\s+\d+-\d+-\d+-\d+", block[j])
    kin = (wm.group(1) + wm.group(2)) if wm else ""
    names = [t.strip() for t in toks[4:]]
    for l in block[j + 1:w - 1]:
        names += [t.strip() for t in l.split("\t")]
    names = [n for n in names if n][:5]

    sire = block[w - 1].split("\t")
    weight = sire[2].strip() if len(sire) > 2 else ""
    wchg = block[w].split("\t")[0].strip()

    # 人気・馬体重・騎手・斤量
    ent1 = re.findall(r"(\d+)人\s+(\S+)\s+(\S+)\s+(\d+(?:\.\d)?)", block[w])
    # タイム・通過順・上がり
    ent2 = re.findall(r"(\d+:\d{2}\.\d)\s+(?:([\d\-]+)\s+)?(\d{2}\.\d)",
                      block[w + 1] if w + 1 < len(block) else "")
    # 1着馬との差・1着馬名
    ent3 = []
    if w + 2 < len(block):
        t3 = block[w + 2].split("\t")
        tail = "\t".join(t3[2:]) if len(t3) > 2 else block[w + 2]
        ent3 = re.findall(r"(\d+\.\d)\s+(\S+)", tail)

    runs = []
    for k, p in enumerate(past):
        r = dict(p)
        r["走"] = ["前走", "前々走", "3走前", "4走前", "5走前"][k]
        r["レース名"] = names[k] if k < len(names) else ""
        ranks, found = class_ranks(r["レース名"])
        r["級順位"] = min(ranks) if ranks else None
        r["級"] = "/".join(dict.fromkeys(found)) if found else "-"
        if unicodedata.normalize("NFKC", r["場"]).startswith("J"):
            r["級順位"], r["級"] = -1, "JRA"  # 中央（Ｊ○○）は地方のどのクラスより格上扱い
        if k < len(ent1):
            r["人気"] = int(ent1[k][0])
            r["馬体重"] = ent1[k][1]
            r["騎手"] = ent1[k][2].lstrip(MARKS)
            r["斤量"] = ent1[k][2][:1] if ent1[k][2][:1] in MARKS else ""
            r["斤量"] += ent1[k][3]
        if k < len(ent2):
            r["タイム"] = ent2[k][0]
            r["通過"] = ent2[k][1] or ""
            r["上がり"] = to_float(ent2[k][2])
            if r["通過"] and r["通過"][0].isdigit():
                pos = int(r["通過"].split("-")[0])
                r["1角"] = pos
                r["頭数比"] = pos / r["頭数"]
        if k < len(ent3):
            mg = to_float(ent3[k][0])
            if mg is not None and r["着順"] is not None:
                r["着差"] = (-mg if mg else 0.0) if r["着順"] == 1 else mg  # 勝ち馬は2着との差をマイナス
            r["1着/2着馬"] = ent3[k][1]
        runs.append(r)

    return {"枠": waku, "馬番": umaban, "馬名": name, "騎手": jockey,
            "odds": to_float(odds), "人気": pop, "斤量": kin,
            "馬体重": f"{weight}({wchg.strip('()（）')})" if weight else "",
            "runs": runs}


def parse_text(text):
    lines = [l.rstrip("\r") for l in text.splitlines()]
    info = parse_race_info(lines)
    starts = [i for i in range(len(lines) - 1)
              if HEADER.match(lines[i].strip()) and POP.match(lines[i + 1].strip())]
    end = next((i for i, l in enumerate(lines) if l.startswith("コースレコード")), len(lines))
    ends = starts[1:] + [end]
    horses, errors, prev = [], [], None
    for s, e in zip(starts, ends):
        try:
            h = parse_horse(lines[s:e], prev)
            prev = h["枠"]
            horses.append(h)
        except Exception as ex:
            errors.append(f"{lines[s].strip()[:20]}… ({ex})")
    return info, horses, errors


# =====================================================
# 指標の計算
# =====================================================
def vs_mean(vals):
    """平均と、各走が平均より良い(<=)かの○×を返す。小さいほど良い指標用。"""
    xs = [v for v in vals if v is not None]
    if not xs:
        return None, "", 0, 0
    mean = sum(xs) / len(xs)
    marks = "".join("－" if v is None else ("○" if v <= mean else "×") for v in vals)
    return mean, marks, sum(v <= mean for v in xs), len(xs)


def avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def analyze(h, today_rank, n_today):
    runs = h["runs"]
    m_mean, m_marks, m_good, m_n = vs_mean([r.get("着差") for r in runs])
    f_mean, f_marks, f_good, f_n = vs_mean([r.get("上がり") for r in runs])
    rels = [r["頭数比"] for r in runs if "頭数比" in r]
    poss = [r["1角"] for r in runs if "1角" in r]
    front = sum(1 for x in rels if x <= TH_FRONT)
    a_rel = avg(rels)
    if a_rel is None:
        style = "不明"
    elif a_rel <= 0.20:
        style = "逃"
    elif a_rel <= 0.40:
        style = "先"
    elif a_rel <= 0.65:
        style = "差"
    else:
        style = "追"

    if today_rank is None:
        cls_txt = "判定不可"
    else:
        cr = [r for r in runs if r["級順位"] is not None and r["級順位"] <= today_rank]
        fins = [r["着順"] for r in cr if r["着順"] is not None]
        cls_txt = "なし" if not cr else f"{len(cr)}走" + (
            f" 平均{avg(fins):.1f}着/最高{min(fins)}着" if fins else "")

    jname = re.sub(r"[（(].*?[）)]", "", h["騎手"])
    rides = [r for r in runs if r.get("騎手") == jname]
    jf = [r["着順"] for r in rides if r["着順"] is not None]
    kind = "継続" if runs and runs[0].get("騎手") == jname else "乗替"
    jtxt = f"{jname} {kind}"
    if rides and jf:
        jtxt += f"(この騎手で{len(rides)}走 平均{avg(jf):.1f}着)"

    return {
        "馬番": h["馬番"], "馬名": h["馬名"],
        "今回人気": h["人気"], "オッズ": h["odds"],
        "人気平均": round(avg([r.get("人気") for r in runs]), 1) if runs else None,
        "着差平均": round(m_mean, 2) if m_mean is not None else None,
        "着差(前走→)": f"{m_marks} {m_good}/{m_n}",
        "上がり平均": round(f_mean, 2) if f_mean is not None else None,
        "上がり(前走→)": f"{f_marks} {f_good}/{f_n}",
        "脚質": style,
        "1角平均": round(avg(poss), 1) if poss else None,
        "頭数比": round(a_rel, 2) if a_rel is not None else None,
        "先行回数": f"{front}/{len(rels)}",
        "今回想定1角": f"約{max(1, round(a_rel * n_today))}番手" if a_rel is not None else "",
        "クラス実績(同格以上)": cls_txt,
        "騎手": jtxt,
    }


# ===UI===
st.set_page_config(page_title="出馬表アナライザー", page_icon="🏇", layout="wide")


def check_password():
    try:
        pw = st.secrets["password"]
    except Exception:
        return True  # Secrets未設定ならログインなし
    if st.session_state.get("ok"):
        return True
    st.title("🔒 ログイン")
    x = st.text_input("パスワード", type="password")
    if st.button("ログイン"):
        if x == pw:
            st.session_state["ok"] = True
            st.rerun()
        else:
            st.error("パスワードが違います")
    return False


if not check_password():
    st.stop()

st.markdown("### 🏇 地方競馬 出馬表アナライザー")
text = st.text_area(
    "出馬表ページを全選択コピーして貼り付け",
    height=120,
    placeholder="keiba.go.jp の出馬表ページ（DebaTable）を全選択→コピー→ここに貼り付け",
)
if not text.strip():
    st.info("👆 出馬表ページ全体を貼り付けると、自動で解析します。")
    st.stop()

info, horses, errors = parse_text(text)
if not horses:
    st.error("出走馬を読み取れませんでした。ページ全体（馬名〜成績まで）をコピーしているか確認してください。")
    st.stop()
if errors:
    st.warning("読み取れなかった馬: " + " / ".join(errors))

auto = info["class"]
choice = st.sidebar.selectbox("今回のクラス", [f"自動({auto or '判定不可'})"] + CLASSES)
cls = auto if choice.startswith("自動") else choice
today_rank = CLASSES.index(cls) if cls else None

st.markdown(f"**{info['venue']} {info['no']}R** {info['title']}  \n{info['cond']}　／　{len(horses)}頭　／　今回クラス: {cls or '不明'}")

rows = [analyze(h, today_rank, len(horses)) for h in horses]
df = pd.DataFrame(rows)

sort_by = st.radio(
    "並び替え",
    ["馬番", "今回人気", "人気平均", "着差平均", "上がり平均", "頭数比"],
    horizontal=True,
)
df = df.sort_values(sort_by, na_position="last")
st.dataframe(df, hide_index=True)
st.caption(
    "○＝その馬の5走平均より良い走（着差が小さい／上がりが速い）。左から前走→5走前。"
    "着差は1着馬との差（自分が1着の時は2着との差をマイナスで表示）。"
    "脚質は1角位置÷頭数の平均（逃≤0.2／先≤0.4／差≤0.65／追）。先行回数は1角が頭数の上位1/3以内だった走。クラス実績は、過去走のレース名にC1等の表記がある走だけ判定（C1/C2混合戦は格上側で数えます。JRAは格上として必ず数え、未格付・「Ａ一組」など数字のない表記は対象外）。"
)

front = [r["馬名"] for r in rows if r["脚質"] in ("逃", "先")]
st.markdown(f"**逃げ・先行タイプ: {len(front)}頭** {'、'.join(front)}")

st.markdown("#### 馬別 過去5走")
sel = st.selectbox("馬を選択", [f"{h['馬番']} {h['馬名']}" for h in horses])
h = next(x for x in horses if f"{x['馬番']} {x['馬名']}" == sel)
st.caption(f"{h['騎手']}　斤量{h['斤量']}　馬体重{h['馬体重']}")
cols = ["走", "日付", "場", "コース", "馬場", "頭数", "級", "着順", "人気", "着差",
        "上がり", "通過", "騎手", "斤量", "レース名"]
detail = pd.DataFrame(h["runs"])
st.dataframe(detail[[c for c in cols if c in detail.columns]], hide_index=True)
