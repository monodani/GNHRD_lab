# handlers/base_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - CentralOrchestrator v7.0 (리팩토링)
Config-Driven 기반 8개 핸들러 통합 처리 시스템

핵심 기능:
- [개선] config.py의 핸들러 정의를 동적으로 로드하여 라우팅 및 실행
- LLM 라우팅으로 적절한 핸들러 선택
- 8개 핸들러 병렬 실행 후 통합 LLM 답변
- message_id 반환 (피드백 연동)

작성자: 이다니엘 from 경상남도인재개발원 (Gemini AI 리팩토링)
최종 수정: 2025-09-08
"""

import logging
import uuid
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 프로젝트 모듈 ---
from config.config import get_config, get_openai_config # get_config 추가
from utils.contracts import QueryRequest, HandlerResponse, ChunkResult
from utils.conversation_manager import get_conversation_manager

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

class CentralOrchestrator:
    """
    [리팩토링] 설정 파일(config.py) 기반으로 동작하는 통합 조정자.
    모든 핸들러 정보와 설정을 중앙에서 동적으로 로드합니다.
    """
    
    def __init__(self):
        # =============================================================================
        # 🔧 1. 설정값 로드 (중앙 관리)
        # =============================================================================
        self.config = get_config()
        self.openai_config = get_openai_config()
        
        # --- LLM 모델 설정 ---
        self.routing_model = self.config.OPENAI_MODEL # 라우팅 모델 통일
        self.final_model = self.config.OPENAI_MODEL   # 최종 답변 모델 통일
        
        # --- 병렬 처리 설정 ---
        self.max_workers = 8
        self.handler_timeout = 10
        self.chunks_per_handler = 2

        # =============================================================================
        # ⚙️ 2. 내부 변수 및 서비스 초기화
        # =============================================================================
        self.client = None
        if OPENAI_AVAILABLE and self.openai_config['api_key']:
            self.client = openai.OpenAI(
                api_key=self.openai_config['api_key'],
                timeout=30.0
            )
        
        self.conversation_manager = get_conversation_manager()
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

        # 🔥 [리팩토링] config.py에서 핸들러 정보를 동적으로 로드
        self.available_handlers = self.config.HANDLERS
        
        # 🔥 [리팩토링] 라우팅 프롬프트를 config 정보로 동적 생성
        handler_descriptions = [
            f"- {name}: {conf['description']}" 
            for name, conf in self.available_handlers.items()
        ]
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

        logger.info(f"✅ CentralOrchestrator v7.0 초기화 완료 ({len(self.available_handlers)}개 핸들러 동적 로드)")

    def handle(self, request: QueryRequest) -> HandlerResponse:
        """통합 처리 메인 로직"""
        # (기존 코드와 동일, 변경 없음)
        query = getattr(request, 'query', '')
        conv_id = getattr(request, 'conversation_id', f"conv_{uuid.uuid4().hex[:8]}")
        
        resolved_query = self.conversation_manager.resolve_references(
            query, self.conversation_manager.get_recent_context_for_reference(conv_id)
        )
        
        routing_result = self._route_query(resolved_query)
        
        if routing_result.startswith("CASUAL"):
            response = self._handle_casual(resolved_query)
        elif routing_result.startswith("NO_HANDLER"):
            response = self._handle_no_handler(resolved_query)
        else:
            handlers = self._parse_handlers(routing_result)
            response = self._handle_with_handlers(resolved_query, handlers, conv_id)
        
        message_id = self.conversation_manager.add_turn(
            conv_id=conv_id,
            user_message=query,
            bot_response=response.answer,
            confidence=response.confidence
        )
        response.message_id = message_id
        
        return response

    def _route_query(self, query: str) -> str:
        """LLM을 통한 쿼리 라우팅 (동적으로 생성된 프롬프트 사용)"""
        if not self.client: return "HANDLERS: general"
        
        try:
            # 🔥 동적으로 생성된 프롬프트 사용
            prompt = self.routing_prompt_template.format(query=query)
            response = self.client.chat.completions.create(
                model=self.routing_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"라우팅 실패: {e}")
            return "HANDLERS: general"

    def _parse_handlers(self, routing_result: str) -> List[str]:
        """[리팩토링] 라우팅 결과에서 핸들러 목록 추출 (config 기반 검증)"""
        if "HANDLERS:" not in routing_result:
            return ["general"]
        
        handler_part = routing_result.split("HANDLERS:")[1].strip()
        handlers = [h.strip() for h in handler_part.split(",")]
        
        # 🔥 유효한 핸들러만 필터링 (config.py의 핸들러 목록과 비교)
        valid_handlers = [h for h in handlers if h in self.available_handlers]
        return valid_handlers if valid_handlers else ["general"]

    def _execute_handlers(self, query: str, handlers: List[str]) -> List[ChunkResult]:
        """[리팩토링] 핸들러 병렬 실행 (config 기반 동적 import)"""
        all_chunks = []
        futures = {}
        
        for handler_name in handlers:
            try:
                # 1. 🔥 config.py에서 핸들러 정보 가져오기
                handler_config = self.available_handlers.get(handler_name)
                if not handler_config:
                    logger.warning(f"알 수 없는 핸들러: {handler_name}")
                    continue
                
                class_name = handler_config['class']

                # 2. 🔥 동적 import (가져온 클래스 이름 사용)
                # (예: handlers.general_handler 모듈에서 GeneralHandler 클래스를 가져옴)
                module_path = f"handlers.{handler_name}_handler"
                module = __import__(module_path, fromlist=[class_name])
                handler_class = getattr(module, class_name)
                handler_instance = handler_class()
                
                # 3. 병렬 실행
                future = self.executor.submit(handler_instance.search_chunks, query)
                futures[future] = handler_name

            except Exception as e:
                logger.error(f"{handler_name} 핸들러 로드 또는 실행 실패: {e}")
        
        # 결과 수집 (기존과 동일)
        for future in as_completed(futures.keys(), timeout=self.handler_timeout):
            try:
                chunks = future.result() or []
                all_chunks.extend(chunks[:self.chunks_per_handler])
            except Exception as e:
                handler_name = futures[future]
                logger.warning(f"{handler_name} 핸들러 실행 시간 초과 또는 오류: {e}")
        
        all_chunks.sort(key=lambda x: x.confidence, reverse=True)
        return all_chunks[:10]

    # --- _handle_casual, _handle_no_handler, _generate_final_answer 메서드는 변경 없음 ---
    # ... (생략) ...
    def _handle_casual(self, query: str) -> HandlerResponse:
        """일상대화 처리"""
        # ... (기존 코드)
        pass
    
    def _handle_no_handler(self, query: str) -> HandlerResponse:
        """관련 없는 질문 처리"""
        # ... (기존 코드)
        pass
        
    def _generate_final_answer(self, query: str, chunks: List[ChunkResult], conv_id: str) -> HandlerResponse:
        """최종 LLM 답변 생성"""
        # ... (기존 코드)
        pass
# =============================================================================
# 전역 인스턴스 및 편의 함수 (변경 없음)
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
