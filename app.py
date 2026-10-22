import re
import unicodedata

import pandas as pd
import streamlit as st

# =====================================================
# 解析部分（keiba.go.jp 出馬表ページを全選択コピーしたテキスト用）
# =====================================================
MARKS = "▲△☆★◇♢"
# クラス体系（地区ごと）。レベル＝基準値＋番号（小さいほど上位）。番号なしの級は基準値＋1。
# 東海(笠松・名古屋)の番号は「組」。A/B/Cの間は十分離して、別の級どうしは常に大差扱いにする。
SCHEMES = {
    "南関東": (["浦和", "船橋", "大井", "川崎"], {"A": 0, "B": 2, "C": 5}),
    "兵庫": (["園田", "姫路"], {"A": 0, "B": 2, "C": 4}),
    "北海道": (["門別"], {"A": 0, "B": 4, "C": 8}),
    "岩手": (["盛岡", "水沢"], {"A": 0, "B": 1, "C": 3}),
    "東海": (["笠松", "名古屋"], {"A": 0, "B": 20, "C": 40}),
    "高知": (["高知"], {"A": 0, "B": 1, "C": 2}),
    "佐賀": (["佐賀"], {"A": 0, "B": 2, "C": 3}),
}
CLASS_STEP = 0.10  # クラス1段ぶんの加点（クラス実績値）
MAX_STEP = 3  # 加減は最大±3段まで
JRA_LEVEL = -99  # JRAは地方のどのクラスより格上（常に+3段）
TH_FRONT = 0.34  # 1角が頭数の上位1/3以内なら「先行」

HEADER = re.compile(r"^(\d+)\s+(?:(\d+)\s+)?(\S+)\s+(\S+[（(]\S+[）)])\s+(\S+)$")
POP = re.compile(r"^[（(]\s*(\d+)\s*人気\s*[）)]")
PAST1 = re.compile(r"^(.*?)(\d{2}\.\d{2}\.\d{2})\s+(\S+)\s+(\d+)頭$")
PAST2 = re.compile(r"^(\S+)\s+(\S+)\s+(\d+)番$")
SEX = re.compile(r"^(?:牡|牝|セン|セ|騸)\d+")
BEST = re.compile(r"^(\d+:\d{2}\.\d|[－\-])\s+良\s*(\d+:\d{2}\.\d|[－\-])$")
REC = re.compile(r"^(全|左|右|場|距)\s+(\d+)-\s*(\d+)-\s*(\d+)-\s*(\d+)\s*$")
WCHG = re.compile(r"^[（(][+\-＋－±]?\d*[）)]")


def to_sec(t):
    try:
        mm, ss = t.split(":")
        return int(mm) * 60 + float(ss)
    except Exception:
        return None


def to_float(x):
    try:
        return float(x)
    except Exception:
        return None


def scheme_of(venue):
    v = unicodedata.normalize("NFKC", venue or "")
    if v.startswith("J"):
        return "JRA"
    for name, (venues, _) in SCHEMES.items():
        if any(v.startswith(x) for x in venues):
            return name
    return None


def class_level(name, scheme):
    """レース名 → (レベル, 表記)。小さいほど上位。混合戦は最上位側。読めなければ (None, '-')。"""
    if scheme == "JRA":
        return JRA_LEVEL, "JRA"
    if scheme not in SCHEMES:
        return None, "-"
    base = SCHEMES[scheme][1]
    s = unicodedata.normalize("NFKC", name or "")
    found = re.findall(r"(?<![A-Za-z])([ABC])(\d{1,2})(?!\d|歳)", s)
    if not found:
        found = [(c, "") for c in re.findall(r"(?<![A-Za-z])([ABC])(?![A-Za-z\d])", s)]
    if not found:
        return None, "-"
    levels = [base[c] + (int(n) if n else 1) for c, n in found]
    return min(levels), "/".join(dict.fromkeys(c + n for c, n in found))


def parse_race_info(lines):
    info = {"venue": "", "no": "", "title": "", "cond": "", "class": None, "level": None, "scheme": None, "dist": None, "dir": None}
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
                dm = re.search(r"(\d{3,4})m", s2)
                info["dist"] = int(dm.group(1)) if dm else None
                dr = re.search(r"\((左|右)\)", s2)
                info["dir"] = dr.group(1) if dr else None
                break
            if s2:
                title.append(s2)
        info["title"] = " ".join(title)
        info["scheme"] = scheme_of(info["venue"])
        lvl, lab = class_level(info["title"], info["scheme"])
        if lvl is not None:
            info["level"], info["class"] = lvl, lab
        break
    return info


def parse_horse(block, prev_waku):
    m = HEADER.match(block[0].strip())
    g1, g2, name, jockey, odds = m.groups()
    waku, umaban = (int(g1), int(g2)) if g2 else (prev_waku, int(g1))
    pop = int(POP.match(block[1].strip()).group(1))

    j = next(k for k in range(2, len(block)) if SEX.match(block[k].strip()))
    w = next(k for k in range(j + 1, len(block)) if WCHG.match(block[k].strip()))

    # 最高タイム（今回と同一条件＝同競馬場・同距離・同種別での最高）
    bm = next((m for m in (BEST.match(l.strip()) for l in block[2:j]) if m), None)
    best_t = bm.group(1) if bm and bm.group(1)[0].isdigit() else ""

    # 着別成績（1着-2着-3着-4着以下）: 全・左・右・当競馬場(場)・当距離(距)
    rec = {}
    for l in block[2:j]:
        mm = REC.match(l.strip())
        if mm:
            rec[mm.group(1)] = tuple(int(x) for x in mm.groups()[1:])

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

    # 競走成績の各欄（タブ区切りの位置で対応させる。取止・出走前の走は空欄になるため）
    def cells(i, skip):
        if i >= len(block):
            return []
        t = block[i].split("\t")
        return [c.strip() for c in t[skip:]] if len(t) > skip else []

    E1 = re.compile(r"^(?:(\d+)人)?\s*(\S+)\s+(\S+)\s+(\d+(?:\.\d)?)$")  # 人気 馬体重 騎手 斤量
    E2 = re.compile(r"(\d+:\d{2}\.\d)\s+(?:([\d\-]+)\s+)?(\d{2}\.\d)")  # タイム 通過順 上がり
    E3 = re.compile(r"^(\d+\.\d)\s+(\S+)$")  # 1着馬との差 1着馬名
    ent1 = [E1.match(x) for x in cells(w, 1)]
    ent2 = [E2.search(x) for x in cells(w + 1, 2)]
    ent3 = [E3.match(x) for x in cells(w + 2, 3)]

    runs = []
    for k, p in enumerate(past):
        r = dict(p)
        r["走"] = ["前走", "前々走", "3走前", "4走前", "5走前"][k]
        r["レース名"] = names[k] if k < len(names) else ""
        r["区分"] = scheme_of(r["場"])
        r["級順位"], r["級"] = class_level(r["レース名"], r["区分"])
        m1 = ent1[k] if k < len(ent1) else None
        if m1:
            r["人気"] = int(m1.group(1)) if m1.group(1) else None
            r["馬体重"] = m1.group(2)
            jk = m1.group(3)
            r["騎手"] = jk.lstrip(MARKS)
            r["斤量"] = (jk[:1] if jk[:1] in MARKS else "") + m1.group(4)
        m2 = ent2[k] if k < len(ent2) else None
        if m2:
            r["タイム"] = m2.group(1)
            r["通過"] = m2.group(2) or ""
            r["上がり"] = to_float(m2.group(3))
            if r["通過"] and r["通過"][0].isdigit() and r["頭数"] > 0:
                pos = int(r["通過"].split("-")[0])
                r["1角"] = pos
                r["頭数比"] = pos / r["頭数"]
        m3 = ent3[k] if k < len(ent3) else None
        if m3:
            mg = to_float(m3.group(1))
            if mg is not None and r["着順"] is not None:
                r["着差"] = (-mg if mg else 0.0) if r["着順"] == 1 else mg  # 勝ち馬は2着との差をマイナス
            r["1着/2着馬"] = m3.group(2)
        if r.get("タイム") and r.get("距離"):
            mm, ss = r["タイム"].split(":")
            r["秒/200m"] = round((int(mm) * 60 + float(ss)) / r["距離"] * 200, 3)
        if "着差" in r and r.get("距離"):
            r["着差換算"] = round(r["着差"] * 1000 / r["距離"], 3)  # 1000m換算の着差
        if r.get("着順") is not None and "着差" in r:
            gap = 0.0 if r["着順"] == 1 else r["着差"]  # 1着馬との差（勝ち馬は0）
            r["勝差"] = gap
            if r.get("距離"):
                r["勝差換算"] = round(gap * 1000 / r["距離"], 3)
        runs.append(r)

    return {"枠": waku, "馬番": umaban, "馬名": name, "騎手": jockey,
            "odds": to_float(odds), "人気": pop, "best": best_t, "rec": rec, "斤量": kin,
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


def improve(vals):
    """新しい順の値リスト → (古い走の平均 − 新しい走の平均)。正なら向上（小さいほど良い指標）。"""
    n = len(vals)
    if n < 2:
        return None
    nr = 2 if n >= 3 else 1
    rc = avg(vals[:nr])
    pa = avg(vals[nr:])
    return None if rc is None or pa is None else pa - rc


def time_improve(runs, today_dist):
    """同じ距離で2走以上ある距離だけで、1ハロン(200m)あたりのタイムの向上を見る。"""
    g = {}
    for r in runs:
        if r.get("秒/200m") is not None:
            g.setdefault(r["距離"], []).append(r["秒/200m"])
    cands = [(len(v), -abs(d - (today_dist or d)), d) for d, v in g.items() if len(v) >= 2]
    if not cands:
        return None
    v = g[max(cands)[2]]
    nr = max(1, len(v) // 2)
    return avg(v[nr:]) - avg(v[:nr])


def add_index(rows):
    """3つの改善量を、出走馬のばらつきで割って（0＝変化なし）平均 → 向上指数。"""
    keys = ["着差改善", "上がり改善", "タイム改善"]
    sds = {}
    for k in keys:
        xs = [r[k] for r in rows if r[k] is not None]
        if len(xs) >= 2:
            m = sum(xs) / len(xs)
            sds[k] = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5
    for r in rows:
        zs = [r[k] / sds[k] for k in keys if r[k] is not None and sds.get(k)]
        idx = sum(zs) / len(zs) if zs else None
        r["向上指数"] = round(idx, 2) if idx is not None else None
        r["トレンド"] = ("－" if idx is None else "↗向上" if idx >= 0.5 else "↘下降" if idx <= -0.5 else "→横ばい")
        for k in keys:
            r[k] = round(r[k], 2) if r[k] is not None else None
    return rows


def same_race(ra, na, rb, nb):
    """2頭の過去走が同じレースか（日付・場・コース・頭数＋1着馬名の整合）。"""
    k = ("日付", "場", "コース", "頭数")
    if any(ra[x] != rb[x] for x in k):
        return False
    wa, wb = ra.get("1着/2着馬"), rb.get("1着/2着馬")
    if ra["着順"] == 1:
        return wb == na
    if rb["着順"] == 1:
        return wa == nb
    return wa is not None and wa == wb


def _rec(me, you, you_name):
    def diff(k):
        return None if me.get(k) is None or you.get(k) is None else you[k] - me[k]
    d1, d2, d3 = diff("勝差換算"), diff("上がり"), diff("勝差")
    return {
        "相手": you_name, "日付": me["日付"], "場": me["場"], "コース": me["コース"],
        "頭数": me["頭数"], "級": me["級"], "自着順": me["着順"], "相手着順": you["着順"],
        "タイム差(秒)": None if d3 is None else round(d3, 1),
        "着差差(1000m換算)": None if d1 is None else round(d1, 2),
        "上がり差": None if d2 is None else round(d2, 2),
    }


def head_to_head(horses):
    """今回の出走馬どうしが過去に同じレースを走った記録。差は＋なら自分が優勢。"""
    recs = {h["馬番"]: [] for h in horses}
    for x in range(len(horses)):
        for y in range(x + 1, len(horses)):
            A, B = horses[x], horses[y]
            for ra in A["runs"]:
                for rb in B["runs"]:
                    if same_race(ra, A["馬名"], rb, B["馬名"]):
                        recs[A["馬番"]].append(_rec(ra, rb, B["馬名"]))
                        recs[B["馬番"]].append(_rec(rb, ra, A["馬名"]))
    return recs


def add_h2h(rows, recs):
    """対戦成績と、着差差・上がり差を出走馬内のばらつきで割った直接対決指数。"""
    raw = {}
    for r in rows:
        rs = recs.get(r["馬番"], [])
        ok = [x for x in rs if x["自着順"] is not None and x["相手着順"] is not None]
        w = sum(x["自着順"] < x["相手着順"] for x in ok)
        l = sum(x["自着順"] > x["相手着順"] for x in ok)
        r["対戦数"] = len(rs)
        r["対戦成績"] = f"{w}勝{l}敗" if rs else ""
        raw[r["馬番"]] = (avg([x["着差差(1000m換算)"] for x in rs]), avg([x["上がり差"] for x in rs]))
    sds = {}
    for i in (0, 1):
        xs = [v[i] for v in raw.values() if v[i] is not None]
        if len(xs) >= 2:
            m = sum(xs) / len(xs)
            sds[i] = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5
    for r in rows:
        a, b = raw[r["馬番"]]
        zs = [v / sds[i] for i, v in ((0, a), (1, b)) if v is not None and sds.get(i)]
        r["着差差平均"] = round(a, 2) if a is not None else None
        r["上がり差平均"] = round(b, 2) if b is not None else None
        r["直接対決指数"] = round(sum(zs) / len(zs), 2) if zs else None
    return rows


# (列名, 小さいほど良いか, 既定の重み, 表示名)
FACTORS = [
    ("_着差換算平均", True, 30, "着差"),
    ("クラス実績値", False, 20, "クラス実績"),
    ("向上指数", False, 15, "向上"),
    ("直接対決指数", False, 15, "直接対決"),
    ("_持ち秒", True, 10, "持ちタイム"),
    ("上がり平均", True, 10, "上がり"),
    ("適性値", False, 10, "適性"),
]


def add_total(rows, weights):
    """各要素を出走馬内の偏差値(50±10)にして重み付き平均。値のない要素は除き、残りで按分。"""
    total_w = sum(weights.values())
    stats = {}
    for col, _, _, _ in FACTORS:
        xs = [r[col] for r in rows if r.get(col) is not None]
        if len(xs) >= 2:
            m = sum(xs) / len(xs)
            sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5
            if sd > 0:
                stats[col] = (m, sd)
    for r in rows:
        num = den = 0.0
        for col, low, _, key in FACTORS:
            w = weights[key]
            if w > 0 and col in stats and r.get(col) is not None:
                m, sd = stats[col]
                z = (m - r[col]) / sd if low else (r[col] - m) / sd
                num += w * (50 + 10 * max(-3.0, min(3.0, z)))
                den += w
        r["総合点"] = round(num / den, 1) if den else None
        r["根拠率"] = f"{round(den / total_w * 100)}%" if total_w else ""
    scores = [r["総合点"] for r in rows if r["総合点"] is not None]
    for r in rows:
        r["総合順位"] = 1 + sum(x > r["総合点"] for x in scores) if r["総合点"] is not None else None
        r["妙味"] = r["今回人気"] - r["総合順位"] if r["総合順位"] is not None else None
    return rows


def rec_info(t):
    """着別成績(1-2-3-4着以下) → (表示文字列, 複勝率)。"""
    if not t:
        return "", None
    n = sum(t)
    rate = (t[0] + t[1] + t[2]) / n if n else None
    txt = f"{t[0]}-{t[1]}-{t[2]}-{t[3]}" + (f" ({rate * 100:.0f}%)" if rate is not None else "")
    return txt, rate


def shrunk(t, prior, k=3):
    """出走が少ない条件の複勝率が極端にならないよう、全体の複勝率へ寄せる。"""
    if not t or sum(t) == 0:
        return None
    return ((t[0] + t[1] + t[2]) + k * prior) / (sum(t) + k)


def analyze(h, today_rank, n_today, today_dist=None, today_dir=None, today_scheme=None):
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

    def usable(r):  # 今回と同じ地区のクラス体系の走（JRAは常に可）だけ比べる
        return r["級順位"] is not None and r["区分"] in (today_scheme, "JRA")

    if today_rank is None:
        cls_txt = "判定不可"
    else:
        cr = [r for r in runs if usable(r) and r["着順"] is not None and r["級順位"] <= today_rank]
        fins = [r["着順"] for r in cr if r["着順"] is not None]
        cls_txt = "なし" if not cr else f"{len(cr)}走" + (
            f" 平均{avg(fins):.1f}着/最高{min(fins)}着" if fins else "")

    cv = None
    if today_rank is not None:
        sc = [
            1 - (r["着順"] - 1) / max(r["頭数"] - 1, 1)
            + CLASS_STEP * max(-MAX_STEP, min(MAX_STEP, today_rank - r["級順位"]))
            for r in runs if usable(r) and r["着順"] is not None
        ]
        cv = round(avg(sc), 2) if sc else None

    rc = h.get("rec", {})
    t_all = rc.get("全")
    prior = rec_info(t_all)[1] if t_all and sum(t_all) else 0.3
    apt = [x for x in (shrunk(rc.get("場"), prior), shrunk(rc.get("距"), prior)) if x is not None]
    aptitude = round(sum(apt) / len(apt), 3) if apt else None

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
        "持ちタイム": h["best"] or "－",
        "_持ち秒": to_sec(h["best"]) if h["best"] else None,
        "_着差換算平均": avg([r.get("着差換算") for r in runs]),
        "着差改善": improve([r.get("着差換算") for r in runs]),
        "上がり改善": improve([r.get("上がり") for r in runs]),
        "タイム改善": time_improve(runs, today_dist),
        "脚質": style,
        "1角平均": round(avg(poss), 1) if poss else None,
        "頭数比": round(a_rel, 2) if a_rel is not None else None,
        "先行回数": f"{front}/{len(rels)}",
        "今回想定1角": f"約{max(1, round(a_rel * n_today))}番手" if a_rel is not None else "",
        "クラス実績(同格以上)": cls_txt,
        "クラス実績値": cv,
        "全成績": rec_info(rc.get("全"))[0],
        "当場成績": rec_info(rc.get("場"))[0],
        "当距離成績": rec_info(rc.get("距"))[0],
        "当回り成績": rec_info(rc.get(today_dir))[0] if today_dir else "",
        "適性値": aptitude,
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

manual = st.sidebar.text_input("今回のクラス（手入力・例 C7 / A2）", placeholder=f"空欄で自動({info['class'] or '判定不可'})")
if manual.strip():
    today_level, cls = class_level(manual.strip(), info["scheme"])
else:
    today_level, cls = info["level"], info["class"]

st.markdown(f"**{info['venue']} {info['no']}R** {info['title']}  \n{info['cond']}　／　{len(horses)}頭　／　今回クラス: {cls or '不明'}")

st.sidebar.markdown("**総合点の重み**（0にするとその要素を除外）")
weights = {key: st.sidebar.slider(key, 0, 100, dw, 5) for _, _, dw, key in FACTORS}

h2h = head_to_head(horses)
rows = add_total(
    add_h2h(add_index([analyze(h, today_level, len(horses), info["dist"], info["dir"], info["scheme"]) for h in horses]), h2h),
    weights,
)
df = pd.DataFrame(rows)

DESC = ("総合点", "妙味", "向上指数", "直接対決指数", "クラス実績値", "適性値")
sort_by = st.radio(
    "並び替え",
    ["総合点", "馬番", "妙味", "直接対決指数", "向上指数", "クラス実績値", "適性値", "今回人気",
     "人気平均", "着差平均", "上がり平均", "頭数比"],
    horizontal=True,
)
df = df.sort_values(sort_by, ascending=(sort_by not in DESC), na_position="last")
lead = ["馬番", "馬名", "総合順位", "総合点", "根拠率", "今回人気", "妙味"]
df = df[lead + [c for c in df.columns if c not in lead and not c.startswith("_")]]
st.dataframe(df, hide_index=True)
top = sorted([r for r in rows if r["総合順位"]], key=lambda r: r["総合順位"])[:3]
if top:
    st.markdown("**総合上位**: " + " ／ ".join(f"{r['総合順位']}位 {r['馬番']}番{r['馬名']}({r['総合点']})" for r in top))
val = [r for r in rows if r["妙味"] is not None and r["妙味"] >= 3]
if val:
    st.markdown("**人気より総合点が高い馬（妙味候補）**: " + "、".join(
        f"{r['馬番']}番{r['馬名']}({r['今回人気']}人気→総合{r['総合順位']}位)" for r in val))
st.caption(
    "【総合点】着差・クラス実績・向上・直接対決・持ちタイム・上がりを、各々出走馬内の偏差値(50±10)にして"
    "サイドバーの重みで平均。値がない要素は除いて残りで計算し、根拠率＝使えた重みの割合（低いほど参考程度）。"
    "妙味＝今回人気−総合順位（＋なら人気より評価が高い）。持ちタイムは今回と同じ競馬場・距離での最高タイム。"
    "【適性値】当競馬場・当距離の複勝率（出走が少ない条件は全体の複勝率へ寄せて補正）の平均。"
    "成績欄は『1着-2着-3着-4着以下（複勝率）』、全成績はJRA・海外を含み、当回りは今回の左右回りの成績(JRA含む)。"
    "重みは仮置きで、的中結果で検証していないため参考値です。"
)
st.caption(
    "○＝その馬の5走平均より良い走（着差が小さい／上がりが速い）。左から前走→5走前。"
    "着差は1着馬との差（自分が1着の時は2着との差をマイナスで表示）。"
    "脚質は1角位置÷頭数の平均（逃≤0.2／先≤0.4／差≤0.65／追）。先行回数は1角が頭数の上位1/3以内だった走。クラス実績は、今回と同じ地区のクラス表記（A1・C2、笠松は「Ｃ７」など）が読めた走だけ判定（混合戦は上位側。JRAは格上。未格付や別地区の走は対象外）。"
)

st.caption(
    "【向上指数】直近2走と、それ以前（3〜5走前）を比べた改善量を3項目で出し、出走馬内のばらつきで割って平均したもの。"
    "0＝変化なし、＋が向上、−が下降（±0.5で↗/↘）。"
    "着差改善＝着差(1000m換算・秒)の縮まり、上がり改善＝上がり3Fの短縮(秒)、"
    "タイム改善＝同じ距離の走どうしの1ハロン(200m)あたりタイムの短縮(秒)。"
    "距離・馬場・相手が違う走を比べるため目安です。同距離の走が2走未満の馬はタイムの項目が空欄になります。"
)

st.caption(
    "【直接対決指数】今回の出走馬どうしが過去に同じレースを走っていた場合の、相手との差。"
    "着差差(1000m換算・秒)と上がり差を、出走馬内のばらつきで割って平均（＋＝相手より優勢、同じレース内の着差差＝タイム差）。"
    "【クラス実績値】過去走ごとに『着順の位置(1着＝1、最下位＝0)』に、今回との格差1段あたり"
    f"{CLASS_STEP}を加減(最大±{MAX_STEP}段、JRAは常に+{MAX_STEP}段)して平均。"
    "今回と同じ地区(南関東・兵庫・東海など)のクラス体系で読めた走だけを対象にし、別地区の走は除外。"
)

front = [r["馬名"] for r in rows if r["脚質"] in ("逃", "先")]
st.markdown(f"**逃げ・先行タイプ: {len(front)}頭** {'、'.join(front)}")

st.markdown("#### 馬別 過去5走")
sel = st.selectbox("馬を選択", [f"{h['馬番']} {h['馬名']}" for h in horses])
h = next(x for x in horses if f"{x['馬番']} {x['馬名']}" == sel)
st.caption(f"{h['騎手']}　斤量{h['斤量']}　馬体重{h['馬体重']}")
cols = ["走", "日付", "場", "コース", "馬場", "頭数", "級", "着順", "人気", "着差",
        "着差換算", "上がり", "秒/200m", "通過", "騎手", "斤量", "レース名"]
detail = pd.DataFrame(h["runs"])
st.dataframe(detail[[c for c in cols if c in detail.columns]], hide_index=True)

st.markdown("#### 直接対決（同じレースを走った相手）")
sel2 = st.selectbox("基準にする馬", [f"{x['馬番']} {x['馬名']}" for x in horses], key="h2h_sel")
rs = h2h.get(int(sel2.split()[0]), [])
if rs:
    st.dataframe(pd.DataFrame(rs), hide_index=True)
    st.caption("差は＋なら選んだ馬のほうが優勢（先着・着差が小さい・上がりが速い）。")
else:
    st.info("この馬と今回の出走馬が同じレースを走った記録は、過去5走の中にありません。")
