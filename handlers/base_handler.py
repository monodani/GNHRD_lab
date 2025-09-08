# handlers/base_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - CentralOrchestrator v7.1 (안정화)
Config-Driven 기반 8개 핸들러 통합 처리 시스템
"""

import logging
import uuid
import re # 🔥 [신규/확인] 정규 표현식 라이브러리 import
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.config import get_config
from utils.contracts import QueryRequest, HandlerResponse, ChunkResult
from utils.conversation_manager import get_conversation_manager

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

class CentralOrchestrator:
    def __init__(self):
        self.config = get_config()
        self.routing_model = self.config.OPENAI_MODEL
        self.final_model = self.config.OPENAI_MODEL
        self.max_workers = 8
        self.handler_timeout = 20
        self.chunks_per_handler = 2

        self.client = None
        if OPENAI_AVAILABLE and self.config.OPENAI_API_KEY:
            self.client = openai.OpenAI(api_key=self.config.OPENAI_API_KEY, timeout=30.0)
        
        self.conversation_manager = get_conversation_manager()
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.available_handlers = self.config.HANDLERS
        
        handler_descriptions = [f"- {name}: {conf['description']}" for name, conf in self.available_handlers.items()]
        self.routing_prompt_template = f"""다음 사용자 질문을 분석하여 가장 적절한 처리 방법을 결정해주세요.

사용자 질문: {{query}}

=== 처리 방법 ===
1. CASUAL: 일상대화, 안부인사, 개인적 고민 등 업무와 무관한 대화
2. NO_HANDLER: 경상남도인재개발원과 전혀 관련 없는 정보 요청
3. HANDLERS: 아래 핸들러 중 관련된 것들 선택 (복수 선택 가능)

=== 사용 가능한 핸들러 ===
{chr(10).join(handler_descriptions)}

출력 형식:
- 일상대화: "CASUAL"
- 관련 없는 정보: "NO_HANDLER" 
- 업무 질문: "HANDLERS: handler_name1, handler_name2, ..."

답변:"""
        logger.info(f"✅ CentralOrchestrator v7.1 초기화 완료 ({len(self.available_handlers)}개 핸들러 동적 로드)")

    def handle(self, request: QueryRequest) -> HandlerResponse:
        query = getattr(request, 'query', '')
        conv_id = getattr(request, 'conversation_id', f"conv_{uuid.uuid4().hex[:8]}")
        
        resolved_query = self.conversation_manager.resolve_references(
            query, self.conversation_manager.get_recent_context_for_reference(conv_id)
        )
        
        routing_result = self._route_query(resolved_query)
        
        # 🔥 [핵심 수정] 'startswith' 대신 'in'을 사용하여 라우팅 판별 로직의 유연성 확보
        if "CASUAL" in routing_result:
            response = self._handle_casual(resolved_query)
        elif "NO_HANDLER" in routing_result:
            response = self._handle_no_handler(resolved_query)
        else:
            handlers_to_run = self._parse_handlers(routing_result)
            
            # 핸들러가 선택되지 않은 경우도 NO_HANDLER와 동일하게 처리
            if not handlers_to_run:
                 response = self._handle_no_handler(resolved_query)
            else:
                all_chunks = self._execute_handlers(resolved_query, handlers_to_run)
                if not all_chunks:
                    response = self._handle_no_handler(resolved_query)
                else:
                    response = self._generate_final_answer(resolved_query, all_chunks, conv_id)

        message_id = self.conversation_manager.add_turn(
            conv_id=conv_id, user_message=query, bot_response=response.answer, confidence=response.confidence
        )
        response.message_id = message_id
        return response

    def _route_query(self, query: str) -> str:
        if not self.client: return "HANDLERS: general"
        try:
            prompt = self.routing_prompt_template.format(query=query)
            response = self.client.chat.completions.create(
                model=self.routing_model, messages=[{"role": "user", "content": prompt}], temperature=0.1, max_tokens=100
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"라우팅 실패: {e}")
            return "HANDLERS: general"

    def _parse_handlers(self, routing_result: str) -> List[str]:
        """
        [리팩토링] 라우팅 결과에서 핸들러 목록 추출 (정규 표현식으로 안정성 강화)
        "답변: 'HANDLERS: general'" 과 같은 다양한 응답 형식도 처리 가능합니다.
        """
        # 🔥 [핵심 수정] 'HANDLERS:' 키워드 이후의 모든 단어를 추출하는 정규 표현식
        # re.IGNORECASE는 HANDLERS, handlers 등 대소문자를 구분하지 않게 합니다.
        match = re.search(r'HANDLERS:\s*(.*)', routing_result, re.IGNORECASE)
        
        if not match:
            # 'HANDLERS:' 키워드를 찾지 못한 경우
            return []

        handler_part = match.group(1).replace('"', '').replace("'", "") # 따옴표 제거
        handlers = [h.strip() for h in handler_part.split(",")]
        
        # 유효한 핸들러 이름만 필터링
        valid_handlers = [h for h in handlers if h in self.available_handlers]
        return valid_handlers

    def _execute_handlers(self, query: str, handlers: List[str]) -> List[ChunkResult]:
        all_chunks = []
        futures = {}
        for handler_name in handlers:
            try:
                handler_config = self.available_handlers.get(handler_name)
                if not handler_config: continue
                
                class_name = handler_config['class']
                module_path = f"handlers.{handler_name}_handler"
                module = __import__(module_path, fromlist=[class_name])
                handler_class = getattr(module, class_name)
                handler_instance = handler_class()
                
                future = self.executor.submit(handler_instance.search_chunks, query)
                futures[future] = handler_name
            except Exception as e:
                logger.error(f"{handler_name} 핸들러 로드 실패: {e}")
        
        for future in as_completed(futures.keys(), timeout=self.handler_timeout):
            try:
                chunks = future.result() or []
                all_chunks.extend(chunks[:self.chunks_per_handler])
            except Exception as e:
                logger.warning(f"{futures[future]} 핸들러 실행 오류: {e}")
        
        all_chunks.sort(key=lambda x: x.confidence, reverse=True)
        return all_chunks[:10]

    def _handle_casual(self, query: str) -> HandlerResponse:
        answer = "안녕하세요! 벼리입니다. 저는 경상남도인재개발원의 AI 어시스턴트입니다. 무엇을 도와드릴까요?"
        if self.client:
            try:
                response = self.client.chat.completions.create(
                    model=self.final_model,
                    messages=[{"role": "user", "content": f"친근한 AI 어시스턴트로서 다음 말에 답변해주세요: {query}"}],
                    temperature=0.7, max_tokens=300
                )
                answer = response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"일상대화 LLM 호출 실패: {e}")
        
        return HandlerResponse(answer=answer, confidence=0.95, domain="casual", success=True)

    def _handle_no_handler(self, query: str) -> HandlerResponse:
        general_answer = "죄송하지만 해당 분야에 대한 전문적인 답변을 드리기 어렵습니다."
        if self.client:
            try:
                response = self.client.chat.completions.create(
                    model=self.final_model, messages=[{"role": "user", "content": query}], temperature=0.3, max_tokens=200
                )
                general_answer = response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"NO_HANDLER LLM 호출 실패: {e}")
        
        answer_template = """경상남도인재개발원 자료 모음집에서는 알 수 없는 내용입니다.

제가 알려드릴 수 있는 내용은 다음과 같습니다:
- 교육과정 및 일정 안내
- 교육 만족도 및 성과 분석
- 사이버교육 수강 방법
- 공지사항 및 최신 소식
- 구내식당 메뉴 및 식단표
- 각종 발행물 및 공식 자료

**그래서 정확하지 않을 수 있지만 답변드리자면,** {general_answer}

더 정확한 정보가 필요하시면 경상남도인재개발원(055-254-2051)으로 문의해주세요."""
        final_answer = answer_template.format(general_answer=general_answer)
        return HandlerResponse(answer=final_answer, confidence=0.3, domain="general", success=True)
        
    def _generate_final_answer(self, query: str, chunks: List[ChunkResult], conv_id: str) -> HandlerResponse:
        if not self.client:
            return HandlerResponse(answer="현재 AI 서비스를 사용할 수 없습니다.", confidence=0.0, domain="error", success=False)
        
        references = "\n".join([f"• {chunk.chunk.content[:200]}..." for chunk in chunks[:5]])
        context = self.conversation_manager.get_context_for_llm(conv_id)
        if context.strip():
            references += f"\n\n[이전 대화]\n{context}"
        
        final_prompt_template = """당신은 경상남도인재개발원의 전문 AI 어시스턴트 "벼리"입니다.

사용자 질문: {query}

참고 자료:
{references}

위 자료를 바탕으로 정확하고 친근한 답변을 작성해주세요.
- 정중하고 친근한 말투 사용
- 중요 정보는 구조화하여 제시
- 관련 부서 연락처 포함 (가능한 경우)

답변:"""
        prompt = final_prompt_template.format(query=query, references=references)
        
        try:
            response = self.client.chat.completions.create(
                model=self.final_model, messages=[{"role": "user", "content": prompt}], temperature=0.1, max_tokens=800
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
            return HandlerResponse(answer="죄송합니다. 답변 생성 중 오류가 발생했습니다.", confidence=0.0, domain="error", success=False)

# --- 전역 함수들 ---
_central_orchestrator: Optional[CentralOrchestrator] = None
def get_central_orchestrator() -> CentralOrchestrator:
    global _central_orchestrator
    if _central_orchestrator is None:
        _central_orchestrator = CentralOrchestrator()
    return _central_orchestrator

def process_query(query: str, conversation_id: Optional[str] = None) -> HandlerResponse:
    orchestrator = get_central_orchestrator()
    request = QueryRequest(query=query, conversation_id=conversation_id)
    return orchestrator.handle(request)
