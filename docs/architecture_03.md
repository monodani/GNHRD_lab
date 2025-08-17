# BYEOLI_TALK_AT_GNHRD_app Architecture v3.1 (최종 완성본 + 피드백 시스템)

## 개요

경상남도인재개발원용 RAG 기반 대화형 챗봇으로, 챗봇의 이름은 "벼리(Byeoli)"이며, 다양한 내부 문서(교육계획, 만족도 조사, 학칙, 공지사항 등)를 기반으로 **인간 친화적 대화형 질의응답 서비스**를 제공합니다.

**핵심 설계 원칙**: 
- 모든 핸들러 병렬 실행 → chunk 수집 → 통합 LLM 호출
- **대화 맥락 유지** (5턴 슬라이딩 윈도우 + 백그라운드 요약)
- **지시어 해소** (자연스러운 대화)
- **Confidence 기반 4단계 분기** (일상 대화 + 되묻기)
- **단어 단위 스트리밍**
- **실시간 피드백 시스템** (Firestore 연동)

## 전체 아키텍처

```mermaid
flowchart TD
    %% 데이터 레이어
    subgraph DATA["🗂️ 데이터 레이어"]
        D1[general/]
        D2[publish/]
        D3[satisfaction/]
        D4[cyber/]
        D5[menu/]
        D6[notice/]
    end
    
    %% 빌드타임 처리
    subgraph BUILD["🔨 빌드타임 처리"]
        M1[modules/loader_*.py]
        M2[utils/textifier.py]
        M3[utils/ocr_utils.py]
        M4[schemas/*.json 검증]
    end
    
    %% 벡터스토어
    subgraph VECTOR["📚 벡터스토어"]
        V1[vectorstore_general/]
        V2[vectorstore_publish/]
        V3[vectorstore_satisfaction/]
        V4[vectorstore_cyber/]
        V5[vectorstore_menu/]
        V6[vectorstore_notice/]
    end
    
    %% 런타임 엔진 - 대화형 구조
    subgraph RUNTIME["⚡ 런타임 엔진"]
        R1[index_manager<br/>싱글톤]
        R2[conversation_manager<br/>대화 관리 + 지시어 해소]
        R3[base_handler<br/>CentralOrchestrator]
        R4[병렬 핸들러 실행<br/>All Handlers]
        R5[Confidence 기반<br/>4단계 분기 처리]
        R6[통합 LLM 호출<br/>Single Call]
    end
    
    %% 핸들러 - 검색만 담당
    subgraph HANDLERS["🎯 핸들러 (검색 전용)"]
        H1[handle_general<br/>chunk 반환]
        H2[handle_publish<br/>chunk 반환]
        H3[handle_satisfaction<br/>chunk 반환]
        H4[handle_cyber<br/>chunk 반환]
        H5[handle_menu<br/>chunk 반환]
        H6[handle_notice<br/>chunk 반환]
    end
    
    %% 피드백 시스템
    subgraph FEEDBACK["📝 피드백 시스템"]
        F1[feedback_manager<br/>Firestore 연동]
        F2[실시간 데이터 수집]
        F3[관리자 대시보드<br/>24시간 캐시]
        F4[에러 로그 관리]
    end
    
    %% UI
    UI[🖥️ Streamlit UI<br/>스트리밍 + 대화형 + 피드백]
    
    DATA --> BUILD
    BUILD --> VECTOR
    VECTOR --> R1
    R1 --> R2
    R2 --> R3
    R3 --> R4
    R4 --> HANDLERS
    HANDLERS --> R5
    R5 --> R6
    R6 --> UI
    UI --> F1
    F1 --> F2
    F2 --> F3
    F3 --> F4
```

## 핵심 설계 변경점

### ❌ 기존 방식 (제거됨)
- Router 기반 핸들러 선택
- Top-2 핸들러만 실행
- 각 핸들러가 독립적으로 LLM 호출
- 단발성 질의응답 (대화 맥락 없음)
- 복잡한 context_manager.py
- 키워드 매칭 규칙

### ✅ 새로운 방식 (v3.1)
- **모든 핸들러 병렬 실행**: 6개 핸들러 동시 검색
- **Chunk 수집 방식**: 각 핸들러는 검색만 담당, LLM 호출 없음
- **통합 LLM 호출**: CentralOrchestrator에서 1회만 호출
- **대화형 시스템**: 5턴 슬라이딩 윈도우 + 백그라운드 요약
- **인간 친화적**: 지시어 해소 + confidence 기반 4단계 분기
- **단일 모듈**: conversation_manager.py로 대화 관리 통합
- **실시간 피드백**: Firestore 기반 피드백 수집 및 관리

## 데이터 구조

### ChunkResult 정의
```python
@dataclass
class ChunkResult:
    chunk: TextChunk           # 텍스트 청크 내용
    confidence: float          # 유사도 점수 (0.0-1.0)
    domain: str                # 도메인명 (satisfaction, general, etc.)
    search_method: str = "faiss"  # 검색 방법
    metadata: Dict[str, Any] = field(default_factory=dict)  # 확장 정보
```

### ConversationTurn 정의
```python
@dataclass
class ConversationTurn:
    user_message: str
    bot_response: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))  # 🆕 피드백 연결용
    timestamp: datetime
    confidence: float
    domain_used: List[str]
    feedback: Optional[FeedbackData] = None  # 🆕 피드백 데이터 연결
```

### FeedbackData 정의 (🆕 추가)
```python
@dataclass
class FeedbackData:
    conversation_id: str       # 어떤 대화 세션인지
    message_id: str           # 어떤 답변에 대한 피드백인지
    user_query: str           # 사용자 질문
    bot_response: str         # 챗봇 답변
    feedback_type: str        # "positive" | "negative"
    feedback_reason: Optional[str] = None  # 부정 피드백 사유
    timestamp: datetime = field(default_factory=datetime.now)
```

### 메타데이터 활용
```python
metadata = {
    "source_file": "course_satisfaction.csv",
    "department": "{부서명} {팀명}",
    "contact": "{전화번호}",
    "rank": 1,
    "search_score": 0.85
}
```
- general → 인재양성과 교육기획담당 (055-254-2051)
- satisfaction → 인재개발지원과 평가분석담당 (055-254-2021)
- cyber → 인재양성과 사이버담당 (055-254-2081)
- menu → 인재개발지원과 총무담당 (055-254-2096)
- notice → 경상남도인재개발원 대표번호 (055-254-2051)
- publish → 경상남도인재개발원 대표번호 (055-254-2051)

## 대화형 플로우

### 런타임 질의 플로우 (대화형 v3.1 + 피드백)
```mermaid
sequenceDiagram
    participant User as 사용자
    participant UI as Streamlit
    participant Conv as conversation_manager
    participant Central as base_handler
    participant H1 as general_handler
    participant H2 as satisfaction_handler
    participant Index as index_manager
    participant LLM as OpenAI LLM
    participant FB as feedback_manager
    participant FS as Firestore
    
    User->>UI: 질문 입력
    UI->>Conv: 대화 기록 확인
    
    Note over Conv: 지시어 해소 처리
    Conv->>Conv: "그 과정" → "중견리더 과정"
    
    Conv->>Central: QueryRequest (확장된 쿼리 + 대화 맥락)
    
    Note over Central: 모든 핸들러 병렬 실행
    par 병렬 검색 (0.5-0.8초)
        Central->>H1: search_chunks(expanded_query)
        H1->>Index: FAISS 검색
        Index-->>H1: 유사 문서들
        H1-->>Central: List[ChunkResult]
    and
        Central->>H2: search_chunks(expanded_query)
        H2->>Index: FAISS 검색
        Index-->>H2: 유사 문서들
        H2-->>Central: List[ChunkResult]
    end
    
    Note over Central: Confidence 기반 4단계 분기
    alt Confidence ≤ 0.20 (일상 대화)
        Central->>LLM: 일상 대화 프롬프트
        LLM-->>Central: "안녕하세요! 제가 도와드릴 수 있는 것은..."
    else Confidence ≤ 0.50 (정보 부족)
        Central->>Central: 담당부서 연락처 생성
        Central-->>UI: "정보 부족, 담당부서 연락하세요"
    else Confidence ≤ 핸들러별기준 (되묻기)
        Central->>LLM: 의도 추론 + 되묻기 프롬프트
        LLM-->>Central: "혹시 이런 의미로 질문하신 건가요?"
    else Confidence > 핸들러별기준 (정상 답변)
        Central->>Central: Chunk 통합 & 중복제거
        Central->>LLM: 통합 프롬프트 + 대화맥락 + chunks
        LLM-->>Central: 최종 답변
    end
    
    Central->>Conv: 응답 + 대화 기록 저장 (message_id 포함)
    Conv->>Conv: 5턴 체크 → 백그라운드 요약
    Central->>UI: HandlerResponse
    UI->>User: 스트리밍 출력 + 피드백 버튼 (👍👎)
    
    Note over UI,FS: 피드백 처리
    User->>UI: 피드백 버튼 클릭
    UI->>UI: 버튼 비활성화 (중복 방지)
    alt 부정 피드백
        UI->>User: 사유 입력 영역 확장
        User->>UI: 사유 입력 (선택사항)
    end
    UI->>FB: 피드백 데이터 생성
    FB->>FS: Firestore에 저장 (자동 문서 ID)
    alt 저장 성공
        FS-->>UI: 성공
        UI->>User: "피드백 감사합니다! 🙏" + 벼리 이미지
    else 저장 실패
        FS-->>FB: 에러
        FB->>FS: 에러 로그 저장
        UI->>User: "일시적 오류, 잠시 후 다시 시도해주세요"
    end
```

## Confidence 기반 4단계 분기 체계

### 설정 구조 (config/thresholds.py)
```python
# 공통 기준선 (모든 핸들러 공통)
COMMON_THRESHOLDS = {
    "casual_chat": 0.20,        # 0.0 ~ 0.20: 일상 대화
    "insufficient_info": 0.50   # 0.20초과 ~ 0.50: 정보 부족
}

# 핸들러별 개별 기준 (도메인 특성 반영)
HANDLER_THRESHOLDS = {
    "satisfaction": 0.70,  # 0.50초과~0.70: 되묻기, 0.70초과~1.0: 정상답변
    "general": 0.65,       # 0.50초과~0.65: 되묻기, 0.65초과~1.0: 정상답변
    "cyber": 0.75,         # 0.50초과~0.75: 되묻기, 0.75초과~1.0: 정상답변
    "menu": 0.60,          # 0.50초과~0.60: 되묻기, 0.60초과~1.0: 정상답변
    "notice": 0.65,        # 0.50초과~0.65: 되묻기, 0.65초과~1.0: 정상답변
    "publish": 0.70        # 0.50초과~0.70: 되묻기, 0.70초과~1.0: 정상답변
}
```

### 처리 로직
```python
def determine_response_type(self, chunks):
    """최고 confidence chunk를 기준으로 응답 타입 결정"""
    if not chunks:
        return "casual_chat"
    
    # 최고 confidence chunk 찾기
    max_chunk = max(chunks, key=lambda x: x.confidence)
    max_confidence = max_chunk.confidence
    dominant_domain = max_chunk.domain
    
    # 4단계 분기 처리
    if max_confidence <= COMMON_THRESHOLDS["casual_chat"]:  # ≤ 0.20
        return "casual_chat"
    elif max_confidence <= COMMON_THRESHOLDS["insufficient_info"]:  # ≤ 0.50
        return "insufficient_info"
    elif max_confidence <= HANDLER_THRESHOLDS[dominant_domain]:  # ≤ 핸들러별기준
        return "clarification"
    else:  # > 핸들러별기준
        return "confident_answer"
```

### 응답 타입별 처리

#### 1. 일상 대화 (0.0 ~ 0.20)
```python
def _handle_casual_chat(self, query, context):
    """LLM 기반 일상 대화 + 벡터스토어 기반 서비스 소개"""
    prompt = f"""
    당신은 벼리입니다. 경상남도인재개발원의 친근한 챗봇입니다.
    
    사용자: {query}
    대화 맥락: {context}
    
    제공 가능한 서비스를 자연스럽게 소개하거나 친근하게 응답하세요:
    - 교육과정 정보 (일정, 내용, 신청방법)
    - 만족도 조사 결과 및 분석  
    - 사이버교육 안내
    - 공지사항 및 소식
    - 구내식당 메뉴
    - 각종 발행물 정보
    
    친근하고 도움이 되는 톤으로 답변하세요.
    """
    return self.llm.invoke(prompt).content
```

#### 2. 정보 부족 (0.20초과 ~ 0.50)
```python
def _handle_insufficient_info(self, query):
    """정중한 안내 + 담당부서 연락처 제공"""
    return f"""
    죄송합니다. 요청하신 '{query}'와 관련된 정보를 찾을 수 없습니다. 
    더 구체적으로 질문해 주시거나, 아래 담당부서로 연락하시면 정확한 답변을 받으실 수 있습니다.
    
    📞 **담당부서 연락처**
    • 인재개발지원과 총무담당: 055-254-2011
    • 인재개발지원과 평가분석담당: 055-254-2021  
    • 인재양성과 교육기획담당: 055-254-2051  
    • 인재양성과 교육운영1담당: 055-254-2061
    • 인재양성과 교육운영2담당: 055-254-2071
    • 인재양성과 사이버담당: 055-254-2081
    
    🌐 **홈페이지**: https://www.gyeongnam.go.kr/hrd
    """
```

#### 3. 되묻기 (0.50초과 ~ 핸들러별 기준)
```python
def _handle_clarification(self, query, chunks):
    """검색 결과 기반 의도 추론 + 되묻기"""
    # 검색된 chunks에서 가능한 의도 추출
    possible_topics = [chunk.chunk.content[:100] for chunk in chunks[:3]]
    
    prompt = f"""
    사용자 질문: {query}
    
    검색된 관련 정보들:
    {chr(10).join([f"- {topic}" for topic in possible_topics])}
    
    사용자의 질문이 다소 모호합니다. 검색 결과를 바탕으로 구체적인 질문을 제안하여 
    "혹시 이런 의미로 질문하신 건가요?" 형태로 되물어보세요.
    
    2-3개의 구체적인 선택지를 제공하세요.
    """
    return self.llm.invoke(prompt).content
```

#### 4. 정상 답변 (핸들러별 기준 초과 ~ 1.0)
```python
def _handle_confident_answer(self, query, chunks, context):
    """기존 RAG 로직 (중복제거 + 통합 프롬프트)"""
    unified_chunks = self._deduplicate_chunks(chunks)
    
    prompt = f"""
    당신은 "벼리(영문명: Byeoli)"입니다. 경상남도인재개발원의 종합 정보 제공 챗봇입니다.
    
    이전 대화 맥락:
    {context}
    
    제공된 참고 자료:
    {self._format_chunks_by_domain(unified_chunks)}
    
    현재 질문: {query}
    
    지침:
    1. 이전 대화 맥락을 고려하여 자연스럽게 답변
    2. 제공된 참고 자료만을 활용하여 정확한 답변
    3. 친근하고 전문적인 어조 유지
    4. 구체적인 수치나 정보가 있다면 명시
    """
    return self.llm.invoke(prompt).content
```

## 핵심 모듈별 역할

### conversation_manager.py (올인원 대화 관리)
**책임**: 모든 대화 관련 기능 통합

**주요 기능**:
- **대화 기록 관리**: 5턴 슬라이딩 윈도우
- **백그라운드 요약**: Threading으로 5턴마다 요약 생성
- **지시어 해소**: "그것" → "중견리더 과정" 변환
- **Confidence 판단**: 4단계 분기 처리
- **설정 관리**: threshold 값 로딩

```python
class ConversationManager:
    def __init__(self):
        self.conversations = {}  # 대화 저장소
        self.openai_client = openai.OpenAI(api_key=get_openai_api_key())
        self.common_thresholds = COMMON_THRESHOLDS
        self.handler_thresholds = HANDLER_THRESHOLDS
    
    def add_turn(self, conv_id, user_msg, bot_response):
        """대화 턴 추가 + 5턴 체크 + 백그라운드 요약"""
        message_id = str(uuid.uuid4())  # 🆕 피드백용 고유 ID
        conversation = self.get_conversation(conv_id)
        conversation.turns.append(ConversationTurn(
            user_message=user_msg,
            bot_response=bot_response,
            message_id=message_id,  # 🆕
            timestamp=datetime.now(),
            confidence=0.0,
            domain_used=[]
        ))
        
        # 5턴 도달시 백그라운드 요약
        if len(conversation.turns) >= 5:
            self._start_background_summary(conv_id, conversation.turns.copy())
            conversation.turns = []  # 초기화
        
        return message_id  # 🆕 UI에서 피드백 버튼 연결용
    
    def resolve_references(self, query, recent_context):
        """지시어 해소: "그것" → 구체적 명사"""
        pronouns = ['그것', '그거', '이것', '이거', '그', '이', '저것', '위의', '앞의', '해당']
        
        if not any(pronoun in query for pronoun in pronouns):
            return query
        
        if recent_context:
            prompt = f"""
            이전 대화: {recent_context}
            현재 질문: {query}
            
            질문의 지시어나 대명사를 구체적인 내용으로 바꿔주세요.
            """
            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=100,
                    temperature=0.1,
                    timeout=3.0
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"지시어 해소 실패: {e}")
        
        return query
    
    def get_context_for_llm(self, conv_id):
        """이전 요약 + 현재 턴들 → LLM용 컨텍스트"""
        conversation = self.get_conversation(conv_id)
        context_parts = []
        
        # 이전 요약
        if conversation.summary:
            context_parts.append(f"[이전 대화 요약]: {conversation.summary}")
        
        # 현재 턴들
        for turn in conversation.turns[-3:]:  # 최근 3턴
            context_parts.append(f"사용자: {turn.user_message}")
            context_parts.append(f"벼리: {turn.bot_response}")
        
        return "\n".join(context_parts)
    
    def determine_response_type(self, chunks):
        """최고 confidence chunk 기준으로 응답 타입 결정"""
        if not chunks:
            return "casual_chat"
        
        # 최고 confidence chunk 찾기
        max_chunk = max(chunks, key=lambda x: x.confidence)
        max_confidence = max_chunk.confidence
        dominant_domain = max_chunk.domain
        
        # 4단계 분기 처리
        if max_confidence <= self.common_thresholds["casual_chat"]:
            return "casual_chat"
        elif max_confidence <= self.common_thresholds["insufficient_info"]:
            return "insufficient_info"
        elif max_confidence <= self.handler_thresholds.get(dominant_domain, 0.7):
            return "clarification"
        else:
            return "confident_answer"
```

### feedback_manager.py (🆕 피드백 시스템)
**책임**: Firestore 기반 피드백 데이터 관리

**주요 기능**:
- **실시간 저장**: 피드백 데이터 Firestore 전송
- **에러 처리**: 연결 실패시 에러 로그 저장
- **관리자 기능**: 대시보드용 데이터 조회 (24시간 캐시)

```python
class FeedbackManager:
    def __init__(self):
        self.db = self._initialize_firestore()
    
    def save_feedback(self, feedback_data: FeedbackData) -> bool:
        """피드백 데이터를 Firestore에 저장 (자동 문서 ID)"""
        try:
            # Firestore add() 함수로 자동 ID 생성
            doc_ref = self.db.collection('feedbacks').add(feedback_data.__dict__)
            logger.info(f"피드백 저장 성공: {doc_ref[1].id}")
            return True
        except Exception as e:
            self._log_error("feedback_save_failed", str(e))
            return False
    
    def get_feedback_stats(self) -> Dict:
        """피드백 통계 조회 (24시간 캐시)"""
        try:
            feedbacks = self.db.collection('feedbacks').stream()
            total = 0
            positive = 0
            negative = 0
            
            for doc in feedbacks:
                data = doc.to_dict()
                total += 1
                if data['feedback_type'] == 'positive':
                    positive += 1
                else:
                    negative += 1
            
            return {
                'total': total,
                'positive': positive,
                'negative': negative,
                'positive_rate': round(positive / total * 100, 1) if total > 0 else 0
            }
        except Exception as e:
            self._log_error("stats_query_failed", str(e))
            return {'total': 0, 'positive': 0, 'negative': 0, 'positive_rate': 0}
    
    def get_recent_feedbacks(self, limit: int = 20) -> List[Dict]:
        """최근 피드백 목록 조회"""
        try:
            feedbacks = self.db.collection('feedbacks')\
                               .order_by('timestamp', direction='DESCENDING')\
                               .limit(limit)\
                               .stream()
            
            return [doc.to_dict() for doc in feedbacks]
        except Exception as e:
            self._log_error("recent_feedbacks_query_failed", str(e))
            return []
    
    def _log_error(self, error_type: str, error_message: str):
        """에러 로그를 Firestore에 저장"""
        try:
            error_data = {
                'error_type': error_type,
                'error_message': error_message,
                'timestamp': datetime.now(),
                'session_id': st.session_state.get('session_id', 'unknown')
            }
            self.db.collection('error_logs').add(error_data)
        except Exception as e:
            logger.error(f"에러 로그 저장 실패: {e}")
```

### base_handler.py (CentralOrchestrator)
**책임**: RAG 검색 조율 + Confidence 분기 + LLM 호출

```python
class BaseHandler:
    def __init__(self):
        self.conversation_manager = ConversationManager()
        self.handlers = self._initialize_handlers()
        self.llm = self._initialize_llm()
    
    def handle_with_context(self, conv_id: str, query: str) -> Tuple[str, str]:
        # 1. 지시어 해소
        context = self.conversation_manager.get_context_for_llm(conv_id)
        expanded_query = self.conversation_manager.resolve_references(query, context)
        
        # 2. 모든 핸들러 병렬 실행
        all_chunks = self._collect_chunks_from_all_handlers(expanded_query)
        
        # 3. Confidence 기반 분기 처리
        response_type = self.conversation_manager.determine_response_type(all_chunks)
        
        # 4. 응답 타입별 처리
        if response_type == "casual_chat":
            response = self._handle_casual_chat(query, context)
        elif response_type == "insufficient_info":
            response = self._handle_insufficient_info(query)
        elif response_type == "clarification":
            response = self._handle_clarification(query, all_chunks)
        else:  # confident_answer
            response = self._handle_confident_answer(expanded_query, all_chunks, context)
        
        # 5. 대화 기록 저장 및 message_id 반환
        message_id = self.conversation_manager.add_turn(conv_id, query, response)
        
        return response, message_id  # 🆕 피드백 버튼 연결용 ID 반환
    
    def stream_response(self, conv_id: str, query: str):
        """실시간 스트리밍 응답 (Streamlit용)"""
        # 위와 동일한 로직이지만 stream=True로 처리
        # yield 방식으로 토큰 하나씩 반환
        # 완료 후 message_id 반환
```

### 개별 핸들러 (검색 전용)
```python
class SatisfactionHandler:
    def __init__(self):
        self.threshold = HANDLER_THRESHOLDS["satisfaction"]  # 0.70
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        # 1. FAISS 검색
        vectorstore = self.index_manager.get_vectorstore("satisfaction")
        search_results = vectorstore.as_retriever(k=5).invoke(query)
        
        # 2. Confidence 계산 및 ChunkResult 변환
        chunk_results = []
        for i, doc in enumerate(search_results):
            confidence = self._calculate_confidence(doc, query, i)
            
            chunk_results.append(ChunkResult(
                chunk=TextChunk(doc.page_content, doc.metadata),
                confidence=confidence,
                domain="satisfaction",
                metadata={
                    "source_file": doc.metadata.get("source"),
                    "department": "인재개발지원과 평가분석담당",
                    "contact": "055-254-2021",
                    "rank": i + 1
                }
            ))
        
        # 3. 상위 3개만 반환
        return chunk_results[:3]
    
    def _calculate_confidence(self, doc, query, rank):
        """순서 기반 confidence 계산"""
        base_confidence = 1.0 - (rank * 0.1)  # 1.0, 0.9, 0.8, 0.7, 0.6
        return max(0.1, base_confidence)
```

## 피드백 시스템 아키텍처 (🆕 추가)

### Firestore 데이터 구조
```
feedbacks/
├── {auto_generated_id_001}/
│   ├── conversation_id: "conv_123"
│   ├── message_id: "msg_456"
│   ├── user_query: "교육과정 언제 시작해?"
│   ├── bot_response: "3월에 시작합니다..."
│   ├── feedback_type: "positive"
│   ├── feedback_reason: null
│   └── timestamp: "2024-12-20T10:30:00Z"
├── {auto_generated_id_002}/
│   ├── conversation_id: "conv_124"
│   ├── message_id: "msg_457"
│   ├── user_query: "만족도 조사 결과는?"
│   ├── bot_response: "2024년 종합 만족도는..."
│   ├── feedback_type: "negative"
│   ├── feedback_reason: "정보가 부정확해요"
│   └── timestamp: "2024-12-20T10:35:00Z"
└── ...

error_logs/
├── {auto_generated_id_001}/
│   ├── error_type: "firestore_connection_failed"
│   ├── error_message: "Network timeout"
│   ├── timestamp: "2024-12-20T10:35:00Z"
│   └── session_id: "session_789"
└── ...
```

### 피드백 UI 플로우
```mermaid
sequenceDiagram
    participant User as 사용자
    participant UI as Streamlit UI
    participant FB as feedback_manager
    participant FS as Firestore
    
    User->>UI: 챗봇 답변 확인
    UI->>User: 👍👎 버튼 표시
    
    alt 긍정 피드백
        User->>UI: 👍 클릭
        UI->>UI: 버튼 비활성화
        UI->>FB: FeedbackData(type="positive", reason=null)
    else 부정 피드백
        User->>UI: 👎 클릭
        UI->>UI: 버튼 비활성화
        UI->>User: 사유 입력 영역 확장
        opt 사유 입력
            User->>UI: 사유 입력
        end
        UI->>FB: FeedbackData(type="negative", reason=입력사유)
    end
    
    FB->>FS: add() 함수로 저장 (자동 ID)
    
    alt 저장 성공
        FS-->>FB: 성공
        FB-->>UI: True
        UI->>User: "피드백 감사합니다! 🙏" + 벼리 이미지
    else 저장 실패
        FS-->>FB: 에러
        FB->>FS: 에러 로그 저장
        FB-->>UI: False
        UI->>User: "일시적 오류, 잠시 후 다시 시도해주세요"
    end
```

### 관리자 대시보드 기능
```python
def show_admin_dashboard():
    """관리자 대시보드 (사이드바 비밀번호 보호)"""
    st.title("📊 벼리톡 관리자 대시보드")
    
    # 비밀번호 확인
    password = st.sidebar.text_input("관리자 비밀번호", type="password")
    if password != st.secrets.get("ADMIN_PASSWORD", "byeoli2024"):
        st.error("접근 권한이 없습니다.")
        return
    
    # 피드백 통계 (24시간 캐시)
    @st.cache_data(ttl=86400)  # 24시간 캐시
    def get_cached_stats():
        return feedback_manager.get_feedback_stats()
    
    stats = get_cached_stats()
    
    # 📊 통계 대시보드
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("총 피드백", stats['total'])
    with col2:
        st.metric("좋아요", stats['positive'])
    with col3:
        st.metric("싫어요", stats['negative'])
    with col4:
        st.metric("만족도", f"{stats['positive_rate']}%")
    
    # 📋 최근 피드백 목록
    st.subheader("최근 피드백")
    recent_feedbacks = feedback_manager.get_recent_feedbacks(20)
    
    for feedback in recent_feedbacks:
        with st.expander(f"{feedback['feedback_type']} - {feedback['timestamp']}"):
            st.write(f"**질문**: {feedback['user_query']}")
            st.write(f"**답변**: {feedback['bot_response'][:200]}...")
            if feedback.get('feedback_reason'):
                st.write(f"**사유**: {feedback['feedback_reason']}")
    
    # 🔍 피드백 검색
    st.subheader("피드백 검색")
    search_keyword = st.text_input("키워드 검색")
    if search_keyword:
        filtered_feedbacks = [
            f for f in recent_feedbacks 
            if search_keyword in f['user_query'] or search_keyword in f['bot_response']
        ]
        st.write(f"검색 결과: {len(filtered_feedbacks)}건")
        for feedback in filtered_feedbacks:
            st.write(f"- {feedback['feedback_type']}: {feedback['user_query']}")
    
    # ❌ 에러 로그
    st.subheader("에러 로그")
    error_logs = feedback_manager.get_error_logs(10)
    for error in error_logs:
        st.error(f"{error['error_type']}: {error['error_message']}")
    
    # 📥 CSV 다운로드
    if st.button("CSV 다운로드"):
        csv_data = feedback_manager.export_to_csv()
        st.download_button(
            label="피드백 데이터 다운로드",
            data=csv_data,
            file_name=f"byeoli_feedback_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
```

## 대화 맥락 관리

### 5턴 슬라이딩 윈도우 + 백그라운드 요약
```python
@dataclass
class Conversation:
    id: str
    turns: List[ConversationTurn]
    summary: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

# 처리 로직
1-5턴: 원본 대화 유지
6턴: [1-5턴 백그라운드 요약] + [6턴 새 시작]
7-10턴: 6턴부터 원본 대화 유지  
11턴: [6-10턴 백그라운드 요약] + [11턴 새 시작]
```

### 오류 처리 로직
```python
def add_turn(self, conv_id, user_msg, bot_response):
    message_id = str(uuid.uuid4())  # 🆕 피드백용 고유 ID
    conversation = self.get_conversation(conv_id)
    conversation.turns.append(new_turn)
    
    # 정상 케이스: 5턴마다 요약
    if len(conversation.turns) >= 5:
        self._start_background_summary(conv_id, conversation.turns.copy())
        conversation.turns = []
    
    # 오류 케이스: 10턴 누적시 강제 정리
    elif len(conversation.turns) >= 10:
        # 요약 실패가 계속되어 누적된 경우
        old_turns = conversation.turns[:-5]  # 앞의 5턴
        recent_turns = conversation.turns[-5:]  # 최근 5턴
        
        # 간단한 키워드 기반 요약으로 대체
        topics = [turn.user_message[:30] for turn in old_turns[-3:]]
        conversation.summary = f"이전 대화: {', '.join(topics)}에 대해 문의함"
        
        # 최근 5턴만 유지
        conversation.turns = recent_turns
        logger.warning(f"강제 정리 실행: {conv_id}")
    
    return message_id  # 🆕 UI에서 피드백 버튼 연결용
```

## 스트리밍 구현

### Streamlit 스트리밍 + 피드백 버튼
```python
def stream_response(self, conv_id: str, query: str):
    """실시간 스트리밍 응답"""
    # 1. 지시어 해소 및 검색 (비스트리밍)
    context = self.conversation_manager.get_context_for_llm(conv_id)
    expanded_query = self.conversation_manager.resolve_references(query, context)
    all_chunks = self._collect_chunks_from_all_handlers(expanded_query)
    response_type = self.conversation_manager.determine_response_type(all_chunks)
    
    # 2. 프롬프트 생성
    if response_type == "casual_chat":
        prompt = self._generate_casual_chat_prompt(query, context)
    elif response_type == "insufficient_info":
        # 스트리밍 불필요 (정적 응답)
        response = self._handle_insufficient_info(query)
        message_id = self.conversation_manager.add_turn(conv_id, query, response)
        yield response, message_id
        return
    elif response_type == "clarification":
        prompt = self._generate_clarification_prompt(query, all_chunks)
    else:
        prompt = self._generate_confident_answer_prompt(expanded_query, all_chunks, context)
    
    # 3. OpenAI 스트리밍 호출
    full_response = ""
    stream = self.openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        temperature=0.1
    )
    
    for chunk in stream:
        if chunk.choices[0].delta.content:
            token = chunk.choices[0].delta.content
            full_response += token
            yield token, None  # 스트리밍 중에는 message_id 없음
    
    # 4. 완료 후 대화 기록 저장 및 message_id 반환
    message_id = self.conversation_manager.add_turn(conv_id, query, full_response)
    yield "", message_id  # 빈 토큰과 함께 message_id 반환

# Streamlit 앱에서 사용
def display_streaming_response_with_feedback(conv_id, query):
    response_placeholder = st.empty()
    full_response = ""
    message_id = None
    
    # 스트리밍 출력
    for token, msg_id in base_handler.stream_response(conv_id, query):
        if token:
            full_response += token
            response_placeholder.markdown(full_response + "▌")
        if msg_id:
            message_id = msg_id
    
    response_placeholder.markdown(full_response)
    
    # 피드백 버튼 표시
    if message_id:
        render_feedback_buttons(conv_id, message_id, query, full_response)

def render_feedback_buttons(conv_id, message_id, user_query, bot_response):
    """피드백 버튼 렌더링 (중복 방지 포함)"""
    feedback_key = f"feedback_{message_id}"
    
    # 이미 피드백했는지 확인
    if st.session_state.get(feedback_key):
        st.success("피드백 감사합니다! 🙏")
        st.image("byeoli.png", width=100)
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("👍", key=f"pos_{message_id}", help="도움이 되었습니다"):
            save_feedback_and_show_thanks(conv_id, message_id, user_query, bot_response, "positive", None)
            st.session_state[feedback_key] = True
            st.rerun()
    
    with col2:
        if st.button("👎", key=f"neg_{message_id}", help="개선이 필요합니다"):
            # 사유 입력 영역 확장
            feedback_reason = st.text_area(
                "개선이 필요한 부분을 알려주세요 (선택사항)",
                key=f"reason_{message_id}",
                placeholder="예: 정보가 부정확해요, 더 자세한 설명이 필요해요"
            )
            if st.button("피드백 제출", key=f"submit_{message_id}"):
                save_feedback_and_show_thanks(conv_id, message_id, user_query, bot_response, "negative", feedback_reason)
                st.session_state[feedback_key] = True
                st.rerun()

def save_feedback_and_show_thanks(conv_id, message_id, user_query, bot_response, feedback_type, feedback_reason):
    """피드백 저장 및 감사 메시지 표시"""
    feedback_data = FeedbackData(
        conversation_id=conv_id,
        message_id=message_id,
        user_query=user_query,
        bot_response=bot_response,
        feedback_type=feedback_type,
        feedback_reason=feedback_reason
    )
    
    success = feedback_manager.save_feedback(feedback_data)
    
    if success:
        st.success("피드백 감사합니다! 🙏")
        st.image("byeoli.png", width=100)
        st.write("더 나은 서비스를 위해 소중한 의견 반영하겠습니다!")
    else:
        st.error("일시적 오류가 발생했습니다. 잠시 후 다시 시도해주세요.")
```

## 출처 및 연락처 관리

### 기본 동작
- 사용자에게 출처를 보여주지 않음
- 자연스러운 답변만 제공
- 사용자가 인사를 하거나 감사를 표하면 반갑게 응대

### 출처 요청 시
사용자가 "출처가 뭐야?", "담당 부서는?" 등을 물어보면:

```
해당 정보에 대한 자세한 문의는 다음 담당부서로 연락해 주세요:

📞 **담당부서 연락처**
• 인재개발지원과 총무담당: 055-254-2011
• 인재개발지원과 평가분석담당: 055-254-2021  
• 인재양성과 교육기획담당: 055-254-2051  
• 인재양성과 교육운영1담당: 055-254-2061
• 인재양성과 교육운영2담당: 055-254-2071
• 인재양성과 사이버담당: 055-254-2081

🌐 **홈페이지**: https://www.gyeongnam.go.kr/hrd

더 정확한 정보를 확인해 드릴 수 있습니다.
```

## 성능 최적화

### 병렬 처리 최적화
- **ThreadPoolExecutor**: 6개 핸들러 동시 실행
- **백그라운드 요약**: 사용자 응답 지연 없음  
- **타임아웃**: 핸들러당 1초, 전체 3초
- **부분 실패 허용**: 일부 핸들러 실패해도 나머지로 계속

### 응답 시간 목표
- **Chunk 수집**: ≤ 3초 (병렬)
- **지시어 해소**: ≤ 1초 (간단한 경우만)
- **LLM 스트리밍**: 첫 토큰 ≤ 1.5초
- **피드백 저장**: ≤ 2초 (Firestore)
- **전체 완료**: ≤ 15초

### 메모리 관리
- **벡터스토어**: 60MB (10MB × 6개) - 문제없음
- **대화 기록**: 5턴 + 요약만 유지 (최대 10턴)
- **피드백 캐시**: 관리자 대시보드 24시간 캐시
- **세션 상태**: 피드백 중복 방지용 플래그만 저장

## 확장성 고려사항

### 새로운 핸들러 추가
1. 새 도메인 데이터 준비
2. 새 핸들러 클래스 생성 (`search_chunks` 메서드 구현)
3. `BaseHandler`에 핸들러 등록
4. `config/thresholds.py`에 설정 추가

```python
# 새 핸들러 추가 예시
HANDLER_THRESHOLDS = {
    "satisfaction": 0.70,
    "general": 0.65,
    "cyber": 0.75,
    "menu": 0.60,
    "notice": 0.65,
    "publish": 0.70,
    "new_domain": 0.68  # 🆕 새 도메인 추가
}
```

### 피드백 시스템 확장
1. **고급 분석**: 감정 분석, 토픽 모델링
2. **자동 알림**: 부정 피드백 급증시 Slack/Email 알림
3. **A/B 테스트**: 응답 방식별 만족도 비교
4. **실시간 모니터링**: Grafana 대시보드 연동

### 설정 수정 편의성
```python
# config/thresholds.py - 관리자가 쉽게 수정 가능
COMMON_THRESHOLDS = {
    "casual_chat": 0.20,        # 일상 대화 임계값 (0.15~0.25 권장)
    "insufficient_info": 0.50   # 정보 부족 임계값 (0.45~0.55 권장)
}

HANDLER_THRESHOLDS = {
    "satisfaction": 0.70,  # 만족도: 정확성 중요 (0.65~0.75)
    "general": 0.65,       # 일반 정보: 관대 (0.60~0.70)
    "cyber": 0.75,         # 사이버교육: 엄격 (0.70~0.80)
    "menu": 0.60,          # 식단: 관대 (0.55~0.65)
    "notice": 0.65,        # 공지사항: 적당히 (0.60~0.70)
    "publish": 0.70        # 발행물: 정확히 (0.65~0.75)
}

# 🆕 피드백 시스템 설정
FEEDBACK_SETTINGS = {
    "enable_feedback": True,
    "require_reason_for_negative": False,  # 부정 피드백시 사유 필수 여부
    "admin_dashboard_cache_hours": 24,
    "max_recent_feedbacks": 50
}
```

### 성능 모니터링
```python
class PerformanceMonitor:
    def track_response_type_distribution(self):
        """응답 타입별 사용 빈도 추적"""
        return {
            "casual_chat": 15%,      # 일상 대화
            "insufficient_info": 20%, # 정보 부족
            "clarification": 25%,     # 되묻기
            "confident_answer": 40%   # 정상 답변
        }
    
    def track_clarification_success_rate(self):
        """되묻기 후 성공률 측정"""
        # 되묻기 → 사용자 재질문 → 정상 답변 비율
        return 0.78  # 78% 성공률
    
    def track_feedback_metrics(self):
        """피드백 관련 지표 추적"""
        return {
            "feedback_rate": 0.25,    # 전체 응답 중 피드백 비율
            "positive_rate": 0.82,    # 긍정 피드백 비율
            "avg_response_time": 2.3, # 평균 응답 시간 (초)
            "firestore_success_rate": 0.99  # Firestore 저장 성공률
        }
    
    def track_handler_performance(self):
        """핸들러별 응답 시간 및 품질"""
        return {
            "satisfaction": {"avg_time": 0.8, "avg_confidence": 0.82, "feedback_score": 4.2},
            "general": {"avg_time": 0.6, "avg_confidence": 0.75, "feedback_score": 4.0},
            "cyber": {"avg_time": 0.9, "avg_confidence": 0.78, "feedback_score": 4.1},
            "menu": {"avg_time": 0.5, "avg_confidence": 0.85, "feedback_score": 4.5},
            "notice": {"avg_time": 0.7, "avg_confidence": 0.73, "feedback_score": 3.8},
            "publish": {"avg_time": 0.8, "avg_confidence": 0.77, "feedback_score": 4.0}
        }
```

---

## 주요 파일 구조

```
streamlit_app/
├── app.py                          # 메인 Streamlit 앱 (대화형 UI + 스트리밍 + 피드백)
├── handlers/
│   ├── base_handler.py            # CentralOrchestrator (Confidence 분기)
│   ├── satisfaction_handler.py    # search_chunks만 담당  
│   ├── general_handler.py         # search_chunks만 담당
│   ├── notice_handler.py          # search_chunks만 담당
│   ├── cyber_handler.py           # search_chunks만 담당
│   ├── menu_handler.py            # search_chunks만 담당
│   └── publish_handler.py         # search_chunks만 담당
├── utils/
│   ├── conversation_manager.py    # 🔄 대화 관리 올인원 (message_id 추가)
│   ├── feedback_manager.py        # 🆕 Firestore 기반 피드백 관리
│   ├── index_manager.py           # 벡터스토어 관리 (싱글톤)
│   ├── contracts.py               # 🔄 데이터 클래스 정의 (FeedbackData 추가)
│   └── logging_utils.py           # 로깅 유틸
├── config/
│   ├── thresholds.py              # Confidence 설정값 + 피드백 설정
│   └── config.py                  # 🔄 기본 설정 (conversation_manager + 피드백 관련)
├── assets/                         # 🆕 정적 파일
│   └── byeoli.png                 # 벼리 캐릭터 이미지
├── vectorstores/                   # 벡터스토어 파일들 (GitHub 업로드)
│   ├── vectorstore_general/
│   ├── vectorstore_satisfaction/
│   ├── vectorstore_cyber/
│   ├── vectorstore_menu/
│   ├── vectorstore_notice/
│   └── vectorstore_publish/
└── requirements.txt               # 🔄 Firestore 의존성 추가
```

## 주요 변경사항

| 기능 | 변경 내용 |
|------|----------|
| `utils/router.py` | 🗑️ **완전 삭제** |
| `utils/context_manager.py` | 🗑️ **완전 삭제** (복잡한 기능들 제거) |
| `utils/conversation_manager.py` | 🔄 **수정** (message_id 추가, 피드백 연동) |
| `utils/feedback_manager.py` | 🆕 **신규 생성** (Firestore 피드백 시스템) |
| `config/thresholds.py` | ✅ **생성 완료** (설정값 관리) |
| `config/config.py` | 🔄 **대폭 수정** (conversation_manager + 피드백 설정) |
| `utils/contracts.py` | 🔄 **수정** (FeedbackData, ConversationTurn 확장) |
| `handlers/base_handler.py` | 🔄 **수정** (CentralOrchestrator + message_id 반환) |
| `handlers/*_handler.py` | ✅ **유지** (LLM 호출 제거, `search_chunks()` 메서드만) |
| `app.py` | 🔄 **대폭 수정** (피드백 UI + 관리자 대시보드) |
| `assets/byeoli.png` | 🆕 **신규 추가** (벼리 캐릭터 이미지) |
| `requirements.txt` | 🔄 **수정** (google-cloud-firestore 추가) |

## 핵심 혁신 기능

### 🚀 **인간 친화적 대화**
- **지시어 해소**: "그 과정" → "중견리더 과정"
- **맥락 유지**: 5턴 슬라이딩 윈도우 + 백그라운드 요약
- **자연스러운 대화**: 이전 대화 기반 연속적 응답

### 🎯 **Confidence 기반 4단계 지능형 분기**
- **일상 대화** (≤0.20): "벼리야 안녕" → 친근한 응답 + 서비스 소개
- **정보 부족** (0.20~0.50): 검색 실패 → 담당부서 연락처 제공
- **되묻기** (0.50~핸들러기준): 애매한 질문 → "혹시 이런 의미인가요?"
- **정상 답변** (핸들러기준 초과): 기존 RAG 방식

### 📝 **실시간 피드백 시스템** (🆕)
- **즉시 수집**: 👍👎 버튼으로 실시간 피드백
- **중복 방지**: 답변별 1회 피드백 제한
- **사유 수집**: 부정 피드백시 개선사항 수집 (선택사항)
- **Firestore 연동**: 안정적인 클라우드 저장
- **관리자 대시보드**: 실시간 통계 및 분석

### ⚡ **성능 최적화**
- **병렬 검색**: 6개 핸들러 동시 실행
- **백그라운드 요약**: Threading으로 응답 지연 없음
- **실시간 스트리밍**: 첫 토큰 1.5초 이내 출력
- **24시간 캐시**: 관리자 대시보드 성능 최적화

### 🔧 **관리 편의성**
- **설정 분리**: 임계값 쉽게 조정 가능 (thresholds.py)
- **핸들러별 설정**: 도메인 특성 반영 (만족도: 엄격, 식단: 관대)
- **실시간 모니터링**: 피드백 통계, 에러 로그, 성능 지표
- **CSV 내보내기**: 피드백 데이터 분석용 다운로드

---

## 실제 대화 시나리오 예시

### 시나리오 1: 자연스러운 대화 흐름 + 피드백
```
사용자: "2025년 중견리더 과정 만족도가 어때?"
벼리: "2025년 중견리더 과정 만족도는 종합 4.2점으로 우수한 편입니다. 기본역량 14.33%, 리더십역량 14.70%, 직무역량 24.64% 향상되었어요."
[👍👎 버튼 표시]

사용자: 👍 클릭
벼리: "피드백 감사합니다! 🙏 [벼리 이미지] 더 나은 서비스를 위해 소중한 의견 반영하겠습니다!"

사용자: "그 중에서 가장 높은 향상도를 보인 역량은?"  # 지시어 해소
벼리: "직무역량이 24.64%로 가장 높은 향상도를 보였습니다. 특히 기획력과 의사표현력 영역에서 큰 성과가 있었어요."
[👍👎 버튼 표시]

사용자: 👎 클릭
[사유 입력 영역 확장]
사용자: "더 구체적인 교과목별 분석이 필요해요" 입력 → 피드백 제출
벼리: "피드백 감사합니다! 🙏 [벼리 이미지] 더 나은 서비스를 위해 소중한 의견 반영하겠습니다!"
```

### 시나리오 2: 되묻기 기능 + 피드백
```
사용자: "교육 신청 어떻게 해?"  # 모호한 질문
벼리: "혹시 이런 의미로 질문하신 건가요?

1️⃣ 2025년 상반기 교육과정 신청 방법을 알고 싶으신가요?
2️⃣ 특정 교육과정(예: 리더십, 직무교육)의 신청 절차를 궁금해하시나요?
3️⃣ 온라인 신청 시스템 사용법을 알고 싶으신가요?

구체적으로 말씀해 주시면 정확한 안내를 해드릴게요!"
[👍👎 버튼 표시]

사용자: "2번이야. 리더십 교육 신청하고 싶어."
벼리: "리더십 교육 신청 방법을 안내해드릴게요! 현재 모집 중인 과정은..."
[👍👎 버튼 표시]
```

### 시나리오 3: 일상 대화 + 피드백
```
사용자: "벼리야 안녕!"
벼리: "안녕하세요! 벼리입니다 😊 오늘도 좋은 하루 보내고 계신가요? 무엇을 도와드릴까요?"
[👍👎 버튼 표시]

사용자: "너가 뭘 할 수 있어?"
벼리: "저는 경상남도인재개발원의 다양한 정보를 도와드릴 수 있어요!

📚 **교육과정 정보**: 리더십, 기본역량, 직무교육 과정 안내
📊 **만족도 분석**: 교육 성과 및 개선사항 정보
💻 **사이버교육**: 온라인 과정 안내 및 수강법
📢 **공지사항**: 최신 소식 및 중요 알림
🍽️ **구내식당**: 일일 메뉴 및 식단표
📖 **발행물**: 각종 자료 및 간행물 정보

궁금한 것이 있으시면 언제든 편하게 물어보세요!"
[👍👎 버튼 표시]
```

### 시나리오 4: 관리자 대시보드 사용
```
관리자: 사이드바에서 "관리자 비밀번호" 입력 → "byeoli2024"
[관리자 대시보드 화면 표시]

📊 통계:
- 총 피드백: 1,247건
- 좋아요: 1,089건 (87.3%)
- 싫어요: 158건 (12.7%)
- 만족도: 87.3%

📋 최근 피드백:
- 2024-12-20 15:30 | positive | "교육과정 정보가 정확해요"
- 2024-12-20 15:25 | negative | "사이버교육 안내가 부족해요" (사유: 링크가 작동하지 않음)
- 2024-12-20 15:20 | positive | "식단 정보 유용해요"

🔍 검색: "만족도" 입력 → 관련 피드백 3건 표시

❌ 에러 로그:
- firestore_connection_failed: Network timeout (1건)

📥 CSV 다운로드: byeoli_feedback_20241220.csv
```

---

## Dependencies (requirements.txt 업데이트)

```txt
# 기존 의존성
streamlit>=1.28.0
openai>=1.0.0
langchain>=0.1.0
langchain-openai>=0.0.5
faiss-cpu>=1.7.4
python-dotenv>=1.0.0
pandas>=2.0.0
numpy>=1.24.0

# 🆕 피드백 시스템 의존성
google-cloud-firestore>=2.13.0
google-auth>=2.23.0

# 🆕 UI 개선
pillow>=10.0.0  # 벼리 이미지 표시용

# 기타 유틸리티
uuid
threading
datetime
```

---

## 환경 변수 (Streamlit Secrets)

```toml
# .streamlit/secrets.toml
[OPENAI_API_KEY]
# OpenAI API 키

[FIRESTORE_KEY]
# Firestore 서비스 계정 JSON (전체 내용)
{
  "type": "service_account",
  "project_id": "byeoli-feedback",
  "private_key_id": "...",
  "private_key": "...",
  "client_email": "...",
  "client_id": "...",
  "auth_uri": "...",
  "token_uri": "...",
  "auth_provider_x509_cert_url": "...",
  "client_x509_cert_url": "..."
}

[ADMIN_PASSWORD]
"byeoli2024"  # 관리자 대시보드 비밀번호
```

---

## 배포 체크리스트

### **코드 구현 완료 항목**
- [x] `config/thresholds.py` ✅ 완료
- [ ] `config/config.py` 수정 (conversation_manager + 피드백 설정)
- [ ] `utils/contracts.py` 수정 (FeedbackData 클래스 추가)
- [ ] `utils/conversation_manager.py` 수정 (message_id 추가)
- [ ] `utils/feedback_manager.py` 신규 생성
- [ ] `handlers/base_handler.py` 수정 (message_id 반환)
- [ ] `app.py` 대폭 수정 (피드백 UI + 관리자 대시보드)
- [ ] `assets/byeoli.png` 추가
- [ ] `requirements.txt` 업데이트

### **배포 전 설정**
- [ ] Firestore 프로젝트 생성 및 설정
- [ ] 서비스 계정 키 생성
- [ ] Streamlit Secrets 설정
- [ ] 벼리 이미지 파일 업로드

### **테스트 항목**
- [ ] 기본 RAG 기능 동작 확인
- [ ] 4단계 분기 로직 테스트
- [ ] 피드백 버튼 및 저장 테스트
- [ ] 관리자 대시보드 접근 및 기능 테스트
- [ ] Firestore 연결 및 에러 처리 테스트
- [ ] 스트리밍 + 피드백 통합 테스트

---

이 새로운 아키텍처는 **인간 친화적 대화, Confidence 기반 지능형 분기, 성능 최적화, 실시간 피드백 시스템**을 모두 갖춘 차세대 RAG 챗봇 플랫폼입니다. 기존의 단순한 RAG 챗봇을 넘어서 진정한 **대화형 AI 어시스턴트 + 지속적 개선 시스템**으로 발전시키며, 사용자와 관리자 모두에게 탁월한 경험을 제공합니다.
