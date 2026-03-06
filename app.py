"""
app.py — VoC Risk Sentinel Dashboard
=====================================
Streamlit 기반 실시간 VoC 리스크 모니터링 대시보드
실행: streamlit run app.py
"""

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ─── 페이지 설정 ────────────────────────────────────────────
st.set_page_config(
    page_title="VoC Risk Sentinel",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── 경로 설정 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
RESULTS_FILE = BASE_DIR / "outputs" / "voc_results.jsonl"
REPORT_FILE = BASE_DIR / "outputs" / "evaluation_report.txt"

# ─── 색상 팔레트 ────────────────────────────────────────────
RISK_COLORS = {
    "Critical": "#DC2626",
    "High": "#F97316",
    "Medium": "#EAB308",
    "Low": "#22C55E",
    "Grey": "#6B7280",
}
RISK_ORDER = ["Critical", "High", "Medium", "Low", "Grey"]


# ─── 데이터 로드 ────────────────────────────────────────────
@st.cache_data
def load_data() -> pd.DataFrame:
    if not RESULTS_FILE.exists():
        return pd.DataFrame()
    records = []
    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    df = pd.DataFrame(records)
    if "created_at" in df.columns:
        df["created_at"] = pd.to_datetime(df["created_at"])
        df["date"] = df["created_at"].dt.date
    return df


def load_report() -> str:
    if REPORT_FILE.exists():
        return REPORT_FILE.read_text(encoding="utf-8")
    return ""


# ─── 메인 ───────────────────────────────────────────────────
def main():
    df = load_data()

    if df.empty:
        st.error("⚠️ 분석 결과 파일이 없습니다. 먼저 `python analyze_voc.py`를 실행하세요.")
        st.stop()

    # ─── 사이드바 필터 ──────────────────────────────────────
    st.sidebar.title("🛡️ VoC Risk Sentinel")
    st.sidebar.markdown("---")

    # 리스크 등급 필터
    selected_levels = st.sidebar.multiselect(
        "리스크 등급",
        options=RISK_ORDER,
        default=RISK_ORDER,
    )

    # 분석 방식 필터
    analysis_types = df["analyzed_by"].unique().tolist()
    selected_analysis = st.sidebar.multiselect(
        "분석 방식",
        options=analysis_types,
        default=analysis_types,
    )

    # 카테고리 필터
    if "category" in df.columns:
        categories = sorted(df["category"].unique().tolist())
        selected_categories = st.sidebar.multiselect(
            "카테고리",
            options=categories,
            default=categories,
        )
    else:
        selected_categories = []

    # 광고 유형 필터
    if "ad_type" in df.columns:
        ad_types = sorted(df["ad_type"].unique().tolist())
        selected_ad_types = st.sidebar.multiselect(
            "광고 유형",
            options=ad_types,
            default=ad_types,
        )
    else:
        selected_ad_types = []

    # 필터 적용
    mask = df["risk_level"].isin(selected_levels) & df["analyzed_by"].isin(selected_analysis)
    if selected_categories:
        mask &= df["category"].isin(selected_categories)
    if selected_ad_types:
        mask &= df["ad_type"].isin(selected_ad_types)
    filtered = df[mask]

    # ─── 헤더 ───────────────────────────────────────────────
    st.title("🛡️ VoC Risk Sentinel Dashboard")
    st.caption("리워드 광고 플랫폼 VoC 리스크 자동 분류 모니터링")
    st.markdown("---")

    # ─── KPI 카드 ───────────────────────────────────────────
    total = len(filtered)
    critical_cnt = len(filtered[filtered["risk_level"] == "Critical"])
    high_cnt = len(filtered[filtered["risk_level"] == "High"])
    grey_cnt = len(filtered[filtered["risk_level"] == "Grey"])
    llm_cnt = len(filtered[filtered["analyzed_by"] == "LLM"])

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("전체 건수", f"{total}건")
    col2.metric("🔴 Critical", f"{critical_cnt}건")
    col3.metric("🟠 High", f"{high_cnt}건")
    col4.metric("⚫ Grey Zone", f"{grey_cnt}건")
    col5.metric("🤖 LLM 분석", f"{llm_cnt}건")

    st.markdown("---")

    # ─── Row 1: 등급 분포 + 카테고리 분포 ────────────────────
    r1_col1, r1_col2 = st.columns(2)

    with r1_col1:
        st.subheader("리스크 등급 분포")
        level_counts = (
            filtered["risk_level"]
            .value_counts()
            .reindex(RISK_ORDER, fill_value=0)
            .reset_index()
        )
        level_counts.columns = ["등급", "건수"]
        fig_level = px.bar(
            level_counts,
            x="등급",
            y="건수",
            color="등급",
            color_discrete_map=RISK_COLORS,
            text="건수",
        )
        fig_level.update_layout(
            showlegend=False,
            xaxis_title="",
            yaxis_title="건수",
            height=400,
        )
        fig_level.update_traces(textposition="outside")
        st.plotly_chart(fig_level, use_container_width=True)

    with r1_col2:
        st.subheader("카테고리별 분포")
        if "category" in filtered.columns:
            cat_counts = filtered["category"].value_counts().reset_index()
            cat_counts.columns = ["카테고리", "건수"]
            fig_cat = px.pie(
                cat_counts,
                values="건수",
                names="카테고리",
                color_discrete_sequence=px.colors.qualitative.Set2,
                hole=0.4,
            )
            fig_cat.update_layout(height=400)
            st.plotly_chart(fig_cat, use_container_width=True)

    # ─── Row 2: 일별 추이 + 광고 유형별 분포 ─────────────────
    r2_col1, r2_col2 = st.columns(2)

    with r2_col1:
        st.subheader("일별 VoC 리스크 추이")
        if "date" in filtered.columns:
            daily = (
                filtered.groupby(["date", "risk_level"])
                .size()
                .reset_index(name="건수")
            )
            fig_daily = px.area(
                daily,
                x="date",
                y="건수",
                color="risk_level",
                color_discrete_map=RISK_COLORS,
                category_orders={"risk_level": RISK_ORDER},
            )
            fig_daily.update_layout(
                xaxis_title="날짜",
                yaxis_title="건수",
                legend_title="등급",
                height=400,
            )
            st.plotly_chart(fig_daily, use_container_width=True)

    with r2_col2:
        st.subheader("광고 유형별 리스크")
        if "ad_type" in filtered.columns:
            ad_risk = (
                filtered.groupby(["ad_type", "risk_level"])
                .size()
                .reset_index(name="건수")
            )
            fig_ad = px.bar(
                ad_risk,
                x="ad_type",
                y="건수",
                color="risk_level",
                color_discrete_map=RISK_COLORS,
                category_orders={"risk_level": RISK_ORDER},
                barmode="stack",
            )
            fig_ad.update_layout(
                xaxis_title="광고 유형",
                yaxis_title="건수",
                legend_title="등급",
                height=400,
            )
            st.plotly_chart(fig_ad, use_container_width=True)

    # ─── Row 3: 매체사별 문의 + 리스크 점수 분포 ──────────────
    r3_col1, r3_col2 = st.columns(2)

    with r3_col1:
        st.subheader("매체사별 문의 현황")
        if "publisher" in filtered.columns:
            pub_risk = (
                filtered.groupby(["publisher", "risk_level"])
                .size()
                .reset_index(name="건수")
            )
            fig_pub = px.bar(
                pub_risk,
                x="publisher",
                y="건수",
                color="risk_level",
                color_discrete_map=RISK_COLORS,
                category_orders={"risk_level": RISK_ORDER},
                barmode="stack",
            )
            fig_pub.update_layout(
                xaxis_title="매체사",
                yaxis_title="건수",
                legend_title="등급",
                height=400,
            )
            st.plotly_chart(fig_pub, use_container_width=True)

    with r3_col2:
        st.subheader("리스크 점수 분포")
        if "risk_score" in filtered.columns:
            fig_hist = px.histogram(
                filtered,
                x="risk_score",
                color="risk_level",
                color_discrete_map=RISK_COLORS,
                category_orders={"risk_level": RISK_ORDER},
                nbins=20,
                barmode="overlay",
                opacity=0.7,
            )
            fig_hist.update_layout(
                xaxis_title="Risk Score",
                yaxis_title="건수",
                legend_title="등급",
                height=400,
            )
            st.plotly_chart(fig_hist, use_container_width=True)

    st.markdown("---")

    # ─── Row 4: 정확도 매트릭스 (실제 vs 예측) ───────────────
    st.subheader("📊 실제 등급 vs 예측 등급 (혼동 행렬)")

    if "actual_risk_level" in filtered.columns:
        confusion = pd.crosstab(
            filtered["actual_risk_level"],
            filtered["risk_level"],
            rownames=["실제 등급"],
            colnames=["예측 등급"],
        )
        confusion = confusion.reindex(index=RISK_ORDER, columns=RISK_ORDER, fill_value=0)

        fig_conf = go.Figure(
            data=go.Heatmap(
                z=confusion.values,
                x=RISK_ORDER,
                y=RISK_ORDER,
                colorscale="RdYlGn_r",
                text=confusion.values,
                texttemplate="%{text}",
                textfont={"size": 16},
                hovertemplate="실제: %{y}<br>예측: %{x}<br>건수: %{z}<extra></extra>",
            )
        )
        fig_conf.update_layout(
            xaxis_title="예측 등급",
            yaxis_title="실제 등급",
            height=450,
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig_conf, use_container_width=True)

        # 정확도 요약
        correct = (filtered["actual_risk_level"] == filtered["risk_level"]).sum()
        total_f = len(filtered)
        accuracy = correct / total_f * 100 if total_f > 0 else 0

        acc_col1, acc_col2, acc_col3 = st.columns(3)
        acc_col1.metric("전체 정확도", f"{accuracy:.1f}%")
        acc_col2.metric("일치 건수", f"{correct}건")
        acc_col3.metric("불일치 건수", f"{total_f - correct}건")

    st.markdown("---")

    # ─── Row 5: 고위험 VoC 상세 테이블 ──────────────────────
    st.subheader("🚨 고위험 VoC 상세 목록")

    high_risk_df = filtered[filtered["risk_level"].isin(["Critical", "High", "Grey"])].copy()

    if not high_risk_df.empty:
        display_cols = [
            "voc_id", "created_at", "risk_level", "risk_score",
            "category", "ad_type", "publisher",
            "voc_content", "reasoning", "analyzed_by",
        ]
        existing_cols = [c for c in display_cols if c in high_risk_df.columns]
        high_risk_display = high_risk_df[existing_cols].sort_values(
            "risk_score", ascending=False
        )

        st.dataframe(
            high_risk_display,
            use_container_width=True,
            height=400,
            column_config={
                "voc_id": st.column_config.TextColumn("VoC ID", width="small"),
                "created_at": st.column_config.DatetimeColumn("일시", format="MM/DD HH:mm"),
                "risk_level": st.column_config.TextColumn("등급", width="small"),
                "risk_score": st.column_config.ProgressColumn(
                    "점수", min_value=0, max_value=100, format="%d"
                ),
                "category": st.column_config.TextColumn("카테고리"),
                "ad_type": st.column_config.TextColumn("광고유형", width="small"),
                "publisher": st.column_config.TextColumn("매체사"),
                "voc_content": st.column_config.TextColumn("VoC 원문", width="large"),
                "reasoning": st.column_config.TextColumn("판단 사유", width="large"),
                "analyzed_by": st.column_config.TextColumn("분석방식", width="small"),
            },
        )
    else:
        st.info("필터 조건에 해당하는 고위험 VoC가 없습니다.")

    st.markdown("---")

    # ─── Row 6: 검증 보고서 ─────────────────────────────────
    st.subheader("📋 검증 보고서")
    report_text = load_report()
    if report_text:
        with st.expander("검증 보고서 전문 보기", expanded=False):
            st.code(report_text, language="text")
    else:
        st.info("검증 보고서 파일이 없습니다.")

    # ─── 푸터 ───────────────────────────────────────────────
    st.markdown("---")
    st.caption(
        "VoC Risk Sentinel — 하이브리드 파이프라인 (Rule-based + Gemini 2.5 Flash)  |  "
        "포트폴리오 프로젝트 (합성 데이터 사용)"
    )


if __name__ == "__main__":
    main()
