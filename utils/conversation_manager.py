# utils/conversation_manager.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 대화 관리자 v3.1
5턴 슬라이딩 윈도우 + 백그라운드 요약 + 지시어 해소 + Confidence 분기

핵심 기능:
- 대화 기록 관리 (5턴 슬라이딩 윈도우)
- 백그라운드 요약 (ThreadPoolExecutor)
- 지시어 해소 ("그것" → "중견리더 과정")
- Confidence 기반 4단계 분기 처리
- message_id 반환 (피드백 시스템 연동)

설계 원칙:
- Architecture.md 100% 준수
- config.py 완전 연동
- contracts.py 데이터 클래스 활용
- 군더더기 없는 아름다운 구조

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-18
"""

import uuid
import logging
import openai
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, Future
from threading import Lock
import atexit

from config.config import get_conversation_config, get_openai_config
from config.thresholds import COMMON_THRESHOLDS, HANDLER_THRESHOLDS
from utils.contracts import (
    Conversation, ConversationTurn, ResponseType, 
    ChunkResult, QueryRequest, HandlerResponse
)

# =============================================================================
# 로거 설정
# =============================================================================

logger = logging.getLogger(__name__)

# 한국 시간대 설정
KST = timezone(timedelta(hours=9))

# =============================================================================
# ConversationManager 클래스
# =============================================================================

class ConversationManager:
    """
    대화 관리 올인원 모듈
    
    주요 기능:
    - 5턴 슬라이딩 윈도우 관리
    - 백그라운드 요약 (ThreadPoolExecutor)
    - 지시어 해소 처리
    - Confidence 기반 4단계 분기
    - 피드백 시스템 연동 (message_id)
    """
    
    def __init__(self):
        """ConversationManager 초기화"""
        # 설정 로드
        self.config = get_conversation_config()
        self.openai_config = get_openai_config()
        
        # OpenAI 클라이언트 초기화
        self.openai_client = None
        if self.openai_config['api_key']:
            try:
                self.openai_client = openai.OpenAI(
                    api_key=self.openai_config['api_key'],
                    timeout=self.openai_config['timeout'],
                    max_retries=self.openai_config['max_retries']
                )
                logger.info("✅ OpenAI 클라이언트 초기화 성공")
            except Exception as e:
                logger.error(f"OpenAI 클라이언트 초기화 실패: {e}")
        
        # Confidence 임계값 로드
        self.common_thresholds = COMMON_THRESHOLDS
        self.handler_thresholds = HANDLER_THRESHOLDS
        
        # 대화 저장소
        self.conversations: Dict[str, Conversation] = {}
        self.conversations_lock = Lock()
        
        # 백그라운드 요약 ThreadPoolExecutor
        self.summary_executor = ThreadPoolExecutor(
            max_workers=2, 
            thread_name_prefix="summary_worker"
        )
        self.pending_summaries: List[Future] = []
        
        # 프로그램 종료시 안전한 정리
        atexit.register(self._cleanup_on_exit)
        
        logger.info(f"✅ ConversationManager 초기화 완료 (윈도우 크기: {self.config['window_size']}턴)")
    
    def get_conversation(self, conv_id: str) -> Conversation:
        """
        대화 세션 조회 (없으면 생성)
        
        Args:
            conv_id: 대화 ID
            
        Returns:
            Conversation: 대화 객체
        """
        with self.conversations_lock:
            if conv_id not in self.conversations:
                self.conversations[conv_id] = Conversation(
                    id=conv_id,
                    created_at=datetime.now(KST)
                )
                logger.info(f"새 대화 세션 생성: {conv_id}")
            
            return self.conversations[conv_id]
    
    def add_turn(self, conv_id: str, user_message: str, bot_response: str, **kwargs) -> str:
        """
        대화 턴 추가 + 5턴 체크 + 백그라운드 요약
        
        Args:
            conv_id: 대화 ID
            user_message: 사용자 메시지
            bot_response: 봇 응답
            **kwargs: 추가 메타데이터 (confidence, domain_used, response_type 등)
            
        Returns:
            str: message_id (피드백 연결용)
        """
        conversation = self.get_conversation(conv_id)
        
        # message_id 생성 (피드백 시스템 연동)
        message_id = str(uuid.uuid4())
        
        # 새 턴 생성
        new_turn = ConversationTurn(
            user_message=user_message,
            bot_response=bot_response,
            message_id=message_id,
            timestamp=datetime.now(KST),
            confidence=kwargs.get('confidence', 0.0),
            domain_used=kwargs.get('domain_used', []),
            response_type=kwargs.get('response_type'),
            feedback=None  # 나중에 피드백 받으면 연결
        )
        
        with self.conversations_lock:
            conversation.turns.append(new_turn)
            conversation.updated_at = datetime.now(KST)
            
            # 5턴 도달시 백그라운드 요약 시작
            if len(conversation.turns) >= self.config['window_size']:
                if self.config['use_background_summary']:
                    self._start_background_summary(conv_id, conversation.turns.copy())
                
                # 현재 턴들 초기화 (요약이 summary에 저장됨)
                conversation.turns = []
                logger.info(f"대화 {conv_id}: 5턴 완료, 백그라운드 요약 시작")
        
        logger.debug(f"대화 턴 추가: {conv_id}, message_id: {message_id}")
        return message_id
    
    def _start_background_summary(self, conv_id: str, turns: List[ConversationTurn]) -> None:
        """
        백그라운드에서 대화 요약 생성 (ThreadPoolExecutor)
        
        Args:
            conv_id: 대화 ID
            turns: 요약할 턴들 (복사본)
        """
        if not self.openai_client:
            logger.warning("OpenAI 클라이언트가 없어 요약을 건너뜁니다.")
            return
        
        try:
            # 백그라운드 작업 제출
            future = self.summary_executor.submit(
                self._generate_summary_background, 
                conv_id, 
                turns
            )
            
            # 완료된 작업들 정리
            self.pending_summaries = [f for f in self.pending_summaries if not f.done()]
            self.pending_summaries.append(future)
            
            logger.info(f"백그라운드 요약 작업 제출: {conv_id} ({len(turns)}턴)")
            
        except Exception as e:
            logger.error(f"백그라운드 요약 제출 실패: {e}")
    
    def _generate_summary_background(self, conv_id: str, turns: List[ConversationTurn]) -> None:
        """
        백그라운드에서 실행되는 요약 생성 함수
        
        Args:
            conv_id: 대화 ID
            turns: 요약할 턴들
        """
        try:
            # 대화 내용 정리
            conversation_text = "\n".join([
                f"사용자: {turn.user_message}\n벼리: {turn.bot_response}"
                for turn in turns
            ])
            
            # 요약 생성 프롬프트
            prompt = f"""
다음 대화를 {self.config['summary_max_length']}자 이내로 간단히 요약해주세요.
주요 키워드와 사용자의 관심사를 중심으로 정리하세요.

대화 내용:
{conversation_text}

요약:"""
            
            # OpenAI 호출
            response = self.openai_client.chat.completions.create(
                model=self.openai_config['model'],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.1,
                timeout=self.config['background_summary_timeout']
            )
            
            summary = response.choices[0].message.content.strip()
            
            # 요약 저장
            with self.conversations_lock:
                conversation = self.conversations.get(conv_id)
                if conversation:
                    # 기존 요약과 연결
                    if conversation.summary:
                        conversation.summary = f"{conversation.summary} | {summary}"
                    else:
                        conversation.summary = summary
                    
                    # 최대 길이 제한
                    if len(conversation.summary) > self.config['summary_max_length'] * 2:
                        conversation.summary = conversation.summary[-self.config['summary_max_length']:]
                    
                    conversation.updated_at = datetime.now(KST)
            
            logger.info(f"백그라운드 요약 완료: {conv_id}")
            
        except Exception as e:
            logger.error(f"백그라운드 요약 생성 실패 ({conv_id}): {e}")
    
    def resolve_references(self, query: str, recent_context: str) -> str:
        """
        지시어 해소: "그것" → "중견리더 과정"
        
        Args:
            query: 사용자 질문
            recent_context: 최근 대화 맥락
            
        Returns:
            str: 해소된 질문
        """
        # 지시어/대명사 목록
        pronouns = ['그것', '그거', '이것', '이거', '그', '이', '저것', '위의', '앞의', '해당', '그런', '이런']
        
        # 지시어가 없으면 원본 반환
        if not any(pronoun in query for pronoun in pronouns):
            return query
        
        # 최근 맥락이 없으면 원본 반환
        if not recent_context:
            logger.debug("지시어가 있지만 맥락이 없어 원본 질문 유지")
            return query
        
        # OpenAI 클라이언트가 없으면 원본 반환
        if not self.openai_client:
            logger.warning("OpenAI 클라이언트가 없어 지시어 해소 불가")
            return query
        
        try:
            # 지시어 해소 프롬프트
            prompt = f"""
이전 대화:
{recent_context}

현재 질문: {query}

현재 질문의 지시어나 대명사를 이전 대화의 구체적인 내용으로 바꿔주세요.
예시: "그 과정" → "중견리더 과정", "그것" → "만족도 조사"

해소된 질문만 답변하세요:"""
            
            # OpenAI 호출
            response = self.openai_client.chat.completions.create(
                model=self.openai_config['model'],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.config['reference_resolution_max_tokens'],
                temperature=0.1,
                timeout=self.config['reference_resolution_timeout']
            )
            
            resolved_query = response.choices[0].message.content.strip()
            
            # 결과 검증 (너무 길거나 이상하면 원본 사용)
            if len(resolved_query) > len(query) * 3 or not resolved_query:
                logger.warning("지시어 해소 결과가 이상하여 원본 사용")
                return query
            
            logger.info(f"지시어 해소: '{query}' → '{resolved_query}'")
            return resolved_query
            
        except Exception as e:
            logger.warning(f"지시어 해소 실패: {e}")
            return query
    
    def get_context_for_llm(self, conv_id: str) -> str:
        """
        LLM용 대화 맥락 생성 (이전 요약 + 현재 턴들)
        
        Args:
            conv_id: 대화 ID
            
        Returns:
            str: LLM용 대화 맥락
        """
        conversation = self.get_conversation(conv_id)
        context_parts = []
        
        # 이전 요약
        if conversation.summary:
            context_parts.append(f"[이전 대화 요약]: {conversation.summary}")
        
        # 현재 턴들 (최근 3턴만)
        recent_turns = conversation.turns[-3:] if len(conversation.turns) > 3 else conversation.turns
        for turn in recent_turns:
            context_parts.append(f"사용자: {turn.user_message}")
            context_parts.append(f"벼리: {turn.bot_response}")
        
        return "\n".join(context_parts)
    
    def get_recent_context_for_reference(self, conv_id: str) -> str:
        """
        지시어 해소용 최근 맥락 (최근 2턴)
        
        Args:
            conv_id: 대화 ID
            
        Returns:
            str: 지시어 해소용 맥락
        """
        conversation = self.get_conversation(conv_id)
        
        # 최근 2턴만 사용 (너무 길면 혼란)
        recent_turns = conversation.turns[-2:] if len(conversation.turns) > 2 else conversation.turns
        
        context_parts = []
        for turn in recent_turns:
            context_parts.append(f"사용자: {turn.user_message}")
            context_parts.append(f"벼리: {turn.bot_response}")
        
        return "\n".join(context_parts)
    
    def determine_response_type(self, chunks: List[ChunkResult]) -> ResponseType:
        """
        Confidence 기반 4단계 분기 결정
        
        Args:
            chunks: 검색된 청크 결과들
            
        Returns:
            ResponseType: 응답 타입
        """
        if not chunks:
            return ResponseType.CASUAL_CHAT
        
        # 최고 confidence chunk 찾기
        max_chunk = max(chunks, key=lambda x: x.confidence)
        max_confidence = max_chunk.confidence
        dominant_domain = max_chunk.domain
        
        # 4단계 분기 처리
        if max_confidence <= self.common_thresholds["casual_chat"]:  # ≤ 0.15
            return ResponseType.CASUAL_CHAT
        elif max_confidence <= self.common_thresholds["insufficient_info"]:  # ≤ 0.35
            return ResponseType.INSUFFICIENT_INFO
        elif max_confidence <= self.handler_thresholds.get(dominant_domain, 0.45):  # ≤ 핸들러별기준
            return ResponseType.CLARIFICATION
        else:  # > 핸들러별기준
            return ResponseType.CONFIDENT_ANSWER
    
    def get_conversation_stats(self, conv_id: str) -> Dict[str, Any]:
        """
        대화 통계 조회 (디버깅/모니터링용)
        
        Args:
            conv_id: 대화 ID
            
        Returns:
            Dict: 대화 통계
        """
        conversation = self.get_conversation(conv_id)
        
        return {
            'conversation_id': conv_id,
            'total_turns': len(conversation.turns),
            'has_summary': bool(conversation.summary),
            'summary_length': len(conversation.summary) if conversation.summary else 0,
            'created_at': conversation.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': conversation.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'pending_summaries': len(self.pending_summaries),
            'recent_domains': [
                turn.domain_used for turn in conversation.turns[-3:]
                if turn.domain_used
            ]
        }
    
    def clear_conversation(self, conv_id: str) -> bool:
        """
        대화 세션 삭제
        
        Args:
            conv_id: 대화 ID
            
        Returns:
            bool: 삭제 성공 여부
        """
        with self.conversations_lock:
            if conv_id in self.conversations:
                del self.conversations[conv_id]
                logger.info(f"대화 세션 삭제: {conv_id}")
                return True
            return False
    
    def _cleanup_on_exit(self) -> None:
        """
        프로그램 종료시 안전한 정리
        백그라운드 작업 완료 대기 + ThreadPoolExecutor 종료
        """
        try:
            logger.info("ConversationManager 정리 시작...")
            
            # 진행 중인 요약 작업들 완료 대기 (최대 10초)
            if self.pending_summaries:
                logger.info(f"백그라운드 요약 {len(self.pending_summaries)}개 완료 대기 중...")
                
                for future in self.pending_summaries:
                    try:
                        future.result(timeout=5)  # 각각 최대 5초 대기
                    except Exception as e:
                        logger.warning(f"백그라운드 요약 완료 대기 실패: {e}")
            
            # ThreadPoolExecutor 정리
            self.summary_executor.shutdown(wait=True, timeout=5)
            logger.info("✅ ConversationManager 정리 완료")
            
        except Exception as e:
            logger.error(f"ConversationManager 정리 중 오류: {e}")

# =============================================================================
# 전역 인스턴스 (싱글톤 패턴)
# =============================================================================

_conversation_manager: Optional[ConversationManager] = None

def get_conversation_manager() -> ConversationManager:
    """
    전역 ConversationManager 인스턴스 반환 (싱글톤)
    
    Returns:
        ConversationManager: 대화 관리자 인스턴스
    """
    global _conversation_manager
    if _conversation_manager is None:
        _conversation_manager = ConversationManager()
    return _conversation_manager

# =============================================================================
# 편의 함수들
# =============================================================================

def add_conversation_turn(
    conv_id: str,
    user_message: str,
    bot_response: str,
    confidence: float = 0.0,
    domain_used: List[str] = None,
    response_type: ResponseType = None
) -> str:
    """
    대화 턴 추가 편의 함수
    
    Returns:
        str: message_id (피드백 연결용)
    """
    manager = get_conversation_manager()
    return manager.add_turn(
        conv_id=conv_id,
        user_message=user_message,
        bot_response=bot_response,
        confidence=confidence,
        domain_used=domain_used or [],
        response_type=response_type
    )

def resolve_query_references(conv_id: str, query: str) -> str:
    """
    지시어 해소 편의 함수
    
    Returns:
        str: 해소된 쿼리
    """
    manager = get_conversation_manager()
    recent_context = manager.get_recent_context_for_reference(conv_id)
    return manager.resolve_references(query, recent_context)

def get_llm_context(conv_id: str) -> str:
    """
    LLM용 맥락 조회 편의 함수
    
    Returns:
        str: LLM용 대화 맥락
    """
    manager = get_conversation_manager()
    return manager.get_context_for_llm(conv_id)

def determine_response_strategy(chunks: List[ChunkResult]) -> ResponseType:
    """
    응답 전략 결정 편의 함수
    
    Returns:
        ResponseType: 응답 타입
    """
    manager = get_conversation_manager()
    return manager.determine_response_type(chunks)

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 대화 관리자 테스트 ===")
    
    try:
        # ConversationManager 초기화 테스트
        cm = ConversationManager()
        print(f"✅ ConversationManager 초기화: OpenAI 사용 가능 = {cm.openai_client is not None}")
        
        # 대화 세션 생성 테스트
        conv_id = "test_conv_123"
        conversation = cm.get_conversation(conv_id)
        print(f"✅ 대화 세션 생성: {conversation.id}")
        
        # 대화 턴 추가 테스트
        message_id = cm.add_turn(
            conv_id=conv_id,
            user_message="안녕하세요",
            bot_response="안녕하세요! 벼리입니다.",
            confidence=0.85,
            domain_used=["general"],
            response_type=ResponseType.CONFIDENT_ANSWER
        )
        print(f"✅ 대화 턴 추가: message_id = {message_id}")
        
        # 지시어 해소 테스트
        if cm.openai_client:
            resolved = cm.resolve_references("그 과정은 언제 시작해?", "중견리더 과정에 대해 문의했습니다.")
            print(f"✅ 지시어 해소 테스트: {resolved}")
        
        # Confidence 분기 테스트
        test_chunks = [
            ChunkResult(
                chunk=None,
                confidence=0.85,
                domain="satisfaction"
            )
        ]
        response_type = cm.determine_response_type(test_chunks)
        print(f"✅ Confidence 분기 테스트: {response_type}")
        
        # 통계 조회 테스트
        stats = cm.get_conversation_stats(conv_id)
        print(f"✅ 대화 통계: {stats}")
        
        # 편의 함수 테스트
        message_id2 = add_conversation_turn(
            conv_id, "테스트 질문", "테스트 답변", 0.75, ["general"]
        )
        print(f"✅ 편의 함수 테스트: {message_id2}")
        
        print("\n🎉 모든 테스트 통과!")
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
