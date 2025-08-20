# handlers/base_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - CentralOrchestrator v4.0
Architecture.md 기반 통합 핸들러 시스템

핵심 기능:
- 6개 핸들러 병렬 실행 → chunk 수집 → 통합 LLM 호출
- Confidence 기반 4단계 분기 (일상대화/정보부족/되묻기/정상답변)
- conversation_manager 연동 (지시어 해소 + 대화 맥락)
- message_id 반환 (피드백 시스템 연동)
- 실패한 핸들러 제외하고 진행 (Graceful degradation)

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-20
"""

# ================================================================
# 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
# ================================================================

# 4단계 분기 임계값 설정
CASUAL_CHAT_THRESHOLD = 0.15        # 일상 대화 기준
INSUFFICIENT_INFO_THRESHOLD = 0.35   # 정보 부족 기준
# 참고: 핸들러별 기준은 config/thresholds.py의 HANDLER_THRESHOLDS 사용

# 병렬 처리 성능 설정
MAX_HANDLER_WORKERS = 6              # 핸들러 병렬 처리 워커 수
HANDLER_TIMEOUT_SECONDS = 10         # 핸들러 응답 제한 시간 (초)
MAX_CHUNKS_PER_DOMAIN = 3            # 도메인당 최대 청크 수
TOP_CHUNKS_FOR_LLM = 5               # LLM에 전달할 최대 청크 수
MAX_TOTAL_CHUNKS = 10                # 전체 보관할 최대 청크 수

# OpenAI LLM 설정
LLM_MODEL = "gpt-4o-mini"            # 사용할 LLM 모델
LLM_MAX_TOKENS = 1000                # 최대 토큰 수  
LLM_TEMPERATURE = 0.1                # 창의성 조절 (0=일관성, 1=창의성)
LLM_TIMEOUT_SECONDS = 30             # LLM 응답 제한 시간

# 벼리 AI 성격 및 톤앤매너 설정
BYEOLI_PERSONALITY = "정중하고 친근한 전문 AI 어시스턴트"
RESPONSE_TONE = "전문적이면서도 친근한"
INCLUDE_EMOJIS = True                # 이모지 사용 여부
FORMAL_ENDING = True                 # 정중한 마무리 ("~습니다", "~해주세요")

# 중복 제거 설정
CONTENT_HASH_LENGTH = 100            # 중복 판단을 위한 내용 해시 길이
ENABLE_DEDUPLICATION = True          # 중복 제거 활성화

# ================================================================
# 분기별 프롬프트 템플릿 설정
# ================================================================

# 일상 대화 템플릿
CASUAL_CHAT_TEMPLATE = """안녕하세요! 벼리입니다 😊

저는 경상남도인재개발원의 AI 어시스턴트로, 다음과 같은 도움을 드릴 수 있어요:

📚 **교육과정 정보**: 교육과정 안내
📊 **만족도 정보**: 교육과정 및 교과목 만족도
💻 **사이버교육**: 온라인 과정 안내 및 수강 방법
📢 **공지사항**: 최신 소식 및 중요 알림
🍽️ **구내식당**: 일일 메뉴 및 식단표
📖 **발행물**: 각종 자료 및 간행물 정보

궁금한 것이 있으시면 언제든 편하게 물어보세요! 🙋‍♀️"""

# 정보 부족 템플릿
INSUFFICIENT_INFO_TEMPLATE = """죄송합니다. '{query}'에 대한 구체적인 정보를 찾을 수 없습니다.

아래 담당부서로 직접 문의해 주시면 정확한 안내를 받으실 수 있습니다:

📞 **담당부서 연락처**

{department_list}

💡 **이용 팁**: 구체적인 키워드(교육과정명, 공지 제목 등)로 다시 질문해 주시면 더 정확한 답변을 드릴 수 있어요!"""

# 되묻기 템플릿
CLARIFICATION_TEMPLATE = """혹시 이런 의미로 질문하신 건가요?

{options}

💡 더 구체적으로 말씀해 주시면 정확한 안내를 해드릴게요!"""

# 통합 프롬프트 템플릿  
UNIFIED_PROMPT_TEMPLATE = """당신은 "벼리(영문명: Byeoli)"입니다. 경상남도인재개발원의 전문 AI 어시스턴트로서 직원들과 도민들의 질문에 정확하고 친절하게 답변합니다.

=== 📋 사용자 질문 ===
{query}

=== 📚 참고 자료 ===
{references}
{context_section}

=== 🎯 답변 지침 ===
1. **정확성 우선**: 제공된 참고 자료의 정보만 사용하세요
2. **친근한 톤**: "~습니다", "~해주세요" 등 정중하고 친근한 말투 사용  
3. **구조화된 답변**: 중요한 정보는 불릿 포인트나 번호로 정리
4. **담당부서 안내**: 관련 담당부서와 연락처 정보 포함
5. **추가 도움**: 더 궁금한 점이 있으면 언제든 질문하라는 안내 추가

=== 📞 주요 담당부서 ===
- 교육기획담당: 055-254-2051
- 교육운영1담당: 055-254-2061(신규 임용(후보)자 과정 등)
- 교육운영2담당: 055-254-2071(중견리더 과정 등)
- 사이버담당: 055-254-2081(온라인 강의 관련)
- 평가분석담당: 055-254-2021
- 총무담당: 055-254-2011
- 구내식당: 055-254-2096

답변을 시작하세요:"""

# 에러 응답 템플릿
ERROR_RESPONSE_TEMPLATE = """죄송합니다. '{query}' 처리 중 일시적인 오류가 발생했습니다.

잠시 후 다시 시도해 주시거나, 아래 담당부서로 직접 문의해 주세요:

📞 **경상남도인재개발원 대표번호**: 055-254-2051

기술적 문제가 지속되면 시스템 관리자에게 문의하시기 바랍니다."""

# ================================================================
# 도메인별 선택지 매핑 (되묻기용)
# ================================================================

DOMAIN_OPTION_MAPPING = {
    "satisfaction": "📊 교육과정 만족도나 성과 분석 정보",
    "cyber": "💻 사이버교육(온라인 교육) 수강 관련",
    "publish": "📖 공식 발행물이나 계획서/평가서 자료",
    "general": "📋 학칙, 규정, 담당자 연락처 정보",
    "notice": "📢 최신 공지사항이나 중요 알림",
    "menu": "🍽️ 구내식당 메뉴나 식단표"
}

# 기본 선택지 (도메인 매칭이 없을 때)
DEFAULT_CLARIFICATION_OPTIONS = [
    "📚 교육과정 정보 (리더십, 직무교육 등)",
    "📊 교육 만족도 및 성과 분석",
    "💻 사이버교육 수강 방법",
    "📢 최신 공지사항",
    "🍽️ 구내식당 식단표"
]

# ================================================================
# 도메인 표시명 매핑
# ================================================================

DOMAIN_DISPLAY_NAMES = {
    "satisfaction": "📊 만족도 조사",
    "cyber": "💻 사이버교육", 
    "publish": "📖 발행물",
    "general": "📋 일반정보",
    "notice": "📢 공지사항",
    "menu": "🍽️ 구내식당"
}

# ================================================================
# 🔧 파인튜닝 설정 구역 끝
# ================================================================

import logging
import time
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.config import get_openai_config
from config.thresholds import COMMON_THRESHOLDS, HANDLER_THRESHOLDS, ALL_DEPARTMENT_CONTACTS
from utils.contracts import QueryRequest, HandlerResponse, ChunkResult, ResponseType
from utils.conversation_manager import get_conversation_manager
from utils.feedback_manager import get_feedback_manager

# 개별 핸들러 임포트
from handlers.satisfaction_handler import SatisfactionHandler
from handlers.cyber_handler import CyberHandler
from handlers.publish_handler import PublishHandler
from handlers.general_handler import GeneralHandler
from handlers.notice_handler import NoticeHandler
from handlers.menu_handler import MenuHandler

# OpenAI 클라이언트
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# =============================================================================
# 로거 설정
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# CentralOrchestrator 클래스
# =============================================================================

class CentralOrchestrator:
    """
    Architecture v4.0 핵심: 6개 핸들러 통합 관리자
    
    처리 흐름:
    1. 지시어 해소 (conversation_manager)
    2. 6개 핸들러 병렬 실행
    3. Chunk 수집 및 통합
    4. Confidence 기반 4단계 분기
    5. 통합 LLM 호출 (1회만)
    6. message_id 반환 (피드백 연동)
    """
    
    def __init__(self):
        """CentralOrchestrator 초기화"""
        # OpenAI 설정
        self.openai_config = get_openai_config()
        self.openai_client = None
        
        if OPENAI_AVAILABLE and self.openai_config['api_key']:
            try:
                self.openai_client = openai.OpenAI(
                    api_key=self.openai_config['api_key'],
                    timeout=LLM_TIMEOUT_SECONDS,
                    max_retries=self.openai_config['max_retries']
                )
                logger.info("✅ OpenAI 클라이언트 초기화 성공")
            except Exception as e:
                logger.error(f"OpenAI 클라이언트 초기화 실패: {e}")
        
        # 대화 및 피드백 매니저
        self.conversation_manager = get_conversation_manager()
        self.feedback_manager = get_feedback_manager()
        
        # 6개 핸들러 초기화
        self.handlers = self._initialize_handlers()
        
        # ThreadPoolExecutor (병렬 처리용)
        self.executor = ThreadPoolExecutor(
            max_workers=MAX_HANDLER_WORKERS, 
            thread_name_prefix="handler_worker"
        )
        
        logger.info(f"✅ CentralOrchestrator 초기화 완료: {len(self.handlers)}개 핸들러")
    
    def _initialize_handlers(self) -> Dict[str, Any]:
        """6개 핸들러 초기화 (실패한 핸들러 제외)"""
        handlers = {}
        handler_classes = {
            "satisfaction": SatisfactionHandler,
            "cyber": CyberHandler,
            "publish": PublishHandler,
            "general": GeneralHandler,
            "notice": NoticeHandler,
            "menu": MenuHandler
        }
        
        for domain, handler_class in handler_classes.items():
            try:
                handler = handler_class()
                handlers[domain] = handler
                logger.info(f"✅ {domain} 핸들러 초기화 성공")
            except Exception as e:
                logger.error(f"❌ {domain} 핸들러 초기화 실패: {e}")
                # 실패한 핸들러는 제외하고 진행
        
        return handlers
    
    def handle(self, request: QueryRequest) -> HandlerResponse:
        """
        통합 핸들러 처리 메인 로직
        
        Args:
            request: 쿼리 요청
            
        Returns:
            HandlerResponse: 통합 응답 (message_id 포함)
        """
        start_time = time.time()
        
        try:
            # 1. 쿼리 추출 및 대화 ID 처리
            query = getattr(request, 'query', '') or getattr(request, 'text', '')
            conversation_id = getattr(request, 'conversation_id', None) or f"conv_{uuid.uuid4().hex[:8]}"
            
            logger.info(f"🚀 통합 처리 시작: '{query}' (대화: {conversation_id})")
            
            # 2. 지시어 해소 (conversation_manager)
            resolved_query = self.conversation_manager.resolve_references(query, 
                self.conversation_manager.get_recent_context_for_reference(conversation_id))
            
            if resolved_query != query:
                logger.info(f"🔧 지시어 해소: '{query}' → '{resolved_query}'")
            
            # 3. 6개 핸들러 병렬 실행
            all_chunks = self._execute_handlers_parallel(resolved_query)
            
            # 4. Confidence 기반 4단계 분기 결정
            response_type = self.conversation_manager.determine_response_type(all_chunks)
            
            # 5. 분기별 응답 생성
            if response_type == ResponseType.CASUAL_CHAT:
                response = self._handle_casual_chat(query, conversation_id)
            elif response_type == ResponseType.INSUFFICIENT_INFO:
                response = self._handle_insufficient_info(query)
            elif response_type == ResponseType.CLARIFICATION:
                response = self._handle_clarification(query, all_chunks, conversation_id)
            else:  # CONFIDENT_ANSWER
                response = self._handle_confident_answer(resolved_query, all_chunks, conversation_id)
            
            # 6. 대화 기록 저장 (message_id 반환)
            message_id = self.conversation_manager.add_turn(
                conv_id=conversation_id,
                user_message=query,
                bot_response=response.answer,
                confidence=response.confidence,
                domain_used=[chunk.domain for chunk in all_chunks[:MAX_CHUNKS_PER_DOMAIN]],
                response_type=response_type
            )
            
            # 7. 최종 응답 설정
            response.message_id = message_id
            response.response_type = response_type
            response.elapsed_ms = (time.time() - start_time) * 1000
            
            logger.info(f"✅ 통합 처리 완료: {response_type.value} ({response.elapsed_ms:.1f}ms)")
            return response
            
        except Exception as e:
            logger.error(f"❌ 통합 처리 실패: {e}")
            return self._create_error_response(query, str(e))
    
    def _execute_handlers_parallel(self, query: str) -> List[ChunkResult]:
        """6개 핸들러 병렬 실행 및 chunk 수집"""
        all_chunks = []
        
        # 병렬 작업 제출
        future_to_domain = {}
        for domain, handler in self.handlers.items():
            future = self.executor.submit(self._safe_handler_search, domain, handler, query)
            future_to_domain[future] = domain
        
        # 결과 수집 (실패한 핸들러 제외)
        for future in as_completed(future_to_domain.keys(), timeout=HANDLER_TIMEOUT_SECONDS):
            domain = future_to_domain[future]
            try:
                chunks = future.result()
                # 도메인당 최대 청크 수 제한
                limited_chunks = chunks[:MAX_CHUNKS_PER_DOMAIN]
                all_chunks.extend(limited_chunks)
                logger.debug(f"✅ {domain}: {len(limited_chunks)}개 청크 수집")
            except Exception as e:
                logger.warning(f"⚠️ {domain} 핸들러 실패: {e}")
                # 실패한 핸들러는 제외하고 진행
        
        # Confidence 순 정렬 및 중복 제거
        if ENABLE_DEDUPLICATION:
            all_chunks = self._deduplicate_and_sort_chunks(all_chunks)
        else:
            all_chunks.sort(key=lambda x: x.confidence, reverse=True)
            all_chunks = all_chunks[:MAX_TOTAL_CHUNKS]
        
        logger.info(f"🔍 병렬 검색 완료: {len(all_chunks)}개 청크 수집")
        return all_chunks
    
    def _safe_handler_search(self, domain: str, handler: Any, query: str) -> List[ChunkResult]:
        """안전한 핸들러 검색 (예외 처리 포함)"""
        try:
            return handler.search_chunks(query)
        except Exception as e:
            logger.warning(f"⚠️ {domain} 검색 실패: {e}")
            return []
    
    def _deduplicate_and_sort_chunks(self, chunks: List[ChunkResult]) -> List[ChunkResult]:
        """청크 중복 제거 및 Confidence 순 정렬"""
        # 간단한 중복 제거 (내용 기반)
        seen_content = set()
        unique_chunks = []
        
        for chunk in chunks:
            content_hash = hash(chunk.chunk.content[:CONTENT_HASH_LENGTH])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_chunks.append(chunk)
        
        # Confidence 순 정렬
        unique_chunks.sort(key=lambda x: x.confidence, reverse=True)
        
        return unique_chunks[:MAX_TOTAL_CHUNKS]
    
    def _handle_casual_chat(self, query: str, conversation_id: str) -> HandlerResponse:
        """일상 대화 처리 (≤ CASUAL_CHAT_THRESHOLD)"""
        answer = CASUAL_CHAT_TEMPLATE

        return HandlerResponse(
            answer=answer,
            confidence=0.10,
            domain="unified",
            success=True,
            chunk_count=0,
            metadata={"response_type": "casual_chat"}
        )
    
    def _handle_insufficient_info(self, query: str) -> HandlerResponse:
        """정보 부족 처리 (CASUAL_CHAT_THRESHOLD ~ INSUFFICIENT_INFO_THRESHOLD)"""
        # 담당부서 목록 생성
        department_list = []
        for i, dept_info in enumerate(ALL_DEPARTMENT_CONTACTS, 1):
            department_list.append(f"**{i}. {dept_info['department']}**")
            department_list.append(f"   📞 {dept_info['phone']}")
            department_list.append(f"   📋 {dept_info['description']}\n")
        
        department_text = "\n".join(department_list)
        
        answer = INSUFFICIENT_INFO_TEMPLATE.format(
            query=query,
            department_list=department_text
        )

        return HandlerResponse(
            answer=answer,
            confidence=0.25,
            domain="unified", 
            success=True,
            chunk_count=0,
            metadata={"response_type": "insufficient_info"}
        )
    
    def _handle_clarification(self, query: str, chunks: List[ChunkResult], conversation_id: str) -> HandlerResponse:
        """되묻기 처리 (INSUFFICIENT_INFO_THRESHOLD ~ 핸들러별 기준)"""
        # 상위 청크들로부터 의도 추론
        top_chunks = chunks[:MAX_CHUNKS_PER_DOMAIN]
        domains_found = list(set([chunk.domain for chunk in top_chunks]))
        
        # 도메인별 선택지 생성
        options = []
        for domain in domains_found:
            if domain in DOMAIN_OPTION_MAPPING:
                options.append(DOMAIN_OPTION_MAPPING[domain])
        
        # 선택지가 없으면 기본 선택지 사용
        if not options:
            options = DEFAULT_CLARIFICATION_OPTIONS
        
        # 선택지 포맷팅
        formatted_options = []
        for i, option in enumerate(options, 1):
            formatted_options.append(f"{i}️⃣ {option}")
        
        answer = CLARIFICATION_TEMPLATE.format(
            options="\n".join(formatted_options)
        )

        # 최고 confidence 계산
        max_confidence = max([chunk.confidence for chunk in top_chunks]) if top_chunks else 0.37
        
        return HandlerResponse(
            answer=answer,
            confidence=max_confidence,
            domain="unified",
            success=True,
            chunk_count=len(top_chunks),
            metadata={
                "response_type": "clarification",
                "domains_suggested": domains_found
            }
        )
    
    def _handle_confident_answer(self, query: str, chunks: List[ChunkResult], conversation_id: str) -> HandlerResponse:
        """정상 RAG 답변 처리 (핸들러별 기준 초과)"""
        if not self.openai_client:
            return HandlerResponse(
                answer="죄송합니다. 현재 AI 응답 서비스를 사용할 수 없습니다.",
                confidence=0.0,
                domain="unified",
                success=False
            )
        
        # 상위 청크 사용
        top_chunks = chunks[:TOP_CHUNKS_FOR_LLM]
        
        # 대화 맥락 조회
        conversation_context = self.conversation_manager.get_context_for_llm(conversation_id)
        
        # 통합 프롬프트 생성
        prompt = self._create_unified_prompt(query, top_chunks, conversation_context)
        
        try:
            # OpenAI 호출
            response = self.openai_client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE,
                timeout=LLM_TIMEOUT_SECONDS
            )
            
            answer = response.choices[0].message.content.strip()
            
            # 최고 confidence 계산
            max_confidence = max([chunk.confidence for chunk in top_chunks]) if top_chunks else 0.5
            
            return HandlerResponse(
                answer=answer,
                confidence=max_confidence,
                domain="unified",
                success=True,
                chunk_count=len(top_chunks),
                metadata={
                    "response_type": "confident_answer",
                    "domains_used": list(set([chunk.domain for chunk in top_chunks]))
                }
            )
            
        except Exception as e:
            logger.error(f"OpenAI 호출 실패: {e}")
            return self._create_error_response(query, f"AI 응답 생성 실패: {str(e)}")
    
    def _create_unified_prompt(self, query: str, chunks: List[ChunkResult], conversation_context: str) -> str:
        """통합 프롬프트 생성"""
        # 청크들을 도메인별로 정리
        domain_chunks = {}
        for chunk in chunks:
            domain = chunk.domain
            if domain not in domain_chunks:
                domain_chunks[domain] = []
            domain_chunks[domain].append(chunk)
        
        # 참고 자료 섹션 생성
        reference_sections = []
        for domain, domain_chunk_list in domain_chunks.items():
            section_name = DOMAIN_DISPLAY_NAMES.get(domain, domain)
            reference_sections.append(f"\n=== {section_name} ===")
            
            for i, chunk in enumerate(domain_chunk_list, 1):
                content = chunk.chunk.content[:300] + "..." if len(chunk.chunk.content) > 300 else chunk.chunk.content
                confidence = f"(신뢰도: {chunk.confidence:.2f})"
                reference_sections.append(f"{i}. {content} {confidence}")
        
        references = "\n".join(reference_sections)
        
        # 대화 맥락 추가
        context_section = ""
        if conversation_context.strip():
            context_section = f"\n\n=== 📝 이전 대화 맥락 ===\n{conversation_context}"
        
        # 통합 프롬프트 생성
        prompt = UNIFIED_PROMPT_TEMPLATE.format(
            query=query,
            references=references,
            context_section=context_section
        )

        return prompt
    
    def _create_error_response(self, query: str, error_msg: str) -> HandlerResponse:
        """에러 응답 생성"""
        answer = ERROR_RESPONSE_TEMPLATE.format(query=query)

        return HandlerResponse(
            answer=answer,
            confidence=0.0,
            domain="unified",
            success=False,
            chunk_count=0,
            metadata={
                "response_type": "error",
                "error_message": error_msg
            }
        )

# =============================================================================
# 전역 인스턴스 (싱글톤 패턴)
# =============================================================================

_central_orchestrator: Optional[CentralOrchestrator] = None

def get_central_orchestrator() -> CentralOrchestrator:
    """
    전역 CentralOrchestrator 인스턴스 반환 (싱글톤)
    
    Returns:
        CentralOrchestrator: 통합 핸들러 인스턴스
    """
    global _central_orchestrator
    if _central_orchestrator is None:
        _central_orchestrator = CentralOrchestrator()
    return _central_orchestrator

# =============================================================================
# 편의 함수들
# =============================================================================

def process_query(query: str, conversation_id: Optional[str] = None) -> HandlerResponse:
    """
    쿼리 처리 편의 함수
    
    Args:
        query: 사용자 질문
        conversation_id: 대화 ID (선택사항)
        
    Returns:
        HandlerResponse: 통합 응답
    """
    orchestrator = get_central_orchestrator()
    
    request = QueryRequest(
        query=query,
        conversation_id=conversation_id,
        follow_up=False
    )
    
    return orchestrator.handle(request)

# =============================================================================
# 파인튜닝 헬퍼 함수들
# =============================================================================

def get_current_settings() -> Dict[str, Any]:
    """
    현재 파인튜닝 설정값들 반환 (디버깅/모니터링용)
    
    Returns:
        Dict: 현재 설정값들
    """
    return {
        "thresholds": {
            "casual_chat": CASUAL_CHAT_THRESHOLD,
            "insufficient_info": INSUFFICIENT_INFO_THRESHOLD
        },
        "performance": {
            "max_workers": MAX_HANDLER_WORKERS,
            "handler_timeout": HANDLER_TIMEOUT_SECONDS,
            "max_chunks_per_domain": MAX_CHUNKS_PER_DOMAIN,
            "top_chunks_for_llm": TOP_CHUNKS_FOR_LLM,
            "max_total_chunks": MAX_TOTAL_CHUNKS
        },
        "llm": {
            "model": LLM_MODEL,
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": LLM_TEMPERATURE,
            "timeout": LLM_TIMEOUT_SECONDS
        },
        "persona": {
            "personality": BYEOLI_PERSONALITY,
            "tone": RESPONSE_TONE,
            "include_emojis": INCLUDE_EMOJIS,
            "formal_ending": FORMAL_ENDING
        },
        "deduplication": {
            "content_hash_length": CONTENT_HASH_LENGTH,
            "enable_deduplication": ENABLE_DEDUPLICATION
        }
    }

def update_settings(**kwargs) -> Dict[str, Any]:
    """
    파인튜닝 설정값 동적 업데이트 (개발/테스트용)
    
    Args:
        **kwargs: 업데이트할 설정값들
        
    Returns:
        Dict: 업데이트된 설정값들
    """
    global CASUAL_CHAT_THRESHOLD, INSUFFICIENT_INFO_THRESHOLD
    global MAX_HANDLER_WORKERS, HANDLER_TIMEOUT_SECONDS
    global MAX_CHUNKS_PER_DOMAIN, TOP_CHUNKS_FOR_LLM, MAX_TOTAL_CHUNKS
    global LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_TIMEOUT_SECONDS
    global CONTENT_HASH_LENGTH, ENABLE_DEDUPLICATION
    
    # 임계값 업데이트
    if 'casual_chat_threshold' in kwargs:
        CASUAL_CHAT_THRESHOLD = kwargs['casual_chat_threshold']
    if 'insufficient_info_threshold' in kwargs:
        INSUFFICIENT_INFO_THRESHOLD = kwargs['insufficient_info_threshold']
    
    # 성능 설정 업데이트
    if 'max_workers' in kwargs:
        MAX_HANDLER_WORKERS = kwargs['max_workers']
    if 'handler_timeout' in kwargs:
        HANDLER_TIMEOUT_SECONDS = kwargs['handler_timeout']
    if 'max_chunks_per_domain' in kwargs:
        MAX_CHUNKS_PER_DOMAIN = kwargs['max_chunks_per_domain']
    if 'top_chunks_for_llm' in kwargs:
        TOP_CHUNKS_FOR_LLM = kwargs['top_chunks_for_llm']
    if 'max_total_chunks' in kwargs:
        MAX_TOTAL_CHUNKS = kwargs['max_total_chunks']
    
    # LLM 설정 업데이트
    if 'llm_model' in kwargs:
        LLM_MODEL = kwargs['llm_model']
    if 'llm_max_tokens' in kwargs:
        LLM_MAX_TOKENS = kwargs['llm_max_tokens']
    if 'llm_temperature' in kwargs:
        LLM_TEMPERATURE = kwargs['llm_temperature']
    if 'llm_timeout' in kwargs:
        LLM_TIMEOUT_SECONDS = kwargs['llm_timeout']
    
    # 중복 제거 설정 업데이트
    if 'content_hash_length' in kwargs:
        CONTENT_HASH_LENGTH = kwargs['content_hash_length']
    if 'enable_deduplication' in kwargs:
        ENABLE_DEDUPLICATION = kwargs['enable_deduplication']
    
    logger.info(f"파인튜닝 설정 업데이트 완료: {list(kwargs.keys())}")
    return get_current_settings()

def validate_settings() -> Dict[str, Any]:
    """
    현재 설정값들의 유효성 검증
    
    Returns:
        Dict: 검증 결과 (errors, warnings, status)
    """
    errors = []
    warnings = []
    
    # 임계값 검증
    if not (0.0 <= CASUAL_CHAT_THRESHOLD <= 1.0):
        errors.append(f"CASUAL_CHAT_THRESHOLD({CASUAL_CHAT_THRESHOLD})는 0.0~1.0 범위여야 함")
    
    if not (0.0 <= INSUFFICIENT_INFO_THRESHOLD <= 1.0):
        errors.append(f"INSUFFICIENT_INFO_THRESHOLD({INSUFFICIENT_INFO_THRESHOLD})는 0.0~1.0 범위여야 함")
    
    if CASUAL_CHAT_THRESHOLD >= INSUFFICIENT_INFO_THRESHOLD:
        errors.append(f"CASUAL_CHAT_THRESHOLD({CASUAL_CHAT_THRESHOLD})는 INSUFFICIENT_INFO_THRESHOLD({INSUFFICIENT_INFO_THRESHOLD})보다 작아야 함")
    
    # 성능 설정 검증
    if MAX_HANDLER_WORKERS < 1 or MAX_HANDLER_WORKERS > 10:
        warnings.append(f"MAX_HANDLER_WORKERS({MAX_HANDLER_WORKERS})는 1~10 범위 권장")
    
    if HANDLER_TIMEOUT_SECONDS < 5 or HANDLER_TIMEOUT_SECONDS > 60:
        warnings.append(f"HANDLER_TIMEOUT_SECONDS({HANDLER_TIMEOUT_SECONDS})는 5~60초 범위 권장")
    
    if MAX_CHUNKS_PER_DOMAIN < 1 or MAX_CHUNKS_PER_DOMAIN > 10:
        warnings.append(f"MAX_CHUNKS_PER_DOMAIN({MAX_CHUNKS_PER_DOMAIN})는 1~10 범위 권장")
    
    if TOP_CHUNKS_FOR_LLM < 1 or TOP_CHUNKS_FOR_LLM > 20:
        warnings.append(f"TOP_CHUNKS_FOR_LLM({TOP_CHUNKS_FOR_LLM})는 1~20 범위 권장")
    
    # LLM 설정 검증
    if LLM_MAX_TOKENS < 100 or LLM_MAX_TOKENS > 4000:
        warnings.append(f"LLM_MAX_TOKENS({LLM_MAX_TOKENS})는 100~4000 범위 권장")
    
    if not (0.0 <= LLM_TEMPERATURE <= 2.0):
        warnings.append(f"LLM_TEMPERATURE({LLM_TEMPERATURE})는 0.0~2.0 범위 권장")
    
    if LLM_TIMEOUT_SECONDS < 10 or LLM_TIMEOUT_SECONDS > 120:
        warnings.append(f"LLM_TIMEOUT_SECONDS({LLM_TIMEOUT_SECONDS})는 10~120초 범위 권장")
    
    # 중복 제거 설정 검증
    if CONTENT_HASH_LENGTH < 50 or CONTENT_HASH_LENGTH > 500:
        warnings.append(f"CONTENT_HASH_LENGTH({CONTENT_HASH_LENGTH})는 50~500 범위 권장")
    
    # 상태 결정
    if errors:
        status = "ERROR"
    elif warnings:
        status = "WARNING"
    else:
        status = "OK"
    
    return {
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "total_issues": len(errors) + len(warnings)
    }

def print_settings_summary():
    """설정값 요약 출력 (개발/디버깅용)"""
    print("\n" + "="*70)
    print("🔧 벼리톡 CentralOrchestrator 파인튜닝 설정 v4.0")
    print("="*70)
    
    print(f"\n📊 4단계 분기 임계값:")
    print(f"  • 일상 대화: ≤ {CASUAL_CHAT_THRESHOLD}")
    print(f"  • 정보 부족: {CASUAL_CHAT_THRESHOLD} ~ {INSUFFICIENT_INFO_THRESHOLD}")
    print(f"  • 되묻기: {INSUFFICIENT_INFO_THRESHOLD} ~ 핸들러별 기준")
    print(f"  • 정상 답변: 핸들러별 기준 초과")
    
    print(f"\n⚡ 병렬 처리 성능:")
    print(f"  • 워커 수: {MAX_HANDLER_WORKERS}개")
    print(f"  • 핸들러 타임아웃: {HANDLER_TIMEOUT_SECONDS}초")
    print(f"  • 도메인당 최대 청크: {MAX_CHUNKS_PER_DOMAIN}개")
    print(f"  • LLM 전달 청크: {TOP_CHUNKS_FOR_LLM}개")
    print(f"  • 전체 최대 청크: {MAX_TOTAL_CHUNKS}개")
    
    print(f"\n🤖 LLM 설정:")
    print(f"  • 모델: {LLM_MODEL}")
    print(f"  • 최대 토큰: {LLM_MAX_TOKENS}")
    print(f"  • 창의성: {LLM_TEMPERATURE}")
    print(f"  • 타임아웃: {LLM_TIMEOUT_SECONDS}초")
    
    print(f"\n🎭 벼리 성격:")
    print(f"  • 성격: {BYEOLI_PERSONALITY}")
    print(f"  • 톤앤매너: {RESPONSE_TONE}")
    print(f"  • 이모지 사용: {'✅' if INCLUDE_EMOJIS else '❌'}")
    print(f"  • 정중한 마무리: {'✅' if FORMAL_ENDING else '❌'}")
    
    print(f"\n🔄 중복 제거:")
    print(f"  • 활성화: {'✅' if ENABLE_DEDUPLICATION else '❌'}")
    print(f"  • 해시 길이: {CONTENT_HASH_LENGTH}자")
    
    # 설정 검증 결과
    validation = validate_settings()
    status_emoji = {"OK": "✅", "WARNING": "⚠️", "ERROR": "❌"}
    print(f"\n📋 설정 검증: {status_emoji[validation['status']]} {validation['status']}")
    
    if validation['errors']:
        print(f"  🚨 오류 {len(validation['errors'])}개:")
        for error in validation['errors']:
            print(f"    - {error}")
    
    if validation['warnings']:
        print(f"  ⚠️ 경고 {len(validation['warnings'])}개:")
        for warning in validation['warnings']:
            print(f"    - {warning}")
    
    print("="*70)

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 CentralOrchestrator 테스트 ===")
    
    try:
        # 설정 요약 출력
        print_settings_summary()
        
        # CentralOrchestrator 초기화 테스트
        orchestrator = CentralOrchestrator()
        print(f"\n✅ CentralOrchestrator 초기화: {len(orchestrator.handlers)}개 핸들러")
        
        # 테스트 쿼리들 (4단계 분기 테스트)
        test_queries = [
            "안녕!",                              # 일상대화
            "벼리야 뭐해?",                        # 일상대화  
            "경남 산업 현황 분석해줘",              # 정보부족
            "교육 관련 문의",                      # 되묻기
            "중견리더 과정 만족도는?",             # 정상답변
            "오늘 점심 메뉴 뭐야?"                 # 정상답변
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n--- 테스트 {i}: {query} ---")
            
            try:
                response = process_query(query, f"test_conv_{i}")
                print(f"응답 타입: {response.metadata.get('response_type', 'unknown')}")
                print(f"Confidence: {response.confidence:.3f}")
                print(f"Message ID: {response.message_id}")
                print(f"청크 개수: {response.chunk_count}")
                print(f"소요시간: {response.elapsed_ms:.1f}ms")
                print(f"답변: {response.answer[:200]}...")
                
            except Exception as e:
                print(f"❌ 테스트 {i} 실패: {e}")
        
        # 파인튜닝 함수 테스트
        print(f"\n--- 파인튜닝 함수 테스트 ---")
        
        # 현재 설정 조회
        current_settings = get_current_settings()
        print(f"✅ 현재 설정 조회: {len(current_settings)}개 카테고리")
        
        # 설정 업데이트 테스트
        updated_settings = update_settings(
            casual_chat_threshold=0.12,
            max_chunks_per_domain=4
        )
        print(f"✅ 설정 업데이트: casual_chat_threshold={updated_settings['thresholds']['casual_chat']}")
        
        # 설정 검증 테스트
        validation_result = validate_settings()
        print(f"✅ 설정 검증: {validation_result['status']} ({validation_result['total_issues']}개 이슈)")
        
        print("\n🎉 모든 테스트 완료!")
        
    except Exception as e:
        print(f"\n❌ CentralOrchestrator 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
