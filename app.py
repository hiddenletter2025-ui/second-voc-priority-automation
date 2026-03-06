"""
VoC Risk Sentinel Dashboard
Run: streamlit run app.py
"""

import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ── Page Config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="VoC Risk Sentinel",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Dark Mode CSS ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
/* 배경 */
[data-testid="stAppViewContainer"] { background-color: #0D1117; }
[data-testid="stHeader"]           { background-color: #0D1117; }
[data-testid="stSidebar"]          { background-color: #161B22; border-right: 1px solid #30363D; }
[data-testid="stSidebarContent"]   { padding-top: 24px; }

/* 공통 텍스트 */
body, p, label, div { color: #C9D1D9; }

/* KPI 카드 */
.kpi-card {
    background: linear-gradient(145deg, #161B22 0%, #1C2333 100%);
    border: 1px solid #30363D;
    border-radius: 14px;
    padding: 22px 24px 18px;
    margin: 4px 0 8px;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
    min-height: 110px;
}
.kpi-card:hover { transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,0.4); }
.kpi-label  { font-size: 12px; font-weight: 600; color: #8B949E; letter-spacing: 0.6px;
              text-transform: uppercase; margin-bottom: 8px; }
.kpi-value  { font-size: 38px; font-weight: 700; color: #E6EDF3; line-height: 1.1; }
.kpi-sub    { font-size: 12px; color: #6E7681; margin-top: 6px; }
.kpi-critical { border-left: 4px solid #FF4757; }
.kpi-abuse    { border-left: 4px solid #ECCC68; }
.kpi-total    { border-left: 4px solid #58A6FF; }
.kpi-avg      { border-left: 4px solid #3FB950; }
.kpi-warn     { border-left: 4px solid #FF6B35; }

/* 섹션 라벨 */
.sec { font-size: 11px; font-weight: 700; color: #6E7681; letter-spacing: 1px;
       text-transform: uppercase; padding: 14px 0 6px;
       border-bottom: 1px solid #21262D; margin-bottom: 10px; }

/* 상세 패널 */
.detail-panel {
    background: #161B22; border: 1px solid #30363D; border-radius: 14px;
    padding: 24px 28px; margin-top: 16px;
}
.dl  { font-size: 11px; font-weight: 600; color: #8B949E; text-transform: uppercase;
       letter-spacing: 0.5px; margin-bottom: 4px; }
.dv  { font-size: 15px; color: #E6EDF3; margin-bottom: 18px; line-height: 1.5; }
.voc-box {
    background: #0D1117; border-radius: 10px; padding: 14px 18px;
    color: #C9D1D9; line-height: 1.7; font-size: 14px; margin-bottom: 18px;
}
.reason-box {
    background: #0D1117;
    border-left: 4px solid #58A6FF;
    border-radius: 0 10px 10px 0;
    padding: 12px 18px; color: #A3BDDB; font-style: italic; font-size: 14px;
}

/* 리스크 배지 */
.badge { display:inline-block; padding:3px 12px; border-radius:20px;
         font-size:12px; font-weight:700; letter-spacing:0.3px; }
.b5 { background:#FF4757; color:#fff; }
.b4 { background:#FF6B35; color:#fff; }
.b3 { background:#FFA502; color:#000; }
.b2 { background:#2ED573; color:#000; }
.b1 { background:#636E72; color:#fff; }

/* 버튼 */
div.stButton > button {
    background: #21262D; color: #C9D1D9; border: 1px solid #30363D;
    border-radius: 8px; font-size: 13px; padding: 6px 16px;
    transition: all 0.15s;
}
div.stButton > button:hover { background: #30363D; border-color: #58A6FF; color: #E6EDF3; }

/* 다운로드 버튼 */
[data-testid="stDownloadButton"] > button {
    background: #1C2333; color: #58A6FF; border: 1px solid #30363D; border-radius: 8px;
}
[data-testid="stDownloadButton"] > button:hover { background: #30363D; }

/* 데이터프레임 */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

/* 슬라이더 */
[data-testid="stSlider"] > div > div { background: #30363D; }

/* 캡션 */
[data-testid="stCaptionContainer"] > p { color: #6E7681 !important; }

/* 구분선 */
hr { border-color: #21262D !important; margin: 10px 0 !important; }

/* 알림 박스 */
[data-testid="stAlert"] { background: #1C2333; border-color: #30363D; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent

SCORE_LABEL = {5: "Critical", 4: "High", 3: "Medium", 2: "Low", 1: "Minimal"}
SCORE_COLOR = {5: "#FF4757", 4: "#FF6B35", 3: "#FFA502", 2: "#2ED573", 1: "#636E72"}
TYPE_COLOR  = {
    "legal":   "#FF4757",
    "system":  "#FFA502",
    "abuse":   "#ECCC68",
    "normal":  "#2ED573",
    "unknown": "#636E72",
}
TYPE_KO = {
    "legal":   "법적 위험",
    "system":  "시스템 결함",
    "abuse":   "어뷰징 의심",
    "normal":  "일반",
    "unknown": "미분류",
}
BADGE_CLS = {5: "b5", 4: "b4", 3: "b3", 2: "b2", 1: "b1"}

# 결과 파일 후보 경로 (우선순위 순)
# app.py 위치 기준으로 가능한 모든 경로를 탐색
RESULT_CANDIDATES = [
    BASE_DIR / "src" / "voc_results.jsonl",   # 루트에서 실행 시
    BASE_DIR / "voc_results.jsonl",            # src/ 안에서 실행 시
    BASE_DIR.parent / "src" / "voc_results.jsonl",  # 하위 폴더에서 실행 시
]
RAW_CANDIDATES = [
    BASE_DIR / "outputs" / "voc_data_4000.csv",        # 루트에서 실행 (현재 구조)
    BASE_DIR / "src" / "voc_data_4000.csv",            # src/ 안에 있는 경우
    BASE_DIR / "voc_data_4000.csv",                    # 루트에 있는 경우
    BASE_DIR.parent / "outputs" / "voc_data_4000.csv", # 하위 폴더에서 실행 시
]

# ── Data Loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_data():
    """JSONL 로드 → DataFrame 변환 → 원본 CSV와 병합 (있을 때)"""

    # 1. 결과 파일 탐색
    result_path = next((p for p in RESULT_CANDIDATES if p.exists()), None)
    if result_path is None:
        return None, (
            f"분석 결과 파일(`voc_results.jsonl`)을 찾을 수 없습니다.\n\n"
            f"**먼저 파이프라인을 실행하세요:**\n```bash\ncd src\npython analyze_voc.py ../outputs/voc_data_4000.csv\n```"
        )

    # 2. JSONL 파싱
    records = []
    with result_path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                st.warning(f"라인 {i} 파싱 실패 (스킵): {e}")

    if not records:
        return None, "파일이 비어있거나 모든 라인 파싱에 실패했습니다."

    df = pd.DataFrame(records)

    # 3. 컬럼 타입 보정
    df["risk_score"] = (
        pd.to_numeric(df.get("risk_score", 3), errors="coerce")
        .fillna(3).astype(int).clip(1, 5)
    )
    df["risk_type"]   = df.get("risk_type",   pd.Series(["unknown"] * len(df))).fillna("unknown")
    df["reason"]      = df.get("reason",      pd.Series([""] * len(df))).fillna("")
    df["triggered_by"]= df.get("triggered_by",pd.Series(["rule"] * len(df))).fillna("rule")
    df["risk_label"]  = df["risk_score"].map(SCORE_LABEL)
    df["type_ko"]     = df["risk_type"].map(TYPE_KO).fillna("미분류")

    # 4. 원본 CSV 병합 (voc_content, ad_type 등 보강)
    raw_path = next((p for p in RAW_CANDIDATES if p.exists()), None)
    if raw_path:
        useful = ["voc_id", "voc_content", "ad_type", "ad_name", "created_at", "user_id"]
        raw = pd.read_csv(
            raw_path, encoding="utf-8-sig",
            usecols=lambda c: c in useful,
        )
        df = df.merge(raw, on="voc_id", how="left")

    # 5. 없는 컬럼 기본값
    for col, default in [
        ("voc_content", "(원문 없음)"),
        ("ad_type",     "미상"),
        ("ad_name",     ""),
        ("created_at",  ""),
        ("user_id",     ""),
    ]:
        if col not in df.columns:
            df[col] = default
        df[col] = df[col].fillna(default)

    return df.sort_values("risk_score", ascending=False).reset_index(drop=True), None


# ── Chart Helpers ─────────────────────────────────────────────────────────────

def make_donut(df: pd.DataFrame) -> go.Figure:
    counts = df["risk_type"].value_counts()
    if counts.empty:
        return go.Figure()
    colors   = [TYPE_COLOR.get(t, "#636E72") for t in counts.index]
    labels_ko= [TYPE_KO.get(t, t) for t in counts.index]

    fig = go.Figure(go.Pie(
        labels=labels_ko,
        values=counts.values,
        hole=0.64,
        marker=dict(colors=colors, line=dict(color="#0D1117", width=3)),
        textinfo="label+percent",
        textfont=dict(size=12, color="#E6EDF3"),
        hovertemplate="%{label}: <b>%{value}건</b> (%{percent})<extra></extra>",
    ))
    fig.add_annotation(
        text=f"<b>{len(df):,}</b><br><span style='font-size:11px'>총 분석</span>",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=18, color="#E6EDF3"),
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#E6EDF3", showlegend=True,
        legend=dict(
            orientation="v", yanchor="middle", y=0.5,
            xanchor="left", x=1.02,
            font=dict(size=12, color="#C9D1D9"),
            bgcolor="rgba(0,0,0,0)",
        ),
        margin=dict(t=10, b=10, l=10, r=90),
        height=270,
    )
    return fig


def make_score_bar(df: pd.DataFrame) -> go.Figure:
    counts = df["risk_score"].value_counts().reindex(range(1, 6), fill_value=0).sort_index()
    colors = [SCORE_COLOR.get(s, "#636E72") for s in counts.index]

    fig = go.Figure(go.Bar(
        x=counts.index,
        y=counts.values,
        marker_color=colors,
        marker_line=dict(color="#0D1117", width=1.5),
        text=counts.values,
        textposition="outside",
        textfont=dict(color="#C9D1D9", size=12),
        hovertemplate="Score %{x} · <b>%{y}건</b><extra></extra>",
        width=0.6,
    ))
    fig.update_xaxes(
        tickvals=list(range(1, 6)),
        ticktext=[f"{SCORE_LABEL.get(s,'')}<br><span style='font-size:10px'>Lv.{s}</span>"
                  for s in range(1, 6)],
        tickfont=dict(color="#8B949E", size=11),
        showgrid=False, zeroline=False,
    )
    fig.update_yaxes(
        showgrid=True, gridcolor="#21262D",
        zeroline=False, tickfont=dict(color="#8B949E"),
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=20, b=10, l=10, r=10), height=270,
    )
    return fig


def make_trigger_donut(df: pd.DataFrame) -> go.Figure:
    counts = df["triggered_by"].value_counts()
    if counts.empty:
        return go.Figure()
    label_map = {"rule": "Rule 탐지", "audit": "랜덤 감사"}

    fig = go.Figure(go.Pie(
        labels=[label_map.get(l, l) for l in counts.index],
        values=counts.values,
        hole=0.55,
        marker=dict(
            colors=["#58A6FF", "#BC8CFF"],
            line=dict(color="#0D1117", width=2),
        ),
        textinfo="label+percent",
        textfont=dict(size=11, color="#E6EDF3"),
        hovertemplate="%{label}: <b>%{value}건</b><extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font_color="#E6EDF3", showlegend=False,
        margin=dict(t=4, b=4, l=4, r=4), height=180,
    )
    return fig


# ── KPI Card Helper ───────────────────────────────────────────────────────────

def kpi(label: str, value, sub: str = "", cls: str = "kpi-total") -> str:
    sub_html = f'<div class="kpi-sub">{sub}</div>' if sub else ""
    return f"""
    <div class="kpi-card {cls}">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      {sub_html}
    </div>"""


# ── Detail Panel ──────────────────────────────────────────────────────────────

def render_detail(row: pd.Series):
    score  = int(row.get("risk_score", 3))
    badge  = (f'<span class="badge {BADGE_CLS.get(score,"b1")}">'
              f'{SCORE_LABEL.get(score,"?")} · Lv.{score}</span>')
    trig   = "Rule 탐지" if row.get("triggered_by") == "rule" else "랜덤 감사"
    voc    = str(row.get("voc_content","(원문 없음)")).replace("<","&lt;").replace(">","&gt;")
    reason = str(row.get("reason","(없음)")).replace("<","&lt;").replace(">","&gt;")

    st.markdown(f"""
    <div class="detail-panel">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:22px;flex-wrap:wrap;">
        <span style="font-size:19px;font-weight:700;color:#E6EDF3;">{row.get('voc_id','')}</span>
        {badge}
        <span style="color:#8B949E;font-size:12px;margin-left:auto">{row.get('processed_at','')}</span>
      </div>

      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-bottom:22px;">
        <div>
          <div class="dl">광고 유형</div>
          <div class="dv">{row.get('ad_type','—')}</div>
        </div>
        <div>
          <div class="dl">광고명</div>
          <div class="dv">{row.get('ad_name','—') or '—'}</div>
        </div>
        <div>
          <div class="dl">탐지 방식</div>
          <div class="dv">{trig}</div>
        </div>
        <div>
          <div class="dl">리스크 유형</div>
          <div class="dv">{TYPE_KO.get(str(row.get('risk_type','')),'—')}</div>
        </div>
        <div>
          <div class="dl">사용자 ID</div>
          <div class="dv">{row.get('user_id','—') or '—'}</div>
        </div>
        <div>
          <div class="dl">접수 일시</div>
          <div class="dv">{row.get('created_at','—') or '—'}</div>
        </div>
      </div>

      <div class="dl">📝 VoC 원문</div>
      <div class="voc-box">{voc}</div>

      <div class="dl">🤖 LLM 판단 근거</div>
      <div class="reason-box">{reason}</div>
    </div>
    """, unsafe_allow_html=True)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():

    # ── 헤더
    st.markdown(
        '<h1 style="color:#E6EDF3;font-size:24px;font-weight:700;margin-bottom:2px;">'
        '🛡️ VoC Risk Sentinel</h1>'
        '<p style="color:#6E7681;font-size:13px;margin:0 0 4px;">'
        '리워드 광고 플랫폼 · 실시간 리스크 우선순위 대시보드</p>',
        unsafe_allow_html=True,
    )
    st.markdown("<hr>", unsafe_allow_html=True)

    # ── 데이터 로드
    df_full, err = load_data()
    if err:
        st.error("데이터 로드 실패")
        st.markdown(err)
        st.stop()

    # ── 사이드바 필터 ──────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown(
            '<p style="color:#E6EDF3;font-size:15px;font-weight:700;">⚙️ 필터</p>',
            unsafe_allow_html=True,
        )

        st.markdown('<div class="sec">리스크 유형</div>', unsafe_allow_html=True)
        all_types = sorted(df_full["risk_type"].unique().tolist())
        sel_types = st.multiselect(
            "", all_types, default=all_types,
            format_func=lambda x: f"{TYPE_KO.get(x, x)}",
            label_visibility="collapsed",
            key="filter_types",
        )

        st.markdown('<div class="sec">Score 범위</div>', unsafe_allow_html=True)
        score_range = st.slider("", 1, 5, (1, 5), label_visibility="collapsed", key="filter_score")

        st.markdown('<div class="sec">광고 유형</div>', unsafe_allow_html=True)
        all_ad = sorted(df_full["ad_type"].dropna().unique().tolist())
        sel_ad = st.multiselect("", all_ad, default=all_ad, label_visibility="collapsed", key="filter_ad")

        st.markdown('<div class="sec">탐지 방식</div>', unsafe_allow_html=True)
        all_trig = sorted(df_full["triggered_by"].unique().tolist())
        sel_trig = st.multiselect(
            "", all_trig, default=all_trig,
            format_func=lambda x: "Rule 탐지" if x == "rule" else "랜덤 감사",
            label_visibility="collapsed",
            key="filter_trig",
        )

        st.markdown("<br>", unsafe_allow_html=True)
        col_r, col_ref = st.columns(2)
        with col_r:
            if st.button("초기화", use_container_width=True):
                st.session_state.pop("filter_types", None)
                st.session_state.pop("filter_score", None)
                st.session_state.pop("filter_ad", None)
                st.session_state.pop("filter_trig", None)
                st.cache_data.clear()
                st.rerun()
        with col_ref:
            if st.button("새로고침", use_container_width=True):
                st.cache_data.clear()
                st.rerun()

        st.markdown('<div class="sec" style="margin-top:20px">탐지 방식 분포</div>', unsafe_allow_html=True)
        st.plotly_chart(
            make_trigger_donut(df_full),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    # ── 필터 적용
    df = df_full.copy()
    if sel_types:
        df = df[df["risk_type"].isin(sel_types)]
    df = df[df["risk_score"].between(*score_range)]
    if sel_ad:
        df = df[df["ad_type"].isin(sel_ad)]
    if sel_trig:
        df = df[df["triggered_by"].isin(sel_trig)]
    df = df.reset_index(drop=True)

    # ── KPI 카드 ───────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    total    = len(df)
    critical = int((df["risk_score"] == 5).sum())
    abuse    = int((df["risk_type"] == "abuse").sum())
    avg_sc   = df["risk_score"].mean() if total > 0 else 0.0

    with c1:
        st.markdown(kpi("전체 분석 건수", f"{total:,}", "필터 적용 기준", "kpi-total"), unsafe_allow_html=True)
    with c2:
        sub2 = "⚠️ 즉시 대응 필요" if critical > 0 else "이상 없음"
        st.markdown(kpi("Critical (score 5)", f"{critical:,}", sub2, "kpi-critical"), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi("Grey Zone (어뷰징)", f"{abuse:,}", "어뷰징 의심 건수", "kpi-abuse"), unsafe_allow_html=True)
    with c4:
        avg_cls = "kpi-warn" if avg_sc >= 4 else ("kpi-abuse" if avg_sc >= 3 else "kpi-avg")
        st.markdown(kpi("평균 리스크 Score", f"{avg_sc:.2f}", f"Max: {df['risk_score'].max() if total else 0}", avg_cls), unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── 차트 ───────────────────────────────────────────────────────────────────
    col_d, col_b = st.columns([1.1, 1])
    with col_d:
        st.markdown('<div class="sec">리스크 유형 분포</div>', unsafe_allow_html=True)
        if not df.empty:
            st.plotly_chart(make_donut(df), use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("표시할 데이터가 없습니다.")

    with col_b:
        st.markdown('<div class="sec">Score 등급 분포</div>', unsafe_allow_html=True)
        if not df.empty:
            st.plotly_chart(make_score_bar(df), use_container_width=True, config={"displayModeBar": False})
        else:
            st.info("표시할 데이터가 없습니다.")

    # ── 우선순위 테이블 ────────────────────────────────────────────────────────
    st.markdown('<div class="sec">📋 우선순위 리스트 (Score 높은 순 · 행 클릭 시 상세 보기)</div>', unsafe_allow_html=True)

    COL_MAP = {
        "voc_id":       "VoC ID",
        "risk_score":   "Score",
        "risk_label":   "등급",
        "type_ko":      "리스크 유형",
        "reason":       "판단 근거",
        "ad_type":      "광고 유형",
        "triggered_by": "탐지 방식",
        "processed_at": "처리 시각",
    }
    show_cols   = [c for c in COL_MAP if c in df.columns]
    display_df  = df[show_cols].rename(columns=COL_MAP)
    if "탐지 방식" in display_df.columns:
        display_df["탐지 방식"] = display_df["탐지 방식"].map(
            {"rule": "Rule 탐지", "audit": "랜덤 감사"}
        ).fillna(display_df["탐지 방식"])

    col_config = {
        "Score":     st.column_config.NumberColumn("Score", format="%d ⭐", width="small"),
        "등급":      st.column_config.TextColumn("등급", width="small"),
        "판단 근거": st.column_config.TextColumn("판단 근거", width="large"),
        "처리 시각": st.column_config.TextColumn("처리 시각", width="medium"),
    }

    st.caption(f"총 {len(display_df):,}건 표시 | 행을 클릭하면 원문·판단 근거가 아래에 표시됩니다")

    event = st.dataframe(
        display_df,
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config=col_config,
        hide_index=True,
        height=420,
    )

    # ── 상세 보기 ──────────────────────────────────────────────────────────────
    if event.selection.rows:
        idx = event.selection.rows[0]
        row = df.iloc[idx]
        st.markdown('<div class="sec">🔍 상세 보기</div>', unsafe_allow_html=True)
        render_detail(row)
    else:
        st.markdown(
            '<p style="color:#6E7681;font-size:13px;text-align:center;padding:12px 0;">'
            '↑ 테이블에서 행을 클릭하면 VoC 원문과 판단 근거를 확인할 수 있습니다.</p>',
            unsafe_allow_html=True,
        )

    # ── 다운로드 ───────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    csv_bytes = df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        label="📥 필터 결과 CSV 다운로드",
        data=csv_bytes,
        file_name=f"voc_risk_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

    # ── 푸터
    st.markdown(
        f'<p style="color:#30363D;font-size:11px;text-align:center;margin-top:40px;">'
        f'VoC Risk Sentinel · {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
