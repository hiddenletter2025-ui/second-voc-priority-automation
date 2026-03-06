"""
gen_data.py — VoC 합성 데이터 300건 생성
=========================================
리스크 등급 비율: Low 60%, Grey 25%, Medium 10%, High 3%, Critical 2%
카테고리 비율  : 리워드미지급 80%, 광고참여불가 15%, 기타 5%
광고 유형 비율 : CPA 80%, CPS 5%, CPI/CPE 10%, 기타 5%
"""

import csv
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# ─── 설정 ───────────────────────────────────────────────────
TOTAL = 300
OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "voc_data_300.csv"

RISK_DIST = {
    "Low": int(TOTAL * 0.60),       # 180
    "Medium": int(TOTAL * 0.10),    # 30
    "High": int(TOTAL * 0.03),      # 9
    "Critical": int(TOTAL * 0.02),  # 6
    "Grey": int(TOTAL * 0.25),      # 75
}
# 반올림 보정 → 합이 300이 되도록
_gap = TOTAL - sum(RISK_DIST.values())
RISK_DIST["Low"] += _gap

CATEGORY_WEIGHTS = {
    "리워드미지급": 0.80,
    "광고참여불가": 0.15,
    "기타": 0.05,
}

AD_TYPE_WEIGHTS = {
    "CPA": 0.80,
    "CPS": 0.05,
    "CPI": 0.05,
    "CPE": 0.05,
    "CPC": 0.02,
    "CPM": 0.01,
    "오퍼월": 0.01,
    "API연동": 0.01,
}

CPA_MISSIONS = [
    "플레이스 검색+저장하기",
    "쇼핑 정답 입력하기",
    "게임 레벨 달성",
    "앱 설치+실행",
    "서비스 가입",
    "SNS 팔로우",
    "라이브커머스 시청",
    "멀티미션 완료",
    "저장하고 링크 입력하기",
]

NON_CPA_ADS = {
    "CPS": ["쇼핑몰 구매 리워드", "브랜드 체험단"],
    "CPI": ["앱 설치 리워드", "신규 앱 체험"],
    "CPE": ["앱 이벤트 달성", "가입 후 튜토리얼 완료"],
    "CPC": ["배너 클릭 리워드", "뉴스 기사 클릭"],
    "CPM": ["영상 노출 리워드", "배너 노출"],
    "오퍼월": ["오퍼월 미션 참여", "오퍼월 앱 설치"],
    "API연동": ["파트너사 연동 미션", "외부 앱 리워드"],
}

PUBLISHERS = {
    "대형": ["카카오뱅크", "토스", "네이버페이", "KB국민은행", "신한SOL"],
    "중형": ["캐시워크", "OK캐쉬백", "리브메이트"],
    "소형": ["포인트타운", "허니스크린"],
}
PUB_WEIGHTS = {"대형": 0.60, "중형": 0.30, "소형": 0.10}

PROFANITY_RATE = 0.10
PROFANITY_INSERTS = [
    "진짜 ㅅㅂ ", "개짜증나네 ", "ㅆㅂ 뭐하는 회사야 ",
    "미친 거 아냐? ", "씨발 ", "개같은 서비스 ",
]

# ─── VoC 템플릿 (등급별) ────────────────────────────────────
VOC_TEMPLATES = {
    "Low": {
        "리워드미지급": [
            "{ad_name} 광고 참여했는데 리워드가 안 들어왔어요.",
            "리워드 지급이 아직 안 됐는데 확인 부탁드립니다.",
            "포인트가 안 들어왔는데 언제 지급되나요?",
            "{ad_name} 완료했는데 리워드 누락된 것 같아요. 확인 부탁드립니다.",
            "광고 참여 완료 후 리워드 미지급입니다. 적립 부탁합니다.",
            "어제 참여한 {ad_name} 리워드가 아직 안 들어왔어요.",
            "미션 완료했는데 포인트 반영이 안 돼요.",
            "리워드 미적립 문의드립니다. {ad_name} 참여 완료했습니다.",
        ],
        "광고참여불가": [
            "{ad_name} 광고가 안 뜨는데 확인 부탁드립니다.",
            "광고 버튼을 눌러도 아무 반응이 없어요.",
        ],
        "기타": [
            "포인트 사용 방법이 궁금합니다.",
            "리워드 지급 기준이 어떻게 되나요?",
            "참여 내역 확인은 어디서 하나요?",
        ],
    },
    "Medium": {
        "리워드미지급": [
            "{ad_name} 미션 3단계까지 완료했는데 2단계부터 적립이 안 됩니다. 확인 부탁드립니다.",
            "화면이 하얗게 되면서 미션 완료가 안 됐는데 리워드도 안 들어왔어요.",
            "앱 설치하고 실행까지 했는데 트래킹이 안 잡히는 것 같아요.",
            "{ad_name} 미션 중간에 앱이 꺼졌는데 이후 단계 리워드가 누락됐습니다.",
            "같은 광고를 여러 번 시도해도 계속 참여 완료가 안 됩니다. 시스템 문제 아닌가요?",
            "다른 사람들도 같은 문제 겪고 있다는데 {ad_name} 광고 오류 확인 부탁합니다.",
        ],
        "광고참여불가": [
            "특정 광고({ad_name})만 계속 화면이 하얗게 되면서 참여가 안 돼요.",
            "{ad_name} 클릭하면 무한 로딩만 되고 페이지가 안 열립니다.",
            "광고 참여 버튼이 비활성화되어 있어서 참여 자체가 불가합니다.",
        ],
        "기타": [
            "앱이 자꾸 튕겨요. 여러 기기에서 동일 증상입니다.",
        ],
    },
    "High": {
        "리워드미지급": [
            "이거 소비자원에 신고할게요. 참여 완료했는데 리워드 안 주면 사기 아닙니까?",
            "벌써 세 번째 문의인데 아직도 해결이 안 되고 있어요. 소비자보호원에 민원 넣겠습니다.",
            "지금 당장 해결 안 해주면 각종 커뮤니티에 다 올릴 겁니다. {ad_name} 리워드 즉시 지급해주세요.",
        ],
        "광고참여불가": [
            "몇 번을 해도 안 되는 광고를 왜 올려놓는 겁니까? 소비자원 신고 준비 중입니다.",
        ],
        "기타": [
            "서비스 품질이 이 모양인데 소비자원에 정식으로 민원 접수하겠습니다.",
        ],
    },
    "Critical": {
        "리워드미지급": [
            "법적 조치 취하겠습니다. 금감원에 민원 넣을 예정이고, 이건 명백한 사기입니다.",
            "변호사 선임 완료했습니다. 미지급 리워드 건으로 소송 진행합니다.",
            "금감원에 이미 신고했고, 추가로 법적 대응 준비 중입니다. 빨리 해결하세요.",
        ],
        "광고참여불가": [
            "고소장 접수 준비 중입니다. 거짓 광고로 사용자를 기만하는 것은 위법입니다.",
        ],
        "기타": [
            "금감원 + 소비자원 동시 신고 완료. 법적 절차 밟겠습니다.",
        ],
    },
    "Grey": {
        "리워드미지급": [
            "매일 같은 미션 20건 넘게 참여하는데 절반은 적립 안 됩니다. 확인해주세요.",
            "스크린샷 보내드립니다. 분명 완료했는데 로그에 안 잡힌다니 이해가 안 됩니다.",
            "참여 완료 캡처본 있는데 시스템에서는 미참여라고 뜹니다. 기록 확인해주세요.",
            "{ad_name} 리워드 안 들어와서 문의드립니다. 제 친구도 같은 내용으로 문의했대요.",
            "게임 레벨 달성 증빙 첨부합니다. 트래커에 안 보인다고 하셨는데 이건 시스템 문제 아닌가요?",
            "하루에 15건 이상 문의하는 게 이상하다고요? 진짜 다 참여한 건데 왜 안 되는지 모르겠어요.",
            "리워드 안 들어왔어요\n홍길동\n010-0000-0000",
            "리워드 안 들어왔어요\n이영희\n010-1111-1111",
            "리워드 안 들어왔어요\n김철수\n010-2222-2222",
        ],
        "광고참여불가": [
            "다른 계정으로도 해봤는데 같은 광고가 안 되네요. 왜 그런 건가요?",
            "여러 기기에서 시도했는데 이 광고만 계속 안 됩니다. VPN은 안 쓰고 있어요.",
        ],
        "기타": [
            "제가 왜 어뷰저 처리됐는지 설명해주세요. 정상적으로 참여했습니다.",
        ],
    },
}

# ─── 유틸 함수 ──────────────────────────────────────────────

def _pick_weighted(weight_dict: dict) -> str:
    keys = list(weight_dict.keys())
    weights = [weight_dict[k] for k in keys]
    return random.choices(keys, weights=weights, k=1)[0]


def _pick_publisher() -> str:
    tier = _pick_weighted(PUB_WEIGHTS)
    return random.choice(PUBLISHERS[tier])


def _pick_ad(ad_type: str) -> str:
    if ad_type == "CPA":
        return random.choice(CPA_MISSIONS)
    return random.choice(NON_CPA_ADS.get(ad_type, ["기타 광고"]))


def _log_matching(risk: str) -> str:
    """Grey Zone과 일부 Medium은 'No_Record'를 부여."""
    if risk == "Grey":
        return random.choice(["No_Record"] * 8 + ["Match"] * 2)
    if risk == "Medium":
        return random.choice(["No_Record"] * 3 + ["Match"] * 7)
    if risk in ("High", "Critical"):
        return random.choice(["No_Record", "Match"])
    return random.choice(["Match"] * 9 + ["No_Record"])


def _daily_query_cnt(risk: str) -> int:
    """Grey Zone은 10 이상 비율 높게, Low는 1~3 중심."""
    if risk == "Grey":
        return random.choice(list(range(10, 35)) * 3 + list(range(1, 10)))
    if risk in ("High", "Critical"):
        return random.randint(3, 15)
    if risk == "Medium":
        return random.randint(2, 8)
    return random.randint(1, 3)


def _maybe_add_profanity(text: str, risk: str) -> str:
    """High / Critical은 욕설 확률 높게, 전체 약 10%."""
    if risk in ("High", "Critical"):
        rate = 0.45
    elif risk == "Grey":
        rate = 0.10
    else:
        rate = 0.05
    if random.random() < rate:
        return random.choice(PROFANITY_INSERTS) + text
    return text


# ─── 메인 생성 로직 ─────────────────────────────────────────

def generate_rows() -> list[dict]:
    rows: list[dict] = []
    base_date = datetime(2025, 6, 1)

    for risk_level, count in RISK_DIST.items():
        for _ in range(count):
            category = _pick_weighted(CATEGORY_WEIGHTS)
            ad_type = _pick_weighted(AD_TYPE_WEIGHTS)
            ad_name = _pick_ad(ad_type)

            templates = VOC_TEMPLATES[risk_level].get(
                category, VOC_TEMPLATES[risk_level]["리워드미지급"]
            )
            content = random.choice(templates).format(ad_name=ad_name)
            content = _maybe_add_profanity(content, risk_level)

            created_at = base_date + timedelta(
                days=random.randint(0, 29),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )

            rows.append(
                {
                    "voc_id": f"VOC-{uuid.uuid4().hex[:8].upper()}",
                    "created_at": created_at.strftime("%Y-%m-%d %H:%M"),
                    "user_id": f"U{random.randint(100000, 999999)}",
                    "publisher": _pick_publisher(),
                    "ad_type": ad_type,
                    "ad_name": ad_name,
                    "category": category,
                    "voc_content": content,
                    "log_matching": _log_matching(risk_level),
                    "daily_query_cnt": _daily_query_cnt(risk_level),
                    "actual_risk_level": risk_level,
                }
            )

    random.shuffle(rows)
    return rows


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = generate_rows()

    fieldnames = [
        "voc_id", "created_at", "user_id", "publisher",
        "ad_type", "ad_name", "category", "voc_content",
        "log_matching", "daily_query_cnt", "actual_risk_level",
    ]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # 분포 검증 출력
    from collections import Counter
    risk_counts = Counter(r["actual_risk_level"] for r in rows)
    cat_counts = Counter(r["category"] for r in rows)
    ad_counts = Counter(r["ad_type"] for r in rows)

    print(f"✅ {OUTPUT_FILE} 생성 완료 ({len(rows)}건)")
    print(f"\n📊 리스크 등급 분포:")
    for k in ["Low", "Medium", "High", "Critical", "Grey"]:
        print(f"   {k:10s}: {risk_counts.get(k, 0):>4d}건 ({risk_counts.get(k, 0)/len(rows)*100:.1f}%)")
    print(f"\n📊 카테고리 분포:")
    for k, v in cat_counts.most_common():
        print(f"   {k:12s}: {v:>4d}건 ({v/len(rows)*100:.1f}%)")
    print(f"\n📊 광고 유형 분포:")
    for k, v in ad_counts.most_common():
        print(f"   {k:8s}: {v:>4d}건 ({v/len(rows)*100:.1f}%)")


if __name__ == "__main__":
    random.seed(42)
    main()
