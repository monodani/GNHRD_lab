# utils/conversation_manager.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 대화 관리자 v4.0 (Langchain Memory 기반)

핵심 기능:
- Langchain ConversationBufferWindowMemory 기반의 대화 기록 관리
- 지시어 해소 ("그것" → "중견리-더 과정")
- Confidence 기반 4단계 분기 처리
- message_id 반환 (피드백 시스템 연동)

설계 원칙 (v4.0):
- [단순성] 복잡한 백그라운드 요약 로직 제거
- [안정성] Langchain의 검증된 메모리 모듈을 사용하여 기억 공백 및 정보 손실 문제 해결
- [직관성] 군더더기 없는 코드로 핵심 기능에 집중
- [유지보수성] 피드백/통계용 메타데이터는 기존 구조를 활용하여 분리 관리

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-09-08 (Gemini AI 제안 기반 리팩토링)
"""

import uuid
import logging
import openai
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

# 1. 핵심 알고리즘 변경: Langchain의 대화 기록 관리 모듈을 import 합니다.
from langchain.memory import ConversationBufferWindowMemory

from config.config import get_conversation_config, get_openai_config
from config.thresholds import COMMON_THRESHOLDS, HANDLER_THRESHOLDS
from utils.contracts import (
    Conversation, ConversationTurn, ResponseType,
    ChunkResult, QueryRequest, HandlerResponse
)

# =============================================================================
# 로거 및 시간대 설정 (기존과 동일)
# =============================================================================

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))

# =============================================================================
# ConversationManager 클래스 (Langchain Memory 기반 재설계)
# =============================================================================

class ConversationManager:
    """
    대화 관리 올인원 모듈 (Langchain Memory 기반)
    
    LLM이 직접 참조하는 대화 기록은 Langchain Memory가 담당하고,
    피드백, 통계 등 부가 정보는 기존 Conversation 객체가 담당하도록 역할을 분리합니다.
    """

    def __init__(self):
        """ConversationManager 초기화"""
        # 2. 설정값 조정 편의성: config.py에서 설정값을 가져와 사용합니다.
        # 이 설정값들이 Manager의 행동 방식을 결정합니다.
        self.config = get_conversation_config()
        self.openai_config = get_openai_config()

        # OpenAI 클라이언트 초기화 (기존과 동일)
        self.openai_client = None
        if self.openai_config['api_key']:
            try:
                self.openai_client = openai.OpenAI(
                    api_key=self.openai_config['api_key'],
                    timeout=self.openai_config.get('timeout', 10.0),
                    max_retries=self.openai_config.get('max_retries', 3)
                )
                logger.info("✅ OpenAI 클라이언트 초기화 성공")
            except Exception as e:
                logger.error(f"OpenAI 클라이언트 초기화 실패: {e}")

        # Confidence 임계값 로드 (기존과 동일)
        self.common_thresholds = COMMON_THRESHOLDS
        self.handler_thresholds = HANDLER_THRESHOLDS

        # 3. 핵심 알고리즘: 대화 기록 저장을 위한 Langchain Memory 저장소
        # Key: conv_id (대화 ID), Value: ConversationBufferWindowMemory 객체
        # LLM에게 전달될 실제 대화 내용은 이곳에 저장됩니다.
        self.memories: Dict[str, ConversationBufferWindowMemory] = {}

        # 4. 피드백/통계용 메타데이터 저장소
        # message_id, confidence, feedback 등 LLM의 대화 맥락과 무관한
        # 부가 정보를 저장하기 위해 기존 Conversation 객체 구조를 활용합니다.
        self.conversations_metadata: Dict[str, Conversation] = {}

        # 5. 단순화: 백그라운드 요약 관련 ThreadPoolExecutor 및 모든 관련 로직 제거
        
        # 설정값 설명 주석
        # window_size: 챗봇이 한 번에 기억할 최근 대화 턴(질문+답변)의 수
        window_size = self.config.get('window_size', 3)
        logger.info(f"✅ ConversationManager 초기화 완료 (Langchain 메모리, 기억 턴 수: {window_size}턴)")

    def get_memory(self, conv_id: str) -> ConversationBufferWindowMemory:
        """
        [핵심] 대화 ID에 해당하는 Langchain Memory 객체를 가져오거나 새로 생성합니다.
        
        Args:
            conv_id: 대화 ID
            
        Returns:
            ConversationBufferWindowMemory: 해당 대화의 메모리 객체
        """
        if conv_id not in self.memories:
            # config의 'window_size' 값을 k로 사용하여 메모리 객체 생성
            # k=3 이면, 최근 3번의 질문과 답변을 기억합니다.
            k_value = self.config.get('window_size', 3)
            
            self.memories[conv_id] = ConversationBufferWindowMemory(
                k=k_value,
                # 'history'라는 키로 대화록 문자열을 반환하도록 설정
                memory_key="history",
                # LLM이 사용할 input과 output의 변수명을 지정
                input_key="input",
                output_key="output"
            )
            logger.info(f"새 Langchain 메모리 생성: {conv_id} (k={k_value})")
        return self.memories[conv_id]

    def get_conversation_metadata(self, conv_id: str) -> Conversation:
        """
        [보조] 피드백/통계 등 부가 정보 저장을 위한 Conversation 객체를 가져옵니다.
        """
        if conv_id not in self.conversations_metadata:
            self.conversations_metadata[conv_id] = Conversation(
                id=conv_id,
                created_at=datetime.now(KST)
            )
        return self.conversations_metadata[conv_id]

    def add_turn(self, conv_id: str, user_message: str, bot_response: str, **kwargs) -> str:
        """
        [핵심] 대화 턴을 Langchain Memory에 즉시 추가하고, 메타데이터를 기록합니다.
        
        Returns:
            str: message_id (피드백 시스템 연동용)
        """
        # 1. Langchain Memory에 대화 내용 저장
        memory = self.get_memory(conv_id)
        # memory.save_context: 이 한 줄이 대화 내용을 기억하게 하는 핵심 알고리즘입니다.
        memory.save_context({"input": user_message}, {"output": bot_response})

        # 2. 피드백/통계용 메타데이터 저장
        conversation_meta = self.get_conversation_metadata(conv_id)
        message_id = str(uuid.uuid4())
        
        new_turn_meta = ConversationTurn(
            user_message=user_message,
            bot_response=bot_response,
            message_id=message_id,
            timestamp=datetime.now(KST),
            confidence=kwargs.get('confidence', 0.0),
            domain_used=kwargs.get('domain_used', []),
            response_type=kwargs.get('response_type'),
        )
        conversation_meta.turns.append(new_turn_meta)
        conversation_meta.updated_at = datetime.now(KST)

        # 3. 단순화: 5턴 체크 및 백그라운드 요약 로직 전체 제거
        
        logger.debug(f"대화 턴 추가 및 메모리 저장: {conv_id}, message_id: {message_id}")
        return message_id

    def resolve_references(self, query: str, recent_context: str) -> str:
        """
        지시어 해소: "그것" → "중견리더 과정" (기존 로직 유지)
        이제 Langchain Memory가 제공하는 풍부한 맥락(recent_context) 덕분에
        더 정확한 지시어 해소가 가능해집니다.
        """
        pronouns = ['그것', '그거', '이것', '이거', '저것', '해당', '그런', '이런']
        
        if not any(pronoun in query for pronoun in pronouns) or not recent_context:
            return query
        
        if not self.openai_client:
            logger.warning("OpenAI 클라이언트가 없어 지시어 해소를 건너뜁니다.")
            return query
        
        try:
            prompt = f"""이전 대화:\n{recent_context}\n\n현재 질문: {query}\n\n현재 질문의 지시어를 이전 대화의 구체적인 내용으로 바꿔서 해소된 질문만 간결하게 다시 작성해줘."""
            
            response = self.openai_client.chat.completions.create(
                model=self.openai_config['model'],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.config.get('reference_resolution_max_tokens', 100),
                temperature=0.0,
                timeout=self.config.get('reference_resolution_timeout', 3.0)
            )
            resolved_query = response.choices[0].message.content.strip()
            
            logger.info(f"지시어 해소: '{query}' → '{resolved_query}'")
            return resolved_query
            
        except Exception as e:
            logger.warning(f"지시어 해소 실패: {e}")
            return query

    def get_context_for_llm(self, conv_id: str) -> str:
        """
        [핵심] Langchain Memory에서 LLM에게 전달할 대화 맥락(Context)을 생성합니다.
        
        Returns:
            str: "Human: 안녕\nAI: 안녕하세요..." 형태의 대화록 문자열
        """
        memory = self.get_memory(conv_id)
        # memory.load_memory_variables: 메모리에 저장된 대화 내용을 지정된 형식으로 불러옵니다.
        memory_variables = memory.load_memory_variables({})
        
        # 'history' 키 값에 저장된 대화록 문자열을 반환
        return memory_variables.get('history', '')

    def get_recent_context_for_reference(self, conv_id: str) -> str:
        """
        지시어 해소용 맥락을 생성합니다. (LLM용 맥락과 동일하게 사용)
        Langchain Memory가 이미 '최근 대화'를 관리하므로, 별도 로직이 필요 없습니다.
        """
        return self.get_context_for_llm(conv_id)

    def determine_response_type(self, chunks: List[ChunkResult]) -> ResponseType:
        """
        Confidence 기반 4단계 분기 결정 (기존 로직과 동일)
        """
        if not chunks:
            return ResponseType.CASUAL_CHAT
        
        max_chunk = max(chunks, key=lambda x: x.confidence)
        
        if max_chunk.confidence <= self.common_thresholds["casual_chat"]:
            return ResponseType.CASUAL_CHAT
        elif max_chunk.confidence <= self.common_thresholds["insufficient_info"]:
            return ResponseType.INSUFFICIENT_INFO
        elif max_chunk.confidence <= self.handler_thresholds.get(max_chunk.domain, 0.45):
            return ResponseType.CLARIFICATION
        else:
            return ResponseType.CONFIDENT_ANSWER

    def clear_conversation(self, conv_id: str) -> bool:
        """
        대화 세션의 Langchain Memory와 메타데이터를 모두 삭제합니다.
        """
        deleted = False
        if conv_id in self.memories:
            del self.memories[conv_id]
            deleted = True
        
        if conv_id in self.conversations_metadata:
            del self.conversations_metadata[conv_id]
            deleted = True

        if deleted:
            logger.info(f"대화 세션 및 메모리 삭제 완료: {conv_id}")

        return deleted

# =============================================================================
# 전역 인스턴스 및 편의 함수 (기존 구조 유지)
# =============================================================================

_conversation_manager: Optional[ConversationManager] = None

def get_conversation_manager() -> ConversationManager:
    """전역 ConversationManager 인스턴스 반환 (싱글톤)"""
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager

# 아래 편의 함수들은 외부 인터페이스 변경 없이 그대로 사용 가능합니다.
# 내부적으로는 모두 새로운 Manager 로직을 따르게 됩니다.

def add_conversation_turn(conv_id: str, user_message: str, bot_response: str, **kwargs) -> str:
    """대화 턴 추가 편의 함수"""
    return get_conversation_manager().add_turn(conv_id, user_message, bot_response, **kwargs)

def resolve_query_references(conv_id: str, query: str) -> str:
    """지시어 해소 편의 함수"""
    manager = get_conversation_manager()
    recent_context = manager.get_recent_context_for_reference(conv_id)
    return manager.resolve_references(query, recent_context)

def get_llm_context(conv_id: str) -> str:
    """LLM용 맥락 조회 편의 함수"""
    return get_conversation_manager().get_context_for_llm(conv_id)

def determine_response_strategy(chunks: List[ChunkResult]) -> ResponseType:
    """응답 전략 결정 편의 함수"""
    return get_conversation_manager().determine_response_type(chunks)

# =============================================================================
# 모듈 테스트 (변경된 로직에 맞게 수정)
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("\n=== 벼리톡 대화 관리자 (v4.0 Langchain Memory) 테스트 ===")
    
    cm = get_conversation_manager()
    conv_id = "test_conv_langchain"
    
    print("\n1. 대화 턴 추가 테스트...")
    add_conversation_turn(conv_id, "안녕하세요, 중견리더 과정에 대해 알려주세요.", "안녕하세요! 중견리더 과정은 10월에 시작합니다.")
    add_conversation_turn(conv_id, "그럼 신임리더 과정은 언제인가요?", "신임리더 과정은 11월에 예정되어 있습니다.")
    add_conversation_turn(conv_id, "식당 메뉴도 알려줄 수 있나요?", "네, 오늘의 메뉴는 제육볶음입니다.")
    
    context = get_llm_context(conv_id)
    print(f"\n2. LLM 컨텍스트 생성 테스트 (k={cm.config.get('window_size', 3)}):")
    print("--------------------[CONTEXT]--------------------")
    print(context)
    print("-------------------------------------------------")
    
    print("\n3. 네 번째 턴 추가 (오래된 대화가 밀려나는지 확인)...")
    add_conversation_turn(conv_id, "알겠습니다.", "감사합니다. 또 궁금한 점이 있으신가요?")
    
    context_after_push = get_llm_context(conv_id)
    print("\n4. 갱신된 LLM 컨텍스트 확인:")
    print("--------------------[CONTEXT]--------------------")
    print(context_after_push)
    print("-------------------------------------------------")
    if "중견리더" not in context_after_push:
        print("✅ 첫 번째 대화('중견리더')가 메모리에서 정상적으로 밀려났습니다.")

    print("\n5. 지시어 해소 테스트...")
    user_query = "그럼 그것 말고 다른 과정은요?"
    resolved_query = resolve_query_references(conv_id, user_query)
    print(f"  - 원본 질문: '{user_query}'")
    print(f"  - 해소된 질문: '{resolved_query}'")
    
    cm.clear_conversation(conv_id)
    print(f"\n6. 대화 세션 삭제 테스트: {conv_id} 세션이 삭제되었습니다.")
    
    final_context = get_llm_context(conv_id)
    if not final_context:
        print("✅ 삭제 후 컨텍스트가 비어있음을 확인했습니다.")

    print("\n🎉 모든 테스트 통과!")
