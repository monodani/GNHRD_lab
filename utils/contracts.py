# utils/contracts.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 데이터 계약 정의 v3.1
Architecture v3.1 + 코랩 호환성 + 피드백 시스템

설계 원칙:
- Architecture.md 기준 우선 (TextChunk.content 등)
- 코랩 base_handler.py 호환성 보장
- dataclass 중심 (일관성)
- Pydantic은 기존 호환성만
- 새 아키텍처: conversation_manager + feedback_manager 지원

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-18
"""

import uuid
from typing import Optional, List, Dict, Any, Union, Literal
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

# =============================================================================
# Enum 클래스들 (공통 사용)
# =============================================================================

class MessageRole(str, Enum):
    """메시지 역할 정의"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class HandlerType(str, Enum):
    """핸들러 타입 정의"""
    SATISFACTION = "satisfaction"
    GENERAL = "general"
    PUBLISH = "publish"
    CYBER = "cyber"
    MENU = "menu"
    NOTICE = "notice"
    FALLBACK = "fallback"

class FeedbackType(str, Enum):
    """피드백 타입 정의"""
    POSITIVE = "positive"
    NEGATIVE = "negative"

class ResponseType(str, Enum):
    """응답 타입 정의 (4단계 분기)"""
    CASUAL_CHAT = "casual_chat"
    INSUFFICIENT_INFO = "insufficient_info"
    CLARIFICATION = "clarification"
    CONFIDENT_ANSWER = "confident_answer"

# =============================================================================
# 🟢 dataclass 영역 (코랩 호환 + Architecture.md 기준)
# =============================================================================

@dataclass
class TextChunk:
    """텍스트 청크 (Architecture.md 기준)"""
    content: str  # Architecture.md 기준 (코랩에서는 text였음)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 코랩 호환성을 위한 별칭 속성
    @property
    def text(self) -> str:
        """코랩 호환성: text 속성으로도 접근 가능"""
        return self.content
    
    @text.setter
    def text(self, value: str):
        """코랩 호환성: text 속성으로도 설정 가능"""
        self.content = value

@dataclass 
class ChunkResult:
    """핸들러가 반환하는 청크 결과 (코랩 호환)"""
    chunk: TextChunk
    confidence: float  # 절대적 유사도 기반 (0.0-1.0)
    domain: str
    search_method: str = "faiss"
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class QueryRequest:
    """쿼리 요청 (코랩 호환)"""
    query: str
    follow_up: bool = False
    # 🆕 새 아키텍처 지원
    conversation_id: Optional[str] = None
    context: Optional[str] = None

@dataclass
class HandlerResponse:
    """최종 응답 (코랩 호환 + 피드백 연동)"""
    answer: str
    confidence: float
    domain: str = "unified"
    success: bool = True
    chunk_count: int = 0
    elapsed_ms: float = 0.0
    # 🆕 피드백 시스템 연동
    message_id: Optional[str] = field(default_factory=lambda: str(uuid.uuid4()))
    response_type: Optional[ResponseType] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

# =============================================================================
# 🟢 dataclass 영역 (새 아키텍처 - 피드백 시스템)
# =============================================================================

@dataclass
class FeedbackData:
    """피드백 데이터 (Firestore 저장용)"""
    conversation_id: str
    message_id: str
    user_query: str
    bot_response: str
    feedback_type: FeedbackType  # "positive" | "negative"
    feedback_reason: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)  # 한국시간
    
    def to_dict(self) -> Dict[str, Any]:
        """Firestore 저장을 위한 딕셔너리 변환"""
        return {
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
            "user_query": self.user_query,
            "bot_response": self.bot_response,
            "feedback_type": self.feedback_type.value if isinstance(self.feedback_type, FeedbackType) else self.feedback_type,
            "feedback_reason": self.feedback_reason,
            "timestamp": self.timestamp
        }

@dataclass
class ConversationTurn:
    """대화 턴 (conversation_manager 전용)"""
    user_message: str
    bot_response: str
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)  # 한국시간
    confidence: float = 0.0
    domain_used: List[str] = field(default_factory=list)
    response_type: Optional[ResponseType] = None
    feedback: Optional[FeedbackData] = None

@dataclass
class Conversation:
    """대화 세션 (conversation_manager 전용)"""
    id: str
    turns: List[ConversationTurn] = field(default_factory=list)
    summary: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def add_turn(self, user_message: str, bot_response: str, **kwargs) -> str:
        """대화 턴 추가"""
        turn = ConversationTurn(
            user_message=user_message,
            bot_response=bot_response,
            timestamp=datetime.now(),
            **kwargs
        )
        self.turns.append(turn)
        self.updated_at = datetime.now()
        return turn.message_id
    
    def get_recent_turns(self, count: int = 5) -> List[ConversationTurn]:
        """최근 N개 턴 반환"""
        return self.turns[-count:] if len(self.turns) >= count else self.turns

# =============================================================================
# 🟠 Pydantic 영역 (기존 호환성 유지)
# =============================================================================

class ChatTurn(BaseModel):
    """기존 채팅 턴 (호환성 유지)"""
    model_config = ConfigDict(extra='allow')
    
    role: MessageRole
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def to_conversation_turn(self, bot_response: str = "") -> ConversationTurn:
        """새 ConversationTurn으로 변환"""
        if self.role == MessageRole.USER:
            return ConversationTurn(
                user_message=self.content,
                bot_response=bot_response,
                timestamp=self.timestamp
            )
        else:
            return ConversationTurn(
                user_message="",
                bot_response=self.content,
                timestamp=self.timestamp
            )

class ConversationContext(BaseModel):
    """기존 대화 컨텍스트 (호환성 유지)"""
    model_config = ConfigDict(extra='allow')
    
    session_id: str
    turns: List[ChatTurn] = Field(default_factory=list)
    entities: Dict[str, List[str]] = Field(default_factory=dict)
    current_topic: Optional[str] = None
    summary: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # 기존 코드 호환성
    @property
    def recent_messages(self) -> List[ChatTurn]:
        """turns의 별칭 (기존 코드 호환성)"""
        return self.turns
    
    @recent_messages.setter
    def recent_messages(self, value: List[ChatTurn]):
        """turns 설정 (기존 코드 호환성)"""
        self.turns = value
    
    def add_message(self, role, content, **kwargs):
        """메시지 추가 메소드 (기존 호환성)"""
        if isinstance(role, str):
            role = MessageRole(role)
        
        new_turn = ChatTurn(
            role=role,
            content=content, 
            timestamp=datetime.now(),
            metadata=kwargs
        )
        self.turns.append(new_turn)
        self.updated_at = datetime.now()
        
        # 최근 6개 턴만 유지
        if len(self.turns) > 6:
            self.turns = self.turns[-6:]
    
    def to_conversation(self) -> Conversation:
        """새 Conversation 객체로 변환"""
        conversation = Conversation(
            id=self.session_id,
            summary=self.summary or "",
            created_at=self.created_at,
            updated_at=self.updated_at
        )
        
        # ChatTurn들을 ConversationTurn으로 변환
        for i in range(0, len(self.turns), 2):
            user_turn = self.turns[i] if i < len(self.turns) else None
            bot_turn = self.turns[i+1] if i+1 < len(self.turns) else None
            
            if user_turn and user_turn.role == MessageRole.USER:
                conversation.add_turn(
                    user_message=user_turn.content,
                    bot_response=bot_turn.content if bot_turn else "",
                    timestamp=user_turn.timestamp
                )
        
        return conversation

class ErrorResponse(BaseModel):
    """오류 응답 (API 검증 필요)"""
    model_config = ConfigDict(extra='allow')
    
    error_type: str
    error_message: str
    domain: Optional[str] = None
    query: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)
    suggestions: List[str] = Field(default_factory=list)

# =============================================================================
# 유틸리티 클래스들 (dataclass)
# =============================================================================

@dataclass
class Citation:
    """인용 정보"""
    source_id: str
    text: str
    relevance_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SearchResult:
    """검색 결과"""
    text: str
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_id: Optional[str] = None

@dataclass
class DomainConfig:
    """도메인 설정"""
    name: str
    description: str
    confidence_threshold: float = 0.45
    max_results: int = 5

@dataclass
class PerformanceMetrics:
    """성능 지표"""
    total_time: float = 0.0
    retrieval_time: float = 0.0
    generation_time: float = 0.0
    documents_retrieved: int = 0
    confidence_score: float = 0.0
    cache_hit: bool = False
    timestamp: datetime = field(default_factory=datetime.now)

# =============================================================================
# 헬퍼 함수들
# =============================================================================

def create_error_response(
    domain: str,
    error: Exception,
    query: Optional[str] = None
) -> HandlerResponse:
    """에러 응답 생성 헬퍼"""
    return HandlerResponse(
        answer=f"죄송합니다. 처리 중 오류가 발생했습니다: {str(error)}",
        confidence=0.0,
        domain=domain,
        success=False,
        metadata={"error_type": type(error).__name__, "query": query}
    )

def create_success_response(
    domain: str,
    answer: str,
    confidence: float,
    chunk_count: int = 0,
    elapsed_ms: float = 0.0,
    response_type: Optional[ResponseType] = None
) -> HandlerResponse:
    """성공 응답 생성 헬퍼"""
    return HandlerResponse(
        answer=answer,
        confidence=confidence,
        domain=domain,
        success=True,
        chunk_count=chunk_count,
        elapsed_ms=elapsed_ms,
        response_type=response_type
    )

def create_feedback_data(
    conversation_id: str,
    message_id: str,
    user_query: str,
    bot_response: str,
    feedback_type: Union[str, FeedbackType],
    feedback_reason: Optional[str] = None
) -> FeedbackData:
    """피드백 데이터 생성 헬퍼"""
    if isinstance(feedback_type, str):
        feedback_type = FeedbackType(feedback_type)
    
    return FeedbackData(
        conversation_id=conversation_id,
        message_id=message_id,
        user_query=user_query,
        bot_response=bot_response,
        feedback_type=feedback_type,
        feedback_reason=feedback_reason
    )

# =============================================================================
# 타입 별칭 (편의성)
# =============================================================================

# 대화 관련
ConversationId = str
MessageId = str
UserId = str

# 응답 관련  
ConfidenceScore = float
Domain = str

# 피드백 관련
FeedbackId = str

# =============================================================================
# 검증 함수들
# =============================================================================

def validate_confidence(confidence: float) -> bool:
    """Confidence 값 검증 (0.0-1.0)"""
    return 0.0 <= confidence <= 1.0

def validate_message_id(message_id: str) -> bool:
    """Message ID 형식 검증 (UUID)"""
    try:
        uuid.UUID(message_id)
        return True
    except ValueError:
        return False

def validate_feedback_type(feedback_type: str) -> bool:
    """피드백 타입 검증"""
    try:
        FeedbackType(feedback_type)
        return True
    except ValueError:
        return False

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 contracts.py 테스트 ===")
    
    # TextChunk 테스트 (코랩 호환성)
    chunk = TextChunk(content="테스트 내용")
    print(f"✅ TextChunk.content: {chunk.content}")
    print(f"✅ TextChunk.text (호환성): {chunk.text}")
    
    # ChunkResult 테스트
    chunk_result = ChunkResult(
        chunk=chunk,
        confidence=0.85,
        domain="satisfaction"
    )
    print(f"✅ ChunkResult: {chunk_result.domain}, confidence={chunk_result.confidence}")
    
    # FeedbackData 테스트
    feedback = create_feedback_data(
        conversation_id="conv_123",
        message_id="msg_456", 
        user_query="테스트 질문",
        bot_response="테스트 답변",
        feedback_type="positive"
    )
    print(f"✅ FeedbackData: {feedback.feedback_type}")
    
    # Conversation 테스트
    conversation = Conversation(id="conv_123")
    message_id = conversation.add_turn("안녕하세요", "안녕하세요! 벼리입니다.")
    print(f"✅ Conversation: {len(conversation.turns)}개 턴, message_id={message_id}")
    
    # 호환성 테스트
    old_context = ConversationContext(session_id="test_123")
    old_context.add_message("user", "테스트 메시지")
    new_conversation = old_context.to_conversation()
    print(f"✅ 호환성: 기존 → 새 아키텍처 변환 성공")
    
    # 검증 함수 테스트
    print(f"✅ Confidence 검증: {validate_confidence(0.85)}")
    print(f"✅ Message ID 검증: {validate_message_id(message_id)}")
    print(f"✅ Feedback 타입 검증: {validate_feedback_type('positive')}")
    
    print("\n🎉 모든 테스트 통과!")
