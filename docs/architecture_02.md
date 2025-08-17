# 벼리(Byeoli) 챗봇 프로젝트 인계 문서 v3.0

## 📋 **프로젝트 개요**
- **프로젝트명**: 벼리(Byeoli) - 경상남도인재개발원 RAG 기반 대화형 챗봇
- **목표**: 인간 친화적 대화형 질의응답 서비스 (5턴 슬라이딩 윈도우 + Confidence 기반 4단계 분기)
- **최종 배포**: GitHub + Streamlit Cloud

## 🎯 **현재까지 완료된 작업**

### **1. 아키텍처 설계 완료** ✅
- **핵심 원칙 확정**: 모든 핸들러 병렬 실행 → chunk 수집 → 통합 LLM 호출
- **기존 Router 제거**: Top-2 핸들러 선택 방식 완전 폐기
- **대화형 시스템**: 5턴 슬라이딩 윈도우 + 백그라운드 요약 (Threading)
- **Architecture v3.0 최종본 완성**: 모든 기술 명세 문서화

### **2. Confidence 기반 4단계 분기 체계 설계** ✅
```python
# 최종 확정된 구조
0.0 ~ 0.20점: 일상 대화 (벡터스토어 기반 서비스 소개)
0.20초과 ~ 0.50점: 정보 부족 (담당부서 연락처 제공)
0.50점초과 ~ 핸들러별기준: 되묻기 ("혹시 이런 의미인가요?")
핸들러별기준 초과 ~ 1.0점: 정상 RAG 답변

※ 최고 confidence chunk가 판단 기준
```

### **3. 모듈 구조 단순화** ✅
- ❌ **복잡한 context_manager.py 완전 삭제** 결정
- ✅ **conversation_manager.py 하나로 통합**: 대화 관리 + 지시어 해소 + Confidence 분기
- ✅ **설정 파일 분리**: config/thresholds.py (쉬운 조정을 위해)

### **4. 핵심 기능 명세 완료** ✅
- **지시어 해소**: "그 과정" → "중견리더 과정"
- **백그라운드 요약**: Threading으로 5턴마다 요약 생성
- **실시간 스트리밍**: 단어 단위 출력
- **오류 처리**: 요약 실패시 대체 로직

## 🔧 **확정된 설정값**

### **Confidence 임계값 (config/thresholds.py)**
```python
COMMON_THRESHOLDS = {
    "casual_chat": 0.20,        # 일상 대화
    "insufficient_info": 0.50   # 정보 부족
}

HANDLER_THRESHOLDS = {
    "satisfaction": 0.70,  # 만족도: 정확성 중요
    "general": 0.65,       # 일반 정보: 관대
    "cyber": 0.75,         # 사이버교육: 엄격
    "menu": 0.60,          # 식단: 관대
    "notice": 0.65,        # 공지사항: 적당히
    "publish": 0.70        # 발행물: 정확히
}
```

### **담당부서 연락처**
```python
DEPARTMENT_CONTACTS = {
    "general": "인재양성과 교육기획담당 (055-254-2051)",
    "satisfaction": "인재개발지원과 평가분석담당 (055-254-2021)",
    "cyber": "인재양성과 사이버담당 (055-254-2081)",
    "menu": "인재개발지원과 총무담당 (055-254-2096)",
    "notice": "경상남도인재개발원 대표번호 (055-254-2051)",
    "publish": "경상남도인재개발원 대표번호 (055-254-2051)"
}
```

## 📁 **최종 파일 구조**
```
streamlit_app/
├── app.py                          # 메인 Streamlit 앱 (대화형 UI + 스트리밍)
├── handlers/
│   ├── base_handler.py            # CentralOrchestrator (Confidence 분기)
│   ├── satisfaction_handler.py    # search_chunks만 담당  
│   ├── general_handler.py         # search_chunks만 담당
│   ├── notice_handler.py          # search_chunks만 담당
│   ├── cyber_handler.py           # search_chunks만 담당
│   ├── menu_handler.py            # search_chunks만 담당
│   └── publish_handler.py         # search_chunks만 담당
├── utils/
│   ├── conversation_manager.py    # 🆕 대화 관리 올인원 (핵심 모듈)
│   ├── index_manager.py           # 벡터스토어 관리 (싱글톤)
│   ├── contracts.py               # 데이터 클래스 정의
│   └── logging_utils.py           # 로깅 유틸
├── config/
│   ├── thresholds.py              # 🆕 Confidence 설정값 (조정 편의성)
│   └── config.py                  # 기본 설정
├── vectorstores/                   # 벡터스토어 파일들 (GitHub 업로드)
│   ├── vectorstore_general/
│   ├── vectorstore_satisfaction/
│   ├── vectorstore_cyber/
│   ├── vectorstore_menu/
│   ├── vectorstore_notice/
│   └── vectorstore_publish/
└── requirements.txt
```

## 🚀 **다음 작업 계획 (우선순위별)**

### **1단계: 기반 설정 및 호환성 작업 (1.5시간) - 🔥 즉시 시작**

#### **1-1. 새로운 설정 파일 생성 (30분)**
**작업**: `config/thresholds.py` 생성
```python
# 파일 내용
COMMON_THRESHOLDS = {
    "casual_chat": 0.20,
    "insufficient_info": 0.50
}

HANDLER_THRESHOLDS = {
    "satisfaction": 0.70,
    "general": 0.65,
    "cyber": 0.75,
    "menu": 0.60,
    "notice": 0.65,
    "publish": 0.70
}

DEPARTMENT_CONTACTS = {
    "general": "인재양성과 교육기획담당 (055-254-2051)",
    "satisfaction": "인재개발지원과 평가분석담당 (055-254-2021)",
    "cyber": "인재양성과 사이버담당 (055-254-2081)",
    "menu": "인재개발지원과 총무담당 (055-254-2096)",
    "notice": "경상남도인재개발원 대표번호 (055-254-2051)",
    "publish": "경상남도인재개발원 대표번호 (055-254-2051)"
}
```

#### **1-2. 기존 파일 호환성 수정 (1시간)**
**작업**: 기존 utils/ 및 config/ 파일들을 새로운 아키텍처에 맞게 수정

**수정 필요 파일들**:

**A) config.py 수정**:
- conversation_manager 관련 설정 추가
- Streamlit secrets 연동 설정 (`get_openai_api_key()` 함수)
- OpenAI 모델 설정 확인 (gpt-4o-mini)

**B) contracts.py 수정**:
```python
# 추가 필요한 데이터 클래스들
@dataclass
class ConversationTurn:
    user_message: str
    bot_response: str
    timestamp: datetime
    confidence: float
    domain_used: List[str]

@dataclass
class Conversation:
    id: str
    turns: List[ConversationTurn]
    summary: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

# 기존 QueryRequest 수정 (대화 맥락 포함)
# 기존 ChunkResult 확인 (confidence 필드 포함되어 있는지)
```

**C) index_manager.py 수정**:
- Streamlit 캐시 데코레이터 적용 (`@st.cache_resource`)
- conversation_manager와의 연동 준비
- 싱글톤 패턴 Streamlit 환경 최적화

**D) logging_utils.py 검토**:
- 대부분 그대로 사용 가능
- conversation 관련 로그 레벨 추가 (필요시)

**완료 조건**: 
- `from config.thresholds import COMMON_THRESHOLDS` 가능
- 기존 파일들이 새로운 시스템과 충돌 없이 import 가능
- Streamlit 환경에서 정상 작동

---

### **2단계: 핵심 모듈 구현 (2-3시간) - 🔥 메인 작업**
**작업**: `utils/conversation_manager.py` 완전 구현

**구현해야 할 클래스 및 메서드**:
```python
class ConversationManager:
    def __init__(self):
        # OpenAI 클라이언트, 설정값 로딩
    
    def add_turn(self, conv_id, user_msg, bot_response):
        # 대화 턴 추가 + 5턴 체크 + 백그라운드 요약
    
    def resolve_references(self, query, recent_context):
        # 지시어 해소: "그것" → "중견리더 과정"
    
    def get_context_for_llm(self, conv_id):
        # 이전 요약 + 현재 턴들 → LLM용 컨텍스트
    
    def determine_response_type(self, chunks):
        # Confidence 기준으로 4단계 분기 결정
    
    def _start_background_summary(self, conv_id, turns):
        # Threading으로 백그라운드 요약 생성
    
    def reset_conversation(self, conv_id):
        # "새 대화 시작" 버튼용
```

**핵심 기능**:
1. **5턴 슬라이딩 윈도우**: 5턴 → 요약 → 새 5턴
2. **지시어 해소**: OpenAI API로 대명사 → 구체적 명사
3. **Confidence 분기**: 최고 chunk 기준으로 4단계 처리
4. **Threading 요약**: 사용자 대기 없이 백그라운드 처리
5. **오류 처리**: 요약 실패시 간단 요약으로 대체

**완료 조건**: 단독 테스트로 대화 기록 관리 및 요약 생성 확인

---

### **3단계: 중앙 조율기 수정 (1-2시간)**
**작업**: `handlers/base_handler.py` 수정

**기존 코랩 코드 활용하여**:
- conversation_manager와 연동
- 4단계 분기 로직 추가 (`_handle_casual_chat`, `_handle_clarification` 등)
- 스트리밍 메서드 추가 (`stream_response`)

**완료 조건**: conversation_manager + base_handler 연동 테스트 성공

---

### **4단계: 개별 핸들러 분리 (1시간)**
**작업**: satisfaction_handler.py, general_handler.py 등 6개 파일 생성

**각 핸들러 구조**:
```python
class SatisfactionHandler:
    def search_chunks(self, query: str) -> List[ChunkResult]:
        # FAISS 검색 + ChunkResult 변환만
        # LLM 호출 없음
```

**완료 조건**: 기존 base_handler에서 검색 로직 성공적으로 분리

---

### **5단계: Streamlit 앱 구현 (2-3시간)**
**작업**: `app.py` 메인 UI 구현

**필수 기능**:
- 채팅 인터페이스 (st.chat_message)
- 실시간 스트리밍 (st.empty() + yield)
- "새 대화 시작" 버튼
- 대화 기록 표시

**완료 조건**: 브라우저에서 실제 대화 가능

---

### **6단계: 통합 테스트 & 디버깅 (1-2시간)**
**작업**: 전체 시스템 연동 테스트

---

## 💡 **중요한 기술적 결정사항 (이미 확정됨)**

### **1. 검색 방식**
- ✅ `as_retriever().invoke()` 사용 (기존 코랩 방식 유지)
- ❌ `similarity_search_with_score()` 사용하지 않음

### **2. Confidence 계산**
```python
confidence = 1.0 - (rank * 0.1)  # 순서 기반
confidence = max(0.1, confidence)
```

### **3. 중복 제거**
```python
# difflib.SequenceMatcher 사용
similarity >= 0.8  # 80% 이상 유사하면 중복 제거
```

### **4. 백그라운드 요약**
```python
# Threading 사용
thread = threading.Thread(target=summarize)
thread.daemon = True
thread.start()
```

## ⚠️ **주의사항**

1. **OpenAI API 키**: Streamlit secrets 사용 (`st.secrets["OPENAI_API_KEY"]`)
2. **벡터스토어 경로**: GitHub 업로드용 상대경로 사용
3. **메모리 관리**: 대화 기록은 5턴 + 요약만 유지
4. **오류 처리**: 모든 OpenAI API 호출에 try-catch 적용
5. **Threading 안전성**: daemon=True 설정으로 메인 프로그램 종료시 같이 종료

## 🎯 **오늘의 목표 (수정됨)**

### **미니멈 목표** (5시간):
- 1단계 (기반 설정 + 호환성) + 2단계 (conversation_manager) + 3단계 (base_handler) 완료
- 백엔드 로직 완성 (CLI 테스트 가능)

### **이상적 목표** (9시간):
- 1~5단계 완료
- Streamlit 앱까지 완성 (실제 사용 가능)

---

## 📞 **문의사항 및 추가 논의**

### **논의 완료된 사항**:
- ✅ 복잡한 context_manager.py 삭제하고 conversation_manager.py로 통합
- ✅ Confidence 기준값들 (핸들러별 차별화)
- ✅ 4단계 분기 로직 (일상대화, 정보부족, 되묻기, 정상답변)
- ✅ 5턴 슬라이딩 윈도우 + 백그라운드 요약 방식

### **구현 중 확인 필요한 사항**:
- 성능 최적화 관련 세부사항
- UI/UX 디자인 요구사항
- 추가 기능 필요시 확장 방향

---

**현재 상태**: 설계 완료 ✅, 구현 준비 완료 ✅  
**다음 단계**: 1단계 `config/thresholds.py` 생성부터 시작  
**예상 완성**: 오늘 밤 또는 내일 오전 (Streamlit 앱 완성)
