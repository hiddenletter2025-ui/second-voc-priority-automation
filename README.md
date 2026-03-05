# 🛡️ VoC Risk Sentinel

> **리워드 광고 플랫폼을 위한 VoC 리스크 자동 분류 시스템**
> Rule-based 필터링과 Gemini 2.5 Flash를 결합한 하이브리드 파이프라인으로 법적 위험·시스템 결함·어뷰징 패턴을 자동 탐지하고, 실시간 대시보드로 시각화합니다.

---

## ✨ 주요 기능

- **하이브리드 파이프라인** — Rule-based 1차 필터링으로 고위험 후보를 추출한 뒤, LLM으로 정밀 분석. LLM 호출량을 전수 분석 대비 **최대 90% 절감**
- **5단계 리스크 분류** — Critical(법적) / High(시스템) / Medium(어뷰징) / Low(일반) / Grey Zone
- **실시간 대시보드** — Streamlit + Plotly 기반 다크모드 UI, KPI 카드·도넛 차트·인터랙티브 테이블
- **Checkpoint 재시도** — 처리 중 중단 시 완료 건 자동 스킵, 실패 건만 재시도
- **미탐율 방어** — 필터 통과 건 5% 랜덤 LLM 감사로 키워드 우회 케이스 보완

---

## 📁 프로젝트 구조

```
voc-priority-automation/
├── app.py                        # Streamlit 대시보드 (메인 진입점)
├── requirements.txt              # 의존성 패키지
├── .env.example                  # 환경변수 템플릿
├── .gitignore
│
├── src/
│   ├── 01_synthetic_data_gen.py  # 합성 데이터 4,000건 생성
│   ├── 02_analyze_voc.py         # 파이프라인 v1 (참고용)
│   ├── analyze_voc.py            # 파이프라인 v2 (현재 사용)
│   └── check_model.py            # 사용 가능한 모델 목록 확인
│
└── data/
    └── sample_voc_100.csv        # 샘플 데이터 100건 (데모용)
```

> **전체 데이터(`voc_data_4000.csv`)** 는 `src/01_synthetic_data_gen.py`를 실행하여 직접 생성하세요.

---

## 🚀 빠른 시작

### 1. 저장소 클론

```bash
git clone https://github.com/<your-username>/voc-priority-automation.git
cd voc-priority-automation
```

### 2. 가상환경 생성 및 의존성 설치

```bash
python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
.venv\Scripts\activate

pip install -r requirements.txt
```

### 3. API Key 설정 ⚠️

```bash
# 템플릿 복사
cp .env.example .env
```

`.env` 파일을 열어 실제 Gemini API Key를 입력하세요:

```dotenv
GEMINI_API_KEY=your_gemini_api_key_here
```

> **Gemini API Key 발급**: [Google AI Studio](https://aistudio.google.com/app/apikey) 에서 무료로 발급받을 수 있습니다.
> ⚠️ `.env` 파일은 절대 Git에 커밋하지 마세요. `.gitignore`에 포함되어 있습니다.

### 4. 데이터 생성 (선택)

```bash
# 합성 데이터 4,000건 생성 (src/voc_data_4000.csv 생성됨)
cd src
python 01_synthetic_data_gen.py
```

> 빠른 테스트는 `data/sample_voc_100.csv`(100건)를 사용하세요.

### 5. 파이프라인 실행 (VoC 분류)

```bash
cd src

# 샘플 100건으로 테스트
python analyze_voc.py ../data/sample_voc_100.csv

# 전체 4,000건 실행
python analyze_voc.py voc_data_4000.csv

# 체크포인트 초기화 후 처음부터 재실행
python analyze_voc.py voc_data_4000.csv --reset
```

분석 완료 시 `src/voc_results.jsonl`이 생성됩니다.

### 6. 대시보드 실행

```bash
# 프로젝트 루트에서 실행
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속

---

## ☁️ Streamlit Cloud 배포

Streamlit Cloud에 배포하면 별도 서버 없이 대시보드를 공개할 수 있습니다.

### 배포 전 준비

1. `voc_results.jsonl` 분석 결과 파일을 저장소에 포함시키거나, 대시보드가 샘플 데이터를 읽도록 설정
2. GitHub 저장소에 코드 푸시

### 배포 단계

1. [share.streamlit.io](https://share.streamlit.io) 접속 후 GitHub 계정 연동
2. **New app** → 저장소/브랜치 선택 → Main file path: `app.py`
3. **Advanced settings → Secrets** 에 API Key 입력:

```toml
GEMINI_API_KEY = "your_gemini_api_key_here"
```

> Streamlit Cloud에서는 `.env` 대신 **Secrets** 기능을 사용합니다.
> `app.py`는 `os.getenv()`로 환경변수를 읽으므로 Secrets가 자동으로 적용됩니다.

4. **Deploy** 클릭

---

## 🧠 파이프라인 상세

### 하이브리드 아키텍처

```
[VoC 원시 데이터]
      │
      ▼
┌─────────────────────┐
│  Rule-based Filter  │  키워드 매칭 + 로그 패턴
│  (Step 1)           │  → 고위험 후보 5~10% 추출
└──────────┬──────────┘
           │ ~200~400건
           ▼
┌─────────────────────┐
│  LLM Precision      │  Gemini 2.5 Flash
│  Scoring (Step 2)   │  → Risk Score 1~5 + Reasoning
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  미탐율 방어 감사    │  필터 통과 건 5% 랜덤 LLM 검증
└─────────────────────┘
```

### 리스크 등급 기준

| Score | 등급 | 유형 | 판단 기준 |
|:---:|------|------|----------|
| 5 | **Critical** | `legal` | 금감원·고소·소송·법적조치 언급 |
| 4 | **High** | `system` | 포인트 미지급 + 로그 불일치 반복 |
| 3 | **Medium** | `abuse` / `system` | 어뷰징 의심, 반복 문의 3회↑ |
| 2 | **Low** | `normal` | 일반 서비스 문의 |
| 1 | **Minimal** | `normal` | 단순 정보 요청 |

### 토큰 최적화 기법

- `thinking_budget=0` — Flash 모델 사고 토큰 완전 차단
- `response_schema` — JSON 구조 API 레벨 강제, 포맷 설명 불필요
- 시스템 프롬프트 ~30 tokens (기존 대비 75% 압축)
- `max_output_tokens=80` — 최솟값 제한

---

## ⚙️ 환경 요구사항

- Python 3.11 이상 (개발: 3.13)
- Gemini API Key ([Google AI Studio](https://aistudio.google.com/app/apikey))
- 주요 패키지: `google-genai`, `streamlit`, `plotly`, `pandas`

---

## 📊 실제 실행 결과 (4,000건 기준)

| 항목 | 수치 |
|------|------|
| LLM 처리 대상 | 1,543건 (전체 38.6%) |
| LLM 비용 절감 | **~90%** (전수 분석 대비) |
| LLM 실패율 | 0% |
| 즉시 대응 필요 (Score 5) | 265건 |

---

## 📄 라이선스

MIT License
