# VoC Risk Sentinel

리워드 광고 플랫폼의 고객 문의(VoC)를 **자동으로 리스크 분류**하는 하이브리드 파이프라인입니다.

Rule-based 키워드 필터링으로 고위험 건을 1차 선별한 뒤, **Gemini 2.0 Flash**로 정밀 분석하여 Critical / High / Medium / Low / Grey Zone 5단계로 등급을 판정합니다. 전량 LLM 분석 대비 **약 70~90%의 API 호출을 절감**하면서도 고위험 건의 누락을 방지합니다.

---

## 프로젝트 구조

```
voc-risk-sentinel/
├── .env.example          # API Key 설정 템플릿
├── .gitignore
├── requirements.txt
├── gen_data.py           # Step 0: 합성 VoC 데이터 300건 생성
├── analyze_voc.py        # Step 1~3: 하이브리드 분석 파이프라인
├── data/
│   └── voc_data_300.csv  # 생성된 합성 데이터
└── outputs/
    ├── voc_results.jsonl       # 분석 결과 (JSON Lines)
    └── evaluation_report.txt   # 검증 보고서
```

---

## 파이프라인 흐름

```
[300건 VoC 합성데이터]
        │
        ▼
┌──────────────────────────┐
│  Step 1: Rule-based      │  키워드 매칭 + 로그 패턴 분석
│  Pre-Filtering           │  → 고위험 후보 추출
└──────────┬───────────────┘
           ▼
┌──────────────────────────┐
│  Step 2: LLM Precision   │  Gemini 2.5 Flash
│  Scoring                 │  → risk_level + risk_score + reasoning
└──────────┬───────────────┘
           ▼
┌──────────────────────────┐
│  미탐율 방어 (5% 감사)     │  나머지 건에서 랜덤 샘플링
└──────────┬───────────────┘
           ▼
   [voc_results.jsonl]
   [evaluation_report.txt]
```

---

## 빠른 시작

### 1. 클론 및 의존성 설치

```bash
git clone https://github.com/<your-username>/voc-risk-sentinel.git
cd voc-risk-sentinel

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. API Key 설정

[Google AI Studio](https://aistudio.google.com/apikey)에서 Gemini API Key를 발급받은 뒤, 프로젝트 루트에 `.env` 파일을 생성합니다.

```bash
cp .env.example .env
```

`.env` 파일을 열어 실제 키를 입력합니다:

```
GEMINI_API_KEY=AIzaSy...실제_키_값
```

> **주의:** `.env` 파일은 `.gitignore`에 의해 Git 추적에서 제외됩니다. 절대 GitHub에 업로드하지 마세요.

> **API Key 없이도 실행 가능합니다.** Key가 없으면 자동으로 Rule-based 모드로 전환되어 동작합니다.

### 3. 실행

```bash
# Step 0: 합성 데이터 생성 (300건)
python gen_data.py

# Step 1~3: 분석 파이프라인 실행
python analyze_voc.py
```

실행이 완료되면 `outputs/` 폴더에 결과가 저장됩니다.

---

## 리스크 등급 체계

| 등급 | 점수 | 정의 | 대응 방식 |
|------|------|------|-----------|
| **Critical** | 81~100 | 법적 대응 언급 (금감원, 소송 등) | 즉시 에스컬레이션 + 정책 변경 검토 |
| **High** | 61~80 | 외부 기관 신고 위협, 심한 욕설 | 24시간 내 대응 + 원인 분석 |
| **Medium** | 41~60 | 시스템 오류, 기술적 확인 필요 | 일반 대응 프로세스 |
| **Low** | 0~40 | 단순 미지급, FAQ 해결 가능 | 자동응답 처리 |
| **Grey Zone** | 판단 유보 | 어뷰징 의심, 증거 불충분 | 추가 조사 후 판정 |

---

## 합성 데이터 구성

| 항목 | 분포 |
|------|------|
| 리스크 등급 | Low 60%, Grey 25%, Medium 10%, High 3%, Critical 2% |
| 카테고리 | 리워드미지급 80%, 광고참여불가 15%, 기타 5% |
| 광고 유형 | CPA 80%, CPS 5%, CPI/CPE 10%, 기타 5% |
| 욕설 포함 | 약 10% |

---

## 토큰 최적화 전략

| 기법 | 효과 |
|------|------|
| Rule-based 1차 필터링 | 전체의 약 25~30%만 LLM에 투입 |
| `response_schema` 적용 | 구조화된 JSON 출력 강제, 파싱 실패 방지 |
| `thinking_budget=0` | 추론 토큰 비용 제거 |
| 시스템 프롬프트 압축 | 분류 기준 핵심만 전달 (불필요 수식어 제거) |
| 5% 랜덤 감사 | 미탐율 방어 + 최소 비용 |

---

## Streamlit Cloud 배포

1. GitHub에 push한 뒤 [Streamlit Cloud](https://streamlit.io/cloud)에서 레포를 연결합니다.
2. **Secrets 설정:** Streamlit Cloud 대시보드 → Settings → Secrets에 아래 내용을 추가합니다:
   ```toml
   GEMINI_API_KEY = "AIzaSy...실제_키_값"
   ```
3. 대시보드 앱 파일을 지정하고 Deploy를 클릭합니다.

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 언어 | Python 3.11+ |
| LLM | Google Gemini 2.5 Flash (`google-genai`) |
| 데이터 | pandas, CSV/JSONL |
| 대시보드 | Streamlit, Plotly |
| 환경 관리 | python-dotenv |

---

## 라이선스

이 프로젝트는 포트폴리오 목적으로 제작되었습니다. 실제 회사 데이터는 포함되어 있지 않으며, 모든 VoC 데이터는 합성(Synthetic) 데이터입니다.
