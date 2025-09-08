# handlers/base_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - CentralOrchestrator v6.1
LLM 라우팅 기반 8개 핸들러 통합 처리 시스템

핵심 기능:
- LLM 라우팅으로 적절한 핸들러 선택
- 8개 핸들러 병렬 실행 후 통합 LLM 답변
- message_id 반환 (피드백 연동)

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-09-07
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.config import get_openai_config
from utils.contracts import QueryRequest, HandlerResponse, ChunkResult
from utils.conversation_manager import get_conversation_manager

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# =============================================================================
# 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
# =============================================================================

# LLM 모델 설정
ROUTING_MODEL = "gpt-4o-mini"      # 라우팅용 LLM 모델
FINAL_MODEL = "gpt-4o-mini"        # 최종 답변 생성용 LLM 모델
LLM_TIMEOUT = 30                   # LLM 호출 타임아웃 (초)
LLM_TEMPERATURE = 0.1              # LLM 창의성 설정 (0.0~1.0)

# 병렬 처리 설정
MAX_WORKERS = 8                    # 핸들러 병렬 실행 최대 워커 수
HANDLER_TIMEOUT = 10               # 개별 핸들러 실행 타임아웃 (초)
CHUNKS_PER_HANDLER = 2             # 핸들러당 최대 반환 청크 수

# 8개 핸들러 목록 및 설명 (pandas agent 4개 + FAISS 벡터스토어 4개)
AVAILABLE_HANDLERS = {
    "course_satisfaction": "교육과정 만족도 및 종합 평가 분석 정보",
    "subject_satisfaction": "교과목별 강의 만족도 및 평가 분석 정보", 
    "cyber": "사이버교육, 온라인 과정, 이러닝 관련",
    "schedule": "교육 일정, 스케줄, 기간 관련",
    "general": "학칙, 규정, 연락처, 일반 정보, 교육과정별 커리큘럼 정보",
    "publish": "발행물, 계획서, 평가서, 공식 자료",
    "notice": "공지사항, 알림, 최신 소식, 경남인재개발원 소개 및 현황 정보, 벼리 소개", "금주 진행 교육과정 설명",
    "menu": "구내식당, 메뉴, 식단표 관련"
}

# 핸들러명 → 클래스명 매핑 (언더스코어 포함 이름 처리)
HANDLER_CLASS_MAPPING = {
    "course_satisfaction": "CourseSatisfactionHandler",
    "subject_satisfaction": "SubjectSatisfactionHandler", 
    "cyber": "CyberHandler",
    "schedule": "ScheduleHandler",
    "general": "GeneralHandler",
    "publish": "PublishHandler", 
    "notice": "NoticeHandler",
    "menu": "MenuHandler"
}

# 라우팅 프롬프트
ROUTING_PROMPT = f"""다음 사용자 질문을 분석하여 적절한 처리 방법을 결정해주세요.

사용자 질문: {{query}}

=== 처리 방법 ===
1. CASUAL: 일상대화, 안부인사, 개인적 고민 등 업무와 무관한 대화
2. NO_HANDLER: 경상남도인재개발원과 전혀 관련 없는 정보 요청
3. HANDLERS: 아래 핸들러 중 관련된 것들 선택 (복수 선택 가능)

=== 사용 가능한 핸들러 ===
{chr(10).join([f"- {k}: {v}" for k, v in AVAILABLE_HANDLERS.items()])}

출력 형식:
- 일상대화: "CASUAL"
- 관련 없는 정보: "NO_HANDLER" 
- 업무 질문: "HANDLERS: handler1, handler2, ..."

답변:"""

# 답변 템플릿
CASUAL_TEMPLATE = """안녕하세요! 벼리입니다 😊

저는 경상남도인재개발원의 AI 어시스턴트로, 교육과정, 만족도 조사, 공지사항, 일정 등에 대해 도움을 드릴 수 있어요.

개인적인 고민이나 일상 이야기도 언제든 편하게 나눠주세요! 어떤 도움이 필요하신가요?"""

NO_HANDLER_TEMPLATE = """경상남도인재개발원 자료 모음집에서는 알 수 없는 내용입니다.

제가 알려드릴 수 있는 내용은 다음과 같습니다:
- 교육과정 및 일정 안내
- 교육 만족도 및 성과 분석  
- 사이버교육 수강 방법
- 공지사항 및 최신 소식
- 구내식당 메뉴 및 식단표
- 각종 발행물 및 공식 자료

**그래서 정확하지 않을 수 있지만 답변드리자면,** {{general_answer}}

더 정확한 정보가 필요하시면 경상남도인재개발원(055-254-2051)으로 문의해주세요."""

FINAL_PROMPT = """당신은 경상남도인재개발원의 전문 AI 어시스턴트 "벼리"입니다.

사용자 질문: {{query}}

참고 자료:
{{references}}

위 자료를 바탕으로 정확하고 친근한 답변을 작성해주세요.
- 정중하고 친근한 말투 사용
- 중요 정보는 구조화하여 제시
- 관련 부서 연락처 포함 (가능한 경우)

답변:"""

# =============================================================================

logger = logging.getLogger(__name__)

class CentralOrchestrator:
    """LLM 라우팅 기반 8개 핸들러 통합 조정자"""
    
    def __init__(self):
        # OpenAI 초기화
        self.openai_config = get_openai_config()
        self.client = None
        
        if OPENAI_AVAILABLE and self.openai_config['api_key']:
            self.client = openai.OpenAI(
                api_key=self.openai_config['api_key'],
                timeout=LLM_TIMEOUT
            )
        
        # 대화 관리자
        self.conversation_manager = get_conversation_manager()
        
        # 병렬 실행자
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        
        logger.info("CentralOrchestrator v6.1 초기화 완료 (8개 핸들러)")
    
    def handle(self, request: QueryRequest) -> HandlerResponse:
        """통합 처리 메인 로직"""
        query = getattr(request, 'query', '')
        conv_id = getattr(request, 'conversation_id', f"conv_{uuid.uuid4().hex[:8]}")
        
        # 지시어 해소 ("그것" → "중견리더 과정")
        resolved_query = self.conversation_manager.resolve_references(
            query, self.conversation_manager.get_recent_context_for_reference(conv_id)
        )
        
        # LLM 라우팅 (핵심 알고리즘)
        routing_result = self._route_query(resolved_query)
        
        # 3분기 처리
        if routing_result.startswith("CASUAL"):
            response = self._handle_casual(resolved_query)
        elif routing_result.startswith("NO_HANDLER"):
            response = self._handle_no_handler(resolved_query)
        else:
            handlers = self._parse_handlers(routing_result)
            response = self._handle_with_handlers(resolved_query, handlers, conv_id)
        
        # message_id 설정 및 대화 기록 (피드백 연동용)
        message_id = self.conversation_manager.add_turn(
            conv_id=conv_id,
            user_message=query,
            bot_response=response.answer,
            confidence=response.confidence
        )
        response.message_id = message_id
        
        return response
    
    def _route_query(self, query: str) -> str:
        """LLM을 통한 쿼리 라우팅"""
        if not self.client:
            return "HANDLERS: general"
        
        try:
            response = self.client.chat.completions.create(
                model=ROUTING_MODEL,
                messages=[{"role": "user", "content": ROUTING_PROMPT.format(query=query)}],
                temperature=LLM_TEMPERATURE,
                max_tokens=100
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"라우팅 실패: {e}")
            return "HANDLERS: general"
    
    def _parse_handlers(self, routing_result: str) -> List[str]:
        """라우팅 결과에서 핸들러 목록 추출"""
        if "HANDLERS:" not in routing_result:
            return ["general"]
        
        handler_part = routing_result.split("HANDLERS:")[1].strip()
        handlers = [h.strip() for h in handler_part.split(",")]
        
        # 유효한 핸들러만 필터링
        valid_handlers = [h for h in handlers if h in AVAILABLE_HANDLERS]
        return valid_handlers if valid_handlers else ["general"]
    
    def _handle_casual(self, query: str) -> HandlerResponse:
        """일상대화 처리"""
        if not self.client:
            answer = CASUAL_TEMPLATE
        else:
            try:
                response = self.client.chat.completions.create(
                    model=FINAL_MODEL,
                    messages=[{
                        "role": "user", 
                        "content": f"친근한 AI 어시스턴트로서 다음 말에 답변해주세요: {query}"
                    }],
                    temperature=0.7,
                    max_tokens=300
                )
                answer = response.choices[0].message.content.strip()
            except:
                answer = CASUAL_TEMPLATE
        
        return HandlerResponse(
            answer=answer,
            confidence=0.95,
            domain="casual",
            success=True
        )
    
    def _handle_no_handler(self, query: str) -> HandlerResponse:
        """관련 없는 질문 처리"""
        general_answer = "죄송하지만 해당 분야에 대한 전문적인 답변을 드리기 어렵습니다."
        
        if self.client:
            try:
                response = self.client.chat.completions.create(
                    model=FINAL_MODEL,
                    messages=[{"role": "user", "content": query}],
                    temperature=0.3,
                    max_tokens=200
                )
                general_answer = response.choices[0].message.content.strip()
            except:
                pass
        
        answer = NO_HANDLER_TEMPLATE.format(general_answer=general_answer)
        
        return HandlerResponse(
            answer=answer,
            confidence=0.3,
            domain="general",
            success=True
        )
    
    def _handle_with_handlers(self, query: str, handlers: List[str], conv_id: str) -> HandlerResponse:
        """핸들러 기반 처리"""
        # 병렬 실행 (핵심 알고리즘)
        all_chunks = self._execute_handlers(query, handlers)
        
        if not all_chunks:
            return self._handle_no_handler(query)
        
        # 최종 LLM 답변 생성
        return self._generate_final_answer(query, all_chunks, conv_id)
    
    def _execute_handlers(self, query: str, handlers: List[str]) -> List[ChunkResult]:
        """8개 핸들러 병렬 실행 (핵심 알고리즘)"""
        all_chunks = []
        futures = {}
        
        # 핸들러 동적 import 및 실행
        for handler_name in handlers:
            try:
                # 핸들러명 유효성 검증
                if handler_name not in HANDLER_CLASS_MAPPING:
                    logger.warning(f"알 수 없는 핸들러: {handler_name}")
                    continue
                
                # 동적 import (매핑 테이블 사용)
                module = __import__(f"handlers.{handler_name}_handler", fromlist=[HANDLER_CLASS_MAPPING[handler_name]])
                handler_class = getattr(module, HANDLER_CLASS_MAPPING[handler_name])
                handler = handler_class()
                
                # 병렬 실행
                future = self.executor.submit(handler.search_chunks, query)
                futures[future] = handler_name
            except Exception as e:
                logger.warning(f"{handler_name} 핸들러 로드 실패: {e}")
        
        # 결과 수집
        for future in as_completed(futures.keys(), timeout=HANDLER_TIMEOUT):
            try:
                chunks = future.result() or []
                all_chunks.extend(chunks[:CHUNKS_PER_HANDLER])
            except Exception as e:
                logger.warning(f"핸들러 실행 실패: {e}")
        
        # confidence 순 정렬
        all_chunks.sort(key=lambda x: x.confidence, reverse=True)
        return all_chunks[:10]  # 상위 10개만
    
    def _generate_final_answer(self, query: str, chunks: List[ChunkResult], conv_id: str) -> HandlerResponse:
        """최종 LLM 답변 생성"""
        if not self.client:
            return HandlerResponse(
                answer="현재 AI 서비스를 사용할 수 없습니다.",
                confidence=0.0,
                domain="error",
                success=False
            )
        
        # 참고 자료 구성
        references = "\n".join([
            f"• {chunk.chunk.content[:200]}..." 
            for chunk in chunks[:5]
        ])
        
        # 대화 맥락 추가
        context = self.conversation_manager.get_context_for_llm(conv_id)
        if context.strip():
            references += f"\n\n[이전 대화]\n{context}"
        
        try:
            response = self.client.chat.completions.create(
                model=FINAL_MODEL,
                messages=[{
                    "role": "user", 
                    "content": FINAL_PROMPT.format(query=query, references=references)
                }],
                temperature=LLM_TEMPERATURE,
                max_tokens=800
            )
            
            max_confidence = max([c.confidence for c in chunks]) if chunks else 0.5
            
            return HandlerResponse(
                answer=response.choices[0].message.content.strip(),
                confidence=max_confidence,
                domain="unified",
                success=True,
                chunk_count=len(chunks)
            )
            
        except Exception as e:
            logger.error(f"최종 답변 생성 실패: {e}")
            return HandlerResponse(
                answer="죄송합니다. 답변 생성 중 오류가 발생했습니다.",
                confidence=0.0,
                domain="error", 
                success=False
            )

# =============================================================================
# 전역 인스턴스 및 편의 함수
# =============================================================================

_central_orchestrator: Optional[CentralOrchestrator] = None

def get_central_orchestrator() -> CentralOrchestrator:
    """전역 CentralOrchestrator 반환"""
    global _central_orchestrator
    if _central_orchestrator is None:
        _central_orchestrator = CentralOrchestrator()
    return _central_orchestrator

def process_query(query: str, conversation_id: Optional[str] = None) -> HandlerResponse:
    """쿼리 처리 편의 함수"""
    orchestrator = get_central_orchestrator()
    request = QueryRequest(query=query, conversation_id=conversation_id)
    return orchestrator.handle(request)
