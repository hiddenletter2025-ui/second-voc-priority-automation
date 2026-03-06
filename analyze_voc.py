"""
analyze_voc.py — 하이브리드 VoC 리스크 분석 파이프라인
=====================================================
Step 1: Rule-based Pre-Filtering  (키워드 + 로그 패턴)
Step 2: LLM Precision Scoring     (Gemini 2.0 Flash, 고위험 + 5% 감사)
Step 3: 결과 저장 + 검증 보고서 생성
"""

import csv
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv

# google-genai는 선택적 의존성 — 미설치 시 Rule-only 모드로 동작
try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# tqdm 선택적 — 미설치 시 간단한 fallback
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, desc="", **kwargs):
        total = len(iterable) if hasattr(iterable, "__len__") else "?"
        for i, item in enumerate(iterable, 1):
            print(f"\r  {desc} [{i}/{total}]", end="", flush=True)
            yield item
        print()

# ─── 경로 설정 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "voc_data_300.csv"
OUTPUT_DIR = BASE_DIR / "outputs"
RESULTS_FILE = OUTPUT_DIR / "voc_results.jsonl"
REPORT_FILE = OUTPUT_DIR / "evaluation_report.txt"

# ─── 환경 변수 ──────────────────────────────────────────────
load_dotenv(BASE_DIR / ".env")
API_KEY = os.getenv("GEMINI_API_KEY")

# ─── Gemini 클라이언트 초기화 ────────────────────────────────
LLM_AVAILABLE = False
client = None
MODEL_ID = "gemini-2.5-flash"

if HAS_GENAI and API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
        LLM_AVAILABLE = True
        print("✅ Gemini API 연결 완료")
    except Exception as e:
        print(f"⚠ Gemini 초기화 실패 ({e}) — Rule-only 모드로 실행합니다.")
else:
    if not HAS_GENAI:
        print("⚠ google-genai 미설치 — Rule-only 모드로 실행합니다.")
    elif not API_KEY:
        print("⚠ GEMINI_API_KEY 미설정 — Rule-only 모드로 실행합니다.")
        print("  → .env 파일에 GEMINI_API_KEY=your_key 를 설정하세요.")

# ─── Rule-based 키워드 사전 ──────────────────────────────────
CRITICAL_KEYWORDS = [
    "금감원", "고소", "법적 조치", "법적 대응", "소송", "변호사",
    "위법", "고소장", "법적 절차",
]
HIGH_KEYWORDS = [
    "소비자원", "소비자보호원", "민원", "신고",
    "커뮤니티에 다 올", "커뮤니티에 올리",
]
PROFANITY_KEYWORDS = [
    "ㅅㅂ", "ㅆㅂ", "씨발", "개같", "개짜증", "미친",
    "존나", "병신", "지랄",
]
MEDIUM_KEYWORDS = [
    "화면이 하얗", "백화", "무한 로딩", "클릭 불가",
    "앱이 꺼", "시스템 문제", "트래킹", "단계부터",
    "앱이 자꾸 튕",
]


# ═══════════════════════════════════════════════════════════════
#  Step 1: Rule-based Pre-Filtering
# ═══════════════════════════════════════════════════════════════

def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(kw in text for kw in keywords)


def rule_based_classify(row: dict) -> dict:
    """
    규칙 기반 1차 분류. 반환값에 'rule_flag' 포함.
    - 'critical' / 'high' / 'medium' / 'grey_suspect' / 'low'
    """
    content = row["voc_content"]
    log_match = row["log_matching"]
    daily_cnt = int(row["daily_query_cnt"])

    # Grey Zone 패턴: 로그 없음 + 문의 빈도 ≥ 10
    if log_match == "No_Record" and daily_cnt >= 10:
        return {**row, "rule_flag": "grey_suspect"}

    if _contains_any(content, CRITICAL_KEYWORDS):
        return {**row, "rule_flag": "critical"}

    if _contains_any(content, HIGH_KEYWORDS):
        return {**row, "rule_flag": "high"}

    if _contains_any(content, PROFANITY_KEYWORDS):
        return {**row, "rule_flag": "high"}

    if _contains_any(content, MEDIUM_KEYWORDS):
        return {**row, "rule_flag": "medium"}

    return {**row, "rule_flag": "low"}


def step1_filter(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """고위험 후보 + 나머지를 분리하여 반환."""
    high_risk = []
    rest = []

    for row in rows:
        classified = rule_based_classify(row)
        if classified["rule_flag"] in ("critical", "high", "grey_suspect"):
            high_risk.append(classified)
        else:
            rest.append(classified)

    return high_risk, rest


# ═══════════════════════════════════════════════════════════════
#  Step 2: LLM Precision Scoring (Gemini 2.0 Flash)
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """리워드 광고 플랫폼 VoC 리스크 분류기.

## 등급 기준
- Critical(81-100): 법적 대응 언급(금감원/고소/소송), 서비스 전체 마비, 심각한 금전 손실
- High(61-80): 외부 기관 신고 언급(소비자원/민원), 심한 욕설, 대형 파트너사 반복 결함
- Medium(41-60): 시스템 오류(백화/무한로딩/클릭불가), 트래킹 누락, 기술 확인 필요
- Low(0-40): 단순 리워드 미지급, FAQ 해결 가능 문의
- Grey(판단유보): log_matching=No_Record + daily_query_cnt≥10 (어뷰징 의심), 증빙 조작 의심, 동일 패턴 복수 계정

## 판단 시 참조
- log_matching: Match(정상) / No_Record(로그 없음)
- daily_query_cnt: 해당 유저의 일 문의 횟수 (10 이상이면 어뷰징 의심)
- 욕설 단독으로는 High 이하. 법적 키워드 동반 시 Critical.

반드시 JSON으로만 응답."""

RESPONSE_SCHEMA = None
if HAS_GENAI:
    RESPONSE_SCHEMA = types.Schema(
        type="OBJECT",
        properties={
            "risk_level": types.Schema(
                type="STRING",
                enum=["Critical", "High", "Medium", "Low", "Grey"],
            ),
            "risk_score": types.Schema(type="INTEGER"),
            "is_grey_zone": types.Schema(type="BOOLEAN"),
            "reasoning": types.Schema(type="STRING"),
        },
        required=["risk_level", "risk_score", "is_grey_zone", "reasoning"],
    )


def build_user_prompt(row: dict) -> str:
    return (
        f"[VoC 분석 요청]\n"
        f"voc_content: {row['voc_content']}\n"
        f"ad_type: {row['ad_type']}\n"
        f"ad_name: {row['ad_name']}\n"
        f"category: {row['category']}\n"
        f"log_matching: {row['log_matching']}\n"
        f"daily_query_cnt: {row['daily_query_cnt']}"
    )


def rule_fallback_score(row: dict) -> dict:
    """LLM 미사용 시 Rule 기반 상세 스코어링 (폴백)."""
    content = row["voc_content"]
    log_match = row["log_matching"]
    daily_cnt = int(row["daily_query_cnt"])
    flag = row.get("rule_flag", "low")

    if flag == "critical" or _contains_any(content, CRITICAL_KEYWORDS):
        return {"risk_level": "Critical", "risk_score": 90, "is_grey_zone": False,
                "reasoning": "법적 대응 관련 키워드 탐지 (Rule-based)"}
    if flag == "high" or _contains_any(content, HIGH_KEYWORDS + PROFANITY_KEYWORDS):
        score = 70
        if _contains_any(content, PROFANITY_KEYWORDS):
            score = 75
        return {"risk_level": "High", "risk_score": score, "is_grey_zone": False,
                "reasoning": "외부 신고 위협 또는 욕설 탐지 (Rule-based)"}
    if flag == "grey_suspect" or (log_match == "No_Record" and daily_cnt >= 10):
        return {"risk_level": "Grey", "risk_score": 55, "is_grey_zone": True,
                "reasoning": f"어뷰징 의심 — 로그 미일치 + 일 문의 {daily_cnt}회 (Rule-based)"}
    if flag == "medium" or _contains_any(content, MEDIUM_KEYWORDS):
        return {"risk_level": "Medium", "risk_score": 50, "is_grey_zone": False,
                "reasoning": "시스템 오류/기술적 확인 필요 (Rule-based)"}
    return {"risk_level": "Low", "risk_score": 20, "is_grey_zone": False,
            "reasoning": "단순 문의 — Rule-based 자동 분류"}


def call_gemini(row: dict, max_retries: int = 3) -> dict:
    """Gemini 2.0 Flash 호출 (v1beta + response_schema + thinking_budget=0).
    LLM 미사용 환경에서는 rule_fallback_score로 대체."""
    if not LLM_AVAILABLE:
        return rule_fallback_score(row)

    user_prompt = build_user_prompt(row)

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                    temperature=0.1,
                ),
            )

            result = json.loads(response.text)
            return {
                "risk_level": result.get("risk_level", "Low"),
                "risk_score": result.get("risk_score", 0),
                "is_grey_zone": result.get("is_grey_zone", False),
                "reasoning": result.get("reasoning", ""),
            }

        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"   ⚠ API 오류 (attempt {attempt+1}): {e} — {wait}초 후 재시도")
                time.sleep(wait)
            else:
                print(f"   ❌ API 최종 실패 — Rule-based 폴백 적용: {e}")
                return rule_fallback_score(row)


def step2_llm_analysis(
    high_risk: list[dict],
    rest: list[dict],
    audit_rate: float = 0.05,
) -> list[dict]:
    """
    고위험 후보 전량 + 나머지의 5%를 LLM으로 분석.
    나머지는 rule_flag 기반 기본값 부여.
    """
    # 5% 랜덤 감사 샘플
    audit_count = max(1, int(len(rest) * audit_rate))
    audit_sample = random.sample(rest, min(audit_count, len(rest)))
    audit_ids = {r["voc_id"] for r in audit_sample}

    llm_targets = high_risk + audit_sample
    print(f"\n🔍 LLM 분석 대상: {len(llm_targets)}건 "
          f"(고위험 {len(high_risk)} + 감사 {len(audit_sample)})")

    results = []

    # LLM 분석 대상
    for row in tqdm(llm_targets, desc="🤖 Gemini 분석 중"):
        llm_result = call_gemini(row)
        results.append({
            "voc_id": row["voc_id"],
            "created_at": row["created_at"],
            "user_id": row["user_id"],
            "publisher": row.get("publisher", ""),
            "ad_type": row["ad_type"],
            "ad_name": row["ad_name"],
            "category": row["category"],
            "voc_content": row["voc_content"],
            "log_matching": row["log_matching"],
            "daily_query_cnt": int(row["daily_query_cnt"]),
            "actual_risk_level": row["actual_risk_level"],
            "rule_flag": row["rule_flag"],
            "analyzed_by": "LLM",
            **llm_result,
        })
        time.sleep(0.3)  # Rate limit 방어

    # 나머지 (Rule-only)
    rule_level_map = {"low": "Low", "medium": "Medium"}
    rule_score_map = {"low": 20, "medium": 50}

    for row in rest:
        if row["voc_id"] in audit_ids:
            continue  # 이미 LLM 분석됨
        flag = row["rule_flag"]
        results.append({
            "voc_id": row["voc_id"],
            "created_at": row["created_at"],
            "user_id": row["user_id"],
            "publisher": row.get("publisher", ""),
            "ad_type": row["ad_type"],
            "ad_name": row["ad_name"],
            "category": row["category"],
            "voc_content": row["voc_content"],
            "log_matching": row["log_matching"],
            "daily_query_cnt": int(row["daily_query_cnt"]),
            "actual_risk_level": row["actual_risk_level"],
            "rule_flag": flag,
            "analyzed_by": "Rule",
            "risk_level": rule_level_map.get(flag, "Low"),
            "risk_score": rule_score_map.get(flag, 20),
            "is_grey_zone": False,
            "reasoning": "Rule-based 자동 분류",
        })

    return results


# ═══════════════════════════════════════════════════════════════
#  Step 3: 결과 저장 + 검증 보고서
# ═══════════════════════════════════════════════════════════════

def save_results(results: list[dict]):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n✅ 결과 저장 완료: {RESULTS_FILE} ({len(results)}건)")


def generate_report(results: list[dict]):
    """검증 보고서 생성."""
    total = len(results)
    correct = sum(1 for r in results if r["actual_risk_level"] == r["risk_level"])
    accuracy = correct / total * 100 if total else 0

    # 등급별 통계
    level_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})
    mismatches: list[dict] = []

    for r in results:
        actual = r["actual_risk_level"]
        predicted = r["risk_level"]
        level_stats[actual]["total"] += 1
        if actual == predicted:
            level_stats[actual]["correct"] += 1
        else:
            mismatches.append(r)

    # 보고서 작성
    lines = [
        "=" * 70,
        "  VoC 리스크 자동 분류 — 검증 보고서 (Evaluation Report)",
        "=" * 70,
        "",
        f"분석 일시     : {time.strftime('%Y-%m-%d %H:%M')}",
        f"총 분석 건수  : {total}건",
        f"LLM 분석 건수 : {sum(1 for r in results if r['analyzed_by'] == 'LLM')}건",
        f"Rule 분류 건수: {sum(1 for r in results if r['analyzed_by'] == 'Rule')}건",
        "",
        "-" * 70,
        "1. 전체 정확도 (Total Accuracy)",
        "-" * 70,
        f"   정확도: {accuracy:.1f}%  ({correct}/{total}건 일치)",
        "",
        "-" * 70,
        "2. 등급별 일치율 (Per-Level Accuracy)",
        "-" * 70,
        f"   {'등급':<12s} {'건수':>6s} {'일치':>6s} {'일치율':>8s}",
        f"   {'─'*12} {'─'*6} {'─'*6} {'─'*8}",
    ]

    for level in ["Critical", "High", "Medium", "Low", "Grey"]:
        s = level_stats.get(level, {"total": 0, "correct": 0})
        t, c = s["total"], s["correct"]
        rate = f"{c/t*100:.1f}%" if t > 0 else "N/A"
        lines.append(f"   {level:<12s} {t:>6d} {c:>6d} {rate:>8s}")

    lines += [
        "",
        "-" * 70,
        "3. 오답 사례 (Mismatched Cases) — 최대 5건",
        "-" * 70,
    ]

    sample_mismatches = mismatches[:5] if len(mismatches) <= 5 else random.sample(mismatches, 5)
    for i, m in enumerate(sample_mismatches, 1):
        content_preview = m["voc_content"][:80] + ("..." if len(m["voc_content"]) > 80 else "")
        lines += [
            f"  [{i}] voc_id     : {m['voc_id']}",
            f"      원문       : {content_preview}",
            f"      실제 등급  : {m['actual_risk_level']}",
            f"      LLM 등급   : {m['risk_level']}",
            f"      LLM 사유   : {m['reasoning']}",
            f"      분석 방식  : {m['analyzed_by']}",
            "",
        ]

    if not sample_mismatches:
        lines.append("  (오답 사례 없음)")

    # 혼동 행렬 요약
    lines += [
        "-" * 70,
        "4. 혼동 행렬 요약 (Confusion Summary)",
        "-" * 70,
    ]
    confusion: dict[str, Counter] = defaultdict(Counter)
    for r in results:
        confusion[r["actual_risk_level"]][r["risk_level"]] += 1

    all_levels = ["Critical", "High", "Medium", "Low", "Grey"]
    label = "실제\\예측"
    header = f"   {label:<10s}" + "".join(f"{l:>10s}" for l in all_levels)
    lines.append(header)
    lines.append(f"   {'─'*10}" + "─" * 50)
    for actual in all_levels:
        row_str = f"   {actual:<10s}"
        for pred in all_levels:
            row_str += f"{confusion[actual][pred]:>10d}"
        lines.append(row_str)

    lines += ["", "=" * 70, "  End of Report", "=" * 70]

    report_text = "\n".join(lines)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"✅ 검증 보고서 저장 완료: {REPORT_FILE}")
    print(f"\n{report_text}")


# ─── 메인 ───────────────────────────────────────────────────

def main():
    random.seed(42)

    # CSV 로드
    if not DATA_FILE.exists():
        sys.exit(f"❌ 데이터 파일 없음: {DATA_FILE}\n   먼저 gen_data.py를 실행하세요.")

    with open(DATA_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"📂 데이터 로드 완료: {len(rows)}건")

    # Step 1
    print("\n" + "=" * 50)
    print("Step 1: Rule-based Pre-Filtering")
    print("=" * 50)
    high_risk, rest = step1_filter(rows)
    print(f"   고위험 후보: {len(high_risk)}건")
    print(f"   나머지     : {len(rest)}건")

    flag_counts = Counter(r["rule_flag"] for r in high_risk)
    for flag, cnt in flag_counts.most_common():
        print(f"     - {flag}: {cnt}건")

    # Step 2
    print("\n" + "=" * 50)
    print("Step 2: LLM Precision Scoring (Gemini 2.0 Flash)")
    print("=" * 50)
    results = step2_llm_analysis(high_risk, rest)

    # Step 3
    print("\n" + "=" * 50)
    print("Step 3: 결과 저장 + 검증 보고서 생성")
    print("=" * 50)
    save_results(results)
    generate_report(results)


if __name__ == "__main__":
    main()
