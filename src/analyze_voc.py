"""
VoC Risk Auto-Classification Pipeline v2
Hybrid: Rule-based Filter → LLM Precision Scoring

[버그 수정 v1→v2]
  1. api_version 'v1' → 'v1beta': v1은 systemInstruction/responseMimeType 미지원 (모든 호출 400 실패 원인)
  2. 컬럼명 수정: content→voc_content, log_status→log_matching, repeat_count→daily_query_cnt
  3. 로그 판단값 수정: '없음' → 'No_Record'
  4. 실패 건은 체크포인트 미기록 (재실행 시 자동 재시도)
  5. 결과 없는데 체크포인트만 있으면 자동 초기화

[2026 최적화]
  - gemini-2.5-flash 업그레이드
  - thinking_budget=0: 사고 토큰 완전 차단 (Flash 특화 토큰 절감)
  - response_schema: JSON 구조 강제 → 시스템 프롬프트 포맷 설명 불필요
  - 시스템 프롬프트: ~30 tokens로 압축
"""

import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional

import pandas as pd
from tqdm import tqdm
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

MODEL_ID       = "gemini-2.5-flash"
CHECKPOINT_DIR = Path("checkpoints")
OUTPUT_PATH    = Path("voc_results.jsonl")
MAX_RETRIES    = 3
RETRY_DELAY    = 5        # seconds (지수 백오프 base)
RANDOM_AUDIT   = 0.05    # 미탐율 방어: 필터 통과 건 5% 랜덤 LLM 감사

# FIX: v1 → v1beta (systemInstruction, responseMimeType, ThinkingConfig 지원)
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version="v1beta"),
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("pipeline.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ── Data Model ────────────────────────────────────────────────────────────────

@dataclass
class RiskResult:
    voc_id: str
    risk_score: int       # 1~5 (5=즉시대응)
    risk_type: str        # legal | system | abuse | normal
    reason: str           # 15자 이내 한 문장
    triggered_by: str     # rule | audit
    processed_at: str


# ── LLM Schema & Config (재사용 객체) ─────────────────────────────────────────

# response_schema: JSON 구조를 API 레벨에서 강제
# → 시스템 프롬프트에 출력 포맷 설명할 필요 없음 → 토큰 절감
RISK_SCHEMA = {
    "type": "object",
    "properties": {
        "score":  {"type": "integer"},
        "type":   {"type": "string", "enum": ["legal", "system", "abuse", "normal"]},
        "reason": {"type": "string"},
    },
    "required": ["score", "type", "reason"],
}

# 극한 압축 시스템 프롬프트 (~30 tokens)
# 포맷 설명 제거 (response_schema가 대체), 판단 기준만 최소 서술
SYSTEM_PROMPT = (
    "리워드광고 VoC 리스크 분류기."
    " score:1~5(5=법적·즉시대응,1=단순문의)."
    " reason:15자이내 한국어."
)

LLM_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    temperature=0.0,           # 결정론적 출력
    max_output_tokens=80,      # JSON 4필드면 충분
    response_mime_type="application/json",
    response_schema=RISK_SCHEMA,
    thinking_config=types.ThinkingConfig(thinking_budget=0),  # 사고 토큰 차단
)


# ── Step 1: Rule-based Filter ─────────────────────────────────────────────────

def normalize(text: str) -> str:
    """공백·대소문자 제거 (키워드 우회 방어)"""
    import re, unicodedata
    text = unicodedata.normalize("NFC", str(text))
    return re.sub(r"[\s·\.]+", "", text.lower())  # 공백·점·중점 제거

LEGAL_KW  = {"금감원","고소","사기","소송","법적조치","변호사","민원","공정위","경찰","신고","형사"}
SYSTEM_KW = {"오류","버그","앱크래시","미지급","포인트안됨","결제오류","백화현상","클릭불가","팅김"}
ABUSE_KW  = {"다계정","대리","매크로","어뷰징","허위","조작","타인명의","환급","중복참여"}


def classify_rule(row) -> Optional[str]:
    # FIX: content → voc_content
    text = normalize(row.get("voc_content", ""))
    # FIX: log_status → log_matching, 값 비교 '없음' → 'No_Record'
    no_log = str(row.get("log_matching", "")).strip() == "No_Record"
    # FIX: repeat_count → daily_query_cnt
    cnt    = int(row.get("daily_query_cnt", 0))

    if any(k in text for k in LEGAL_KW):
        return "legal"
    if any(k in text for k in ABUSE_KW):
        return "abuse"
    if any(k in text for k in SYSTEM_KW) or (no_log and cnt >= 3):
        return "system"
    return None


def rule_filter(df: pd.DataFrame) -> pd.DataFrame:
    """Rule 기반 고위험 후보 추출 + 랜덤 감사 샘플 추가 (미탐율 방어)"""
    df = df.copy()
    df["_rule_type"] = df.apply(classify_rule, axis=1)

    high_risk = df[df["_rule_type"].notna()].copy()
    high_risk["triggered_by"] = "rule"

    rest    = df[df["_rule_type"].isna()]
    audit_n = max(1, int(len(rest) * RANDOM_AUDIT))
    audit   = rest.sample(n=audit_n, random_state=42).copy()
    audit["_rule_type"]   = "unknown"
    audit["triggered_by"] = "audit"

    candidates = pd.concat([high_risk, audit]).reset_index(drop=True)
    log.info(
        f"Rule filter: {len(high_risk)}건 고위험 "
        f"+ {len(audit)}건 감사 = {len(candidates)}건 LLM 대상"
    )
    return candidates


# ── Step 2: LLM Analysis ──────────────────────────────────────────────────────

def build_user_message(row: pd.Series) -> str:
    """입력 토큰 최소화: 300자 컷 + JSON 인라인"""
    text = str(row.get("voc_content", ""))[:300].replace('"', "'").replace("\n", " ")
    return (
        f'{{"id":"{row.get("voc_id","")}","text":"{text}",'
        f'"log":"{str(row.get("log_matching",""))[:20]}",'
        f'"cnt":{int(row.get("daily_query_cnt", 0))}}}'
    )


def call_llm(row: pd.Series) -> Optional[dict]:
    """단일 VoC LLM 호출 (재시도 + 지수 백오프)"""
    user_msg = build_user_message(row)
    vid = row.get("voc_id", "?")

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.models.generate_content(
                model=MODEL_ID,
                contents=user_msg,
                config=LLM_CONFIG,
            )
            return json.loads(resp.text)

        except json.JSONDecodeError as e:
            log.warning(f"[{vid}] JSON 파싱 실패 (시도 {attempt+1}): {e}")

        except Exception as e:
            log.warning(f"[{vid}] API 오류 (시도 {attempt+1}): {e}")
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (2 ** attempt)
                log.info(f"[{vid}] {wait}초 후 재시도...")
                time.sleep(wait)

    log.error(f"[{vid}] 최대 재시도 초과 → fallback (수동 검토 큐)")
    return None


# ── Checkpoint 관리 ───────────────────────────────────────────────────────────

def load_done_ids() -> set:
    """성공적으로 처리된 voc_id 집합 반환"""
    CHECKPOINT_DIR.mkdir(exist_ok=True)
    done = {f.stem for f in CHECKPOINT_DIR.glob("*.done")}
    if done:
        log.info(f"Checkpoint: {len(done)}건 이미 처리됨 → 스킵")
    return done


def mark_done(voc_id: str):
    """성공 건만 체크포인트 기록 (실패 건은 재실행 시 재시도)"""
    (CHECKPOINT_DIR / f"{voc_id}.done").touch()


def reset_checkpoints():
    """체크포인트 전체 초기화"""
    for f in CHECKPOINT_DIR.glob("*.done"):
        f.unlink()
    log.info("체크포인트 초기화 완료")


def save_result(result: RiskResult):
    with OUTPUT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


# ── Main Pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(input_csv: str, reset: bool = False):
    log.info("=" * 60)
    log.info(f"VoC Risk Pipeline 시작: {datetime.now().isoformat()}")
    log.info(f"모델: {MODEL_ID} | 감사율: {RANDOM_AUDIT*100:.0f}%")

    # 결과 파일 없는데 체크포인트만 남은 경우 자동 초기화 (이전 실패 런 방어)
    if not reset and not OUTPUT_PATH.exists() and any(CHECKPOINT_DIR.glob("*.done")):
        log.warning("결과 파일 없는데 체크포인트 발견 → 자동 초기화 (이전 런 실패 추정)")
        reset = True

    if reset:
        reset_checkpoints()
        if OUTPUT_PATH.exists():
            OUTPUT_PATH.unlink()
            log.info("기존 결과 파일 삭제")

    # 1. 데이터 로드
    df = pd.read_csv(input_csv, encoding="utf-8-sig")
    log.info(f"전체 VoC: {len(df)}건")

    # 필수 컬럼 보정 (없으면 기본값)
    defaults = {"voc_id": "", "voc_content": "", "log_matching": "", "daily_query_cnt": 0}
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val
            log.warning(f"컬럼 '{col}' 없음 → 기본값 '{val}' 사용")

    # 2. Rule 필터링
    candidates = rule_filter(df)

    # 3. 체크포인트 로드
    done_ids = load_done_ids()

    # 4. LLM 분석 루프
    skipped = failed = 0
    for _, row in tqdm(candidates.iterrows(), total=len(candidates), desc="LLM 분석"):
        vid = str(row["voc_id"])

        if vid in done_ids:
            skipped += 1
            continue

        raw = call_llm(row)

        if raw is None:
            result = RiskResult(
                voc_id=vid,
                risk_score=3,                              # 중간값 → 수동 검토
                risk_type=str(row.get("_rule_type", "unknown")),
                reason="LLM실패-수동검토",
                triggered_by=str(row.get("triggered_by", "rule")),
                processed_at=datetime.now().isoformat(),
            )
            failed += 1
            # 실패 건은 mark_done 안 함 → 재실행 시 자동 재시도

        else:
            score = max(1, min(5, int(raw.get("score", 3))))  # 1~5 범위 보정
            result = RiskResult(
                voc_id=vid,
                risk_score=score,
                risk_type=raw.get("type", "normal"),
                reason=raw.get("reason", "")[:50],
                triggered_by=str(row.get("triggered_by", "rule")),
                processed_at=datetime.now().isoformat(),
            )
            mark_done(vid)  # 성공 건만 체크포인트

        save_result(result)
        time.sleep(0.1)   # Rate limit 방어 (10 RPS 목표)

    # 5. 요약
    log.info("=" * 60)
    log.info(
        f"완료: {len(candidates) - skipped}건 처리 "
        f"| 스킵 {skipped}건 | 실패(수동검토) {failed}건"
    )
    log.info(f"결과: {OUTPUT_PATH.resolve()}")

    # 6. 결과 분포 출력
    if OUTPUT_PATH.exists():
        results_df = pd.read_json(OUTPUT_PATH, lines=True)
        print("\n[리스크 타입 분포]")
        print(results_df["risk_type"].value_counts().to_string())
        print("\n[점수 분포 (1=단순, 5=즉시대응)]")
        print(results_df["risk_score"].value_counts().sort_index().to_string())
        urgent = results_df[results_df["risk_score"] == 5][["voc_id", "risk_type", "reason"]]
        if not urgent.empty:
            print(f"\n[즉시 대응 필요 (score=5) — {len(urgent)}건]")
            print(urgent.to_string(index=False))

    return OUTPUT_PATH


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="VoC Risk Pipeline")
    parser.add_argument(
        "csv", nargs="?",
        default="../outputs/voc_data_4000.csv",
        help="입력 CSV 경로 (기본: ../outputs/voc_data_4000.csv)",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="체크포인트·결과 초기화 후 처음부터 재실행",
    )
    args = parser.parse_args()
    run_pipeline(args.csv, reset=args.reset)
