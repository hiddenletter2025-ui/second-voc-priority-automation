import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

print("🔎 사용 가능한 Gemini 모델 목록:")
try:
    for model in client.models.list():
        # 최신 SDK(google-genai)에서는 supported_actions를 사용함
        if 'generateContent' in model.supported_actions:
            # 출력된 이 이름을 복사해서 MODEL_ID에 넣으면 돼!
            print(f"- {model.name}")
except Exception as e:
    print(f"❌ 목록 가져오기 실패: {e}") 