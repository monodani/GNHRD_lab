# handlers/base_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - CentralOrchestrator v5.1
개별 핸들러 v5.1 호환 간소화 버전

핵심 기능만:
- 6개 핸들러 병렬 실행 → chunk 수집
- confidence 순 정렬 (정규화 없이 직접 비교)
- 4단계 분기 처리
- 통합 LLM 호출 (1회)
- message_id 반환 (피드백 연동)

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-31
"""

# ================================================================
# 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
# ================================================================

# 4단계 분기 임계값
CASUAL_CHAT_THRESHOLD = 0.15        # 일상 대화 기준
INSUFFICIENT_INFO_THRESHOLD = 0.35   # 정보 부족 기준

# 병렬 처리 설정
MAX_HANDLER_WORKERS = 6              # 병렬 워커 수
HANDLER_TIMEOUT_SECONDS = 10         # 핸들러 타임아웃
MAX_CHUNKS_PER_DOMAIN = 3            # 도메인당 최대 청크
TOP_CHUNKS_FOR_LLM = 5               # LLM 전달 청크 수

# 중복 제거 설정
CONTENT_HASH_LENGTH = 100            # 중복 판단 해시 길이
ENABLE_DEDUPLICATION = True          # 중복 제거 활성화

# LLM 설정
LLM_MODEL = "gpt-4o-mini"
LLM_MAX_TOKENS = 1000
LLM_TEMPERATURE = 0.1
LLM_TIMEOUT_SECONDS = 30

# ================================================================
# 템플릿 설정
# ================================================================

CASUAL_CHAT_TEMPLATE = """안녕하세요! 벼리입니다 😊

저는 경상남도인재개발원의 AI 어시스턴트로, 다음과 같은 도움을 드릴 수 있어요:

📚 **교육과정 정보**: 교육과정 안내
📊 **만족도 정보**: 교육과정 및 교과목 만족도
💻 **사이버교육**: 온라인 과정 안내 및 수강 방법
📢 **공지사항**: 최신 소식 및 중요 알림
🍽️ **구내식당**: 일일 메뉴 및 식단표
📖 **발행물**: 각종 자료 및 간행물 정보

궁금한 것이 있으시면 언제든 편하게 물어보세요! 🙋‍♀️"""

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

답변을 시작하세요:"""

# ================================================================

import logging
import time
import uuid
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.config import get_openai_config
from config.thresholds import COMMON_THRESHOLDS, HANDLER_THRESHOLDS, ALL_DEPARTMENT_CONTACTS
from utils.contracts import QueryRequest, HandlerResponse, ChunkResult, ResponseType
from utils.conversation_manager import get_conversation_manager

# 개별 핸들러 임포트
from handlers.satisfaction_handler import SatisfactionHandler
from handlers.cyber_handler import CyberHandler
from handlers.publish_handler import PublishHandler
from handlers.general_handler import GeneralHandler
from handlers.notice_handler import NoticeHandler
from handlers.menu_handler import MenuHandler

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

# ================================================================
# CentralOrchestrator 클래스 (간소화)
# ================================================================

class CentralOrchestrator:
    """6개 핸들러 통합 관리자 (간소화 버전)"""
    
    def __init__(self):
        """간소한 초기화"""
        # OpenAI 클라이언트
        self.openai_config = get_openai_config()
        self.openai_client = None
        
        if OPENAI_AVAILABLE and self.openai_config['api_key']:
            try:
                self.openai_client = openai.OpenAI(
                    api_key=self.openai_config['api_key'],
                    timeout=LLM_TIMEOUT_SECONDS,
                    max_retries=self.openai_config['max_retries']
                )
            except Exception as e:
                logger.error(f"OpenAI 초기화 실패: {e}")
        
        # 대화 매니저
        self.conversation_manager = get_conversation_manager()
        
        # 6개 핸들러 간단 초기화
        self.handlers = {
            "satisfaction": SatisfactionHandler(),
            "cyber": CyberHandler(),
            "publish": PublishHandler(),
            "general": GeneralHandler(),
            "notice": NoticeHandler(),
            "menu": MenuHandler()
        }
        
        # 병렬 처리
        self.executor = ThreadPoolExecutor(max_workers=MAX_HANDLER_WORKERS)
        
        logger.info(f"CentralOrchestrator 초기화: {len(self.handlers)}개 핸들러")
    
    def handle(self, request: QueryRequest) -> HandlerResponse:
        """통합 처리 메인 로직"""
        start_time = time.time()
        
        # 쿼리 및 대화 ID 추출
        query = getattr(request, 'query', '') or getattr(request, 'text', '')
        conversation_id = getattr(request, 'conversation_id', None) or f"conv_{uuid.uuid4().hex[:8]}"
        
        # 지시어 해소
        resolved_query = self.conversation_manager.resolve_references(
            query, self.conversation_manager.get_recent_context_for_reference(conversation_id)
        )
        
        # 6개 핸들러 병렬 실행
        all_chunks = self._execute_handlers_parallel(resolved_query)
        
        # 4단계 분기 결정
        response_type = self.conversation_manager.determine_response_type(all_chunks)
        
        # 분기별 응답 생성
        if response_type == ResponseType.CASUAL_CHAT:
            response = self._handle_casual_chat()
        elif response_type == ResponseType.INSUFFICIENT_INFO:
            response = self._handle_insufficient_info(query)
        elif response_type == ResponseType.CLARIFICATION:
            response = self._handle_clarification(query, all_chunks)
        else:  # CONFIDENT_ANSWER
            response = self._handle_confident_answer(resolved_query, all_chunks, conversation_id)
        
        # 대화 기록 저장 및 message_id 설정
        message_id = self.conversation_manager.add_turn(
            conv_id=conversation_id,
            user_message=query,
            bot_response=response.answer,
            confidence=response.confidence,
            domain_used=[chunk.domain for chunk in all_chunks[:MAX_CHUNKS_PER_DOMAIN]],
            response_type=response_type
        )
        
        response.message_id = message_id
        response.response_type = response_type
        response.elapsed_ms = (time.time() - start_time) * 1000
        
        return response
    
    def _execute_handlers_parallel(self, query: str) -> List[ChunkResult]:
        """6개 핸들러 병렬 실행 및 chunk 수집"""
        all_chunks = []
        
        # 병렬 작업 제출
        future_to_domain = {}
        for domain, handler in self.handlers.items():
            future = self.executor.submit(handler.search_chunks, query)
            future_to_domain[future] = domain
        
        # 결과 수집 (실패한 핸들러 제외)
        for future in as_completed(future_to_domain.keys(), timeout=HANDLER_TIMEOUT_SECONDS):
            domain = future_to_domain[future]
            try:
                chunks = future.result() or []
                all_chunks.extend(chunks[:MAX_CHUNKS_PER_DOMAIN])
            except Exception as e:
                logger.warning(f"{domain} 핸들러 실패: {e}")
        
        # 중복 제거 및 confidence 순 정렬
        if ENABLE_DEDUPLICATION:
            all_chunks = self._deduplicate_chunks(all_chunks)
        
        all_chunks.sort(key=lambda x: x.confidence, reverse=True)
        return all_chunks[:TOP_CHUNKS_FOR_LLM]
    
    def _deduplicate_chunks(self, chunks: List[ChunkResult]) -> List[ChunkResult]:
        """간단한 중복 제거 (내용 기반)"""
        seen_content = set()
        unique_chunks = []
        
        for chunk in chunks:
            content_hash = hash(chunk.chunk.content[:CONTENT_HASH_LENGTH])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_chunks.append(chunk)
        
        return unique_chunks
    
    def _handle_casual_chat(self) -> HandlerResponse:
        """일상 대화 처리"""
        return HandlerResponse(
            answer=CASUAL_CHAT_TEMPLATE,
            confidence=0.10,
            domain="unified",
            success=True,
            chunk_count=0
        )
    
    def _handle_insufficient_info(self, query: str) -> HandlerResponse:
        """정보 부족 처리"""
        department_list = []
        for i, dept in enumerate(ALL_DEPARTMENT_CONTACTS, 1):
            department_list.append(f"**{i}. {dept['department']}**")
            department_list.append(f"   📞 {dept['phone']}")
            department_list.append(f"   📋 {dept['description']}\n")
        
        answer = f"""죄송합니다. '{query}'에 대한 구체적인 정보를 찾을 수 없습니다.

아래 담당부서로 직접 문의해 주시면 정확한 안내를 받으실 수 있습니다:

📞 **담당부서 연락처**

{chr(10).join(department_list)}

💡 **이용 팁**: 구체적인 키워드(교육과정명, 공지 제목 등)로 다시 질문해 주시면 더 정확한 답변을 드릴 수 있어요!"""
        
        return HandlerResponse(
            answer=answer,
            confidence=0.25,
            domain="unified",
            success=True,
            chunk_count=0
        )
    
    def _handle_clarification(self, query: str, chunks: List[ChunkResult]) -> HandlerResponse:
        """되묻기 처리"""
        domains_found = list(set([chunk.domain for chunk in chunks[:3]]))
        
        domain_options = {
            "satisfaction": "📊 교육과정 만족도나 성과 분석 정보",
            "cyber": "💻 사이버교육(온라인 교육) 수강 관련",
            "publish": "📖 공식 발행물이나 계획서/평가서 자료",
            "general": "📋 학칙, 규정, 담당자 연락처 정보",
            "notice": "📢 최신 공지사항이나 중요 알림",
            "menu": "🍽️ 구내식당 메뉴나 식단표"
        }
        
        options = [domain_options.get(domain, f"{domain} 관련 정보") for domain in domains_found]
        if not options:
            options = ["📚 교육과정 정보", "📊 교육 만족도", "💻 사이버교육", "📢 공지사항", "🍽️ 구내식당"]
        
        formatted_options = [f"{i}️⃣ {option}" for i, option in enumerate(options, 1)]
        
        answer = f"""혹시 이런 의미로 질문하신 건가요?

{chr(10).join(formatted_options)}

💡 더 구체적으로 말씀해 주시면 정확한 안내를 해드릴게요!"""
        
        max_confidence = max([chunk.confidence for chunk in chunks]) if chunks else 0.37
        
        return HandlerResponse(
            answer=answer,
            confidence=max_confidence,
            domain="unified",
            success=True,
            chunk_count=len(chunks)
        )
    
    def _handle_confident_answer(self, query: str, chunks: List[ChunkResult], conversation_id: str) -> HandlerResponse:
        """정상 RAG 답변 처리"""
        if not self.openai_client:
            return HandlerResponse(
                answer="죄송합니다. 현재 AI 응답 서비스를 사용할 수 없습니다.",
                confidence=0.0,
                domain="unified",
                success=False
            )
        
        # 대화 맥락 및 프롬프트 생성
        conversation_context = self.conversation_manager.get_context_for_llm(conversation_id)
        references = self._create_references(chunks)
        context_section = f"\n\n=== 📝 이전 대화 맥락 ===\n{conversation_context}" if conversation_context.strip() else ""
        
        prompt = UNIFIED_PROMPT_TEMPLATE.format(
            query=query,
            references=references,
            context_section=context_section
        )
        
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
            max_confidence = max([chunk.confidence for chunk in chunks]) if chunks else 0.5
            
            return HandlerResponse(
                answer=answer,
                confidence=max_confidence,
                domain="unified",
                success=True,
                chunk_count=len(chunks)
            )
            
        except Exception as e:
            logger.error(f"OpenAI 호출 실패: {e}")
            return HandlerResponse(
                answer=f"죄송합니다. '{query}' 처리 중 일시적인 오류가 발생했습니다.\n\n잠시 후 다시 시도해 주시거나, 경상남도인재개발원(055-254-2051)으로 직접 문의해 주세요.",
                confidence=0.0,
                domain="unified",
                success=False
            )
    
    def _create_references(self, chunks: List[ChunkResult]) -> str:
        """참고 자료 섹션 생성"""
        domain_chunks = {}
        for chunk in chunks:
            domain = chunk.domain
            if domain not in domain_chunks:
                domain_chunks[domain] = []
            domain_chunks[domain].append(chunk)
        
        domain_names = {
            "satisfaction": "📊 만족도 조사",
            "cyber": "💻 사이버교육",
            "publish": "📖 발행물",
            "general": "📋 일반정보",
            "notice": "📢 공지사항",
            "menu": "🍽️ 구내식당"
        }
        
        sections = []
        for domain, domain_chunk_list in domain_chunks.items():
            section_name = domain_names.get(domain, domain)
            sections.append(f"\n=== {section_name} ===")
            
            for i, chunk in enumerate(domain_chunk_list, 1):
                content = chunk.chunk.content[:300] + "..." if len(chunk.chunk.content) > 300 else chunk.chunk.content
                sections.append(f"{i}. {content} (신뢰도: {chunk.confidence:.2f})")
        
        return "\n".join(sections)

# ================================================================
# 전역 인스턴스 및 편의 함수
# ================================================================

_central_orchestrator: Optional[CentralOrchestrator] = None

def get_central_orchestrator() -> CentralOrchestrator:
    """전역 CentralOrchestrator 반환 (싱글톤)"""
    global _central_orchestrator
    if _central_orchestrator is None:
        _central_orchestrator = CentralOrchestrator()
    return _central_orchestrator

def process_query(query: str, conversation_id: Optional[str] = None) -> HandlerResponse:
    """쿼리 처리 편의 함수"""
    orchestrator = get_central_orchestrator()
    request = QueryRequest(query=query, conversation_id=conversation_id, follow_up=False)
    return orchestrator.handle(request)
