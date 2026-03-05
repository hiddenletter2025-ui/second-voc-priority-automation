import os
import json
import pandas as pd
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# [1] API 설정 - v1 경로로 안전하게 접속
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY"),
    http_options=types.HttpOptions(api_version='v1')
)

# 2026년 기준 가장 효율적인 모델 사용
MODEL_NAME = 'gemini-2.5-flash' 

# [2] 프롬프트 보강: JSON만 출력하도록 강제함
SYSTEM_PROMPT = """
# Role: 리워드 광고 플랫폼 리스크 매니저
# Task: VoC 리스크 분류 (JSON 형식으로만 답변)
# Rules:
1. Critical(81-100): 법적대응/금감원 언급, 서비스 마비
2. High(61-80): 소비자원/민원 언급, 심한 욕설
3. Medium(41-60): 시스템 오류(백화, 클릭불가), 트래킹 결함
4. Low(0-40): 단순 미지급, FAQ 문의
5. Grey: Log:'No_Record' & Count >= 10 (어뷰징), 패턴 반복
# Output Format:
{"risk_level": "등급", "risk_score": 점수, "is_grey_zone": true/false, "reasoning": "근거"}
"""

def classify_voc(voc_row):
    user_input = f"Txt:{voc_row['voc_content']}, Log:{voc_row['log_matching']}, Cnt:{voc_row['daily_query_cnt']}"
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=f"{SYSTEM_PROMPT}\nIn:{user_input}"
        )
        
        # [수정] 텍스트에서 JSON 부분만 안전하게 추출
        clean_text = response.text.strip()
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].split("```")[0].strip()
            
        return json.loads(clean_text)
    except Exception as e:
        time.sleep(1) # 에러 시 1초 대기
        return {"risk_level": "Error", "risk_score": 0, "is_grey_zone": False, "reasoning": str(e)}

if __name__ == "__main__":
    input_file = "voc_data_4000.csv"
    output_file = "voc_analysis_results.csv"
    df = pd.read_csv(input_file)
    
    # [3] 테스트 여부 선택 기능
    choice = input("테스트(10개)는 't', 전체 실행은 'a'를 입력해: ").lower()
    
    if choice == 't':
        process_df = df.head(10).copy()
        print(f"🔬 10개 데이터로 테스트 분석 시작...")
    else:
        process_df = df.copy()
        print(f"🚀 전체 {len(process_df)}건 분석 시작...")

    # [4] 분석 수행
    results = []
    for _, row in tqdm(process_df.iterrows(), total=len(process_df)):
        res = classify_voc(row)
        results.append(res)
        time.sleep(0.3) # 유료 티어 속도 조절

    # [5] 결과 합치기 및 저장
    res_df = pd.json_normalize(results)
    final_df = pd.concat([process_df.reset_index(drop=True), res_df], axis=1)
    
    final_df.to_csv(output_file, index=False, encoding="utf-8-sig")
    print(f"\n✅ 분석 완료! 결과가 {output_file}에 저장됐어.")
    
    if choice == 't':
        print("\n👇 [테스트 결과 샘플]")
        print(final_df[['voc_id', 'risk_level', 'risk_score']].head())