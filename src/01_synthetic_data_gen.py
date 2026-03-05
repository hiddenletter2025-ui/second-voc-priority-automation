import pandas as pd
import random
from datetime import datetime, timedelta

# 1. 기초 데이터 설정
ad_names = ["OO게임 멀티미션", "네이버 지도 장소 찜하기", "쇼핑 탭 상품 찾기", "OO보험 상담 신청", "인스타그램 팔로우"]
ad_types = ["CPA", "CPA", "CPA", "CPA", "CPA"]
log_options = ["Match", "Mismatch", "No_Record"]

# 2. 페르소나별 문의 템플릿 (리스크 등급별 실제 패턴 반영)
templates = {
    "Critical": [
        "{ad_name} 일주일째 리워드 안 들어옴. 사기 치는 거임? 금감원에 신고함.",
        "미션 다 했는데 포인트 지급 안 됨. 이거 명백한 사기임. 법적으로 대응하겠음.",
    ],
    "High": [
        "정답 제대로 썼는데 왜 오답임? 포인트 주기 싫어서 수 쓰는 거 다 보임. 사기꾼들아.",
        "소비자원에 민원 넣을게요. 사람 장난치는 것도 아니고 뭐 하는 겁니까?",
    ],
    "Medium": [
        "참여하기 눌러도 페이지가 안 넘어가요. 화면 백화 현상 있음.",
        "10레벨은 들어왔는데 20레벨부터 기록이 안 떠요. 트래킹 오류 확인 바람.",
    ],
    "Low": [
        "리워드 안 들어왔어요 확인 부탁드려요.",
        "참여 완료했는데 언제 적립되나요?",
    ],
    "Grey": [
        "리워드 미지급 / 유저ID: {user_id} / 연락처 별도 제출",
        "포인트 안 들어옴. 빨리 확인해서 넣어주쇼.",
    ]
}

# 3. 데이터 생성 로직
data = []
start_time = datetime(2026, 3, 1, 9, 0, 0)

for i in range(4000):
    # 가중치에 따른 리스크 레벨 결정 (Low를 가장 많게, Critical을 적게)
    level = random.choices(
        ["Critical", "High", "Medium", "Low", "Grey"], 
        weights=[2, 8, 15, 60, 15]
    )[0]
    
    ad_idx = random.randint(0, len(ad_names)-1)
    user_id = f"USER_{random.randint(1000, 9999)}"
    
    # 데이터 조립
    row = {
        "voc_id": f"TK-{i+1:04d}",
        "created_at": start_time + timedelta(minutes=random.randint(1, 10000)),
        "user_id": user_id,
        "ad_type": ad_types[ad_idx],
        "ad_name": ad_names[ad_idx],
        "voc_content": random.choice(templates[level]).format(ad_name=ad_names[ad_idx], user_id=user_id),
        "log_matching": random.choices(log_options, weights=[70, 20, 10])[0],
        "daily_query_cnt": random.randint(1, 3) if level != "Grey" else random.randint(10, 30),
        "actual_risk_level": level # 정답 셋 (검증용)
    }
    data.append(row)

# 4. CSV 저장
df = pd.DataFrame(data)
import pathlib
out_path = pathlib.Path(__file__).parent / "voc_data_4000.csv"
df.to_csv(out_path, index=False, encoding="utf-8-sig")
print(f"4,000건의 합성 데이터 생성 완료! → {out_path}")