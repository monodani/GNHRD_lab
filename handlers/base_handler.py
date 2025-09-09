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

# [수정] 날짜/시간 계산을 위한 라이브러리 추가
from datetime import datetime, timedelta, timezone
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
# [신규] 대한민국 표준시(KST) 정의
KST = timezone(timedelta(hours=9))

class CentralOrchestrator:
    def __init__(self):
        self.config = get_config()
        self.routing_model = self.config.OPENAI_MODEL
        self.final_model = self.config.OPENAI_MODEL
        self.max_workers = 8
        self.handler_timeout = 30
        self.chunks_per_handler = 10

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
        # [수정] 전체 handle 메서드 흐름 변경
        query = getattr(request, 'query', '')
        conv_id = getattr(request, 'conversation_id', f"conv_{uuid.uuid4().hex[:8]}")
        
        # 단계 1: 지시어 해소 ("그것" -> "중견리더 과정")
        resolved_query = self.conversation_manager.resolve_references(
            query, self.conversation_manager.get_recent_context_for_reference(conv_id)
        )
        
        # 단계 2: 시간 표현 전처리 ("오늘" -> "(2025-09-10 또는 2025. 09. 10.)")
        time_aware_query = self._resolve_time_references(resolved_query)
        if resolved_query != time_aware_query:
            logger.info(f"시간 표현 변환: '{resolved_query}' -> '{time_aware_query}'")

        # 단계 3: 라우팅 (전처리가 완료된 최종 쿼리 사용)
        routing_result = self._route_query(time_aware_query)
        
        # 단계 4: 라우팅 결과에 따라 핸들러 실행 또는 답변 생성
        if "CASUAL" in routing_result:
            response = self._handle_casual(time_aware_query)
        elif "NO_HANDLER" in routing_result:
            response = self._handle_no_handler(time_aware_query)
        else:
            handlers_to_run = self._parse_handlers(routing_result)
            if not handlers_to_run:
                 response = self._handle_no_handler(time_aware_query)
            else:
                all_chunks = self._execute_handlers(time_aware_query, handlers_to_run)
                if not all_chunks:
                    response = self._handle_no_handler(time_aware_query)
                else:
                    response = self._generate_final_answer(time_aware_query, all_chunks, conv_id)

        # 최종 단계: 대화 기록 저장 (사용자의 원본 질문으로 저장)
        message_id = self.conversation_manager.add_turn(
            conv_id=conv_id, user_message=query, bot_response=response.answer, confidence=response.confidence
        )
        response.message_id = message_id
        return response

    # [신규] 시간 표현 전처리 메서드 추가
    def _resolve_time_references(self, query: str) -> str:
        """
        사용자 쿼리의 상대 시간 표현을 DB의 두 가지 날짜 형식('YYYY-MM-DD', 'YYYY. MM. DD.')을
        모두 포함하는 절대 날짜 문자열로 변환합니다.
        """
        now = datetime.now(KST)
        today = now.date()

        def format_date_for_search(date_obj: datetime.date) -> str:
            format1 = date_obj.strftime('%Y-%m-%d')
            format2 = date_obj.strftime('%Y. %m. %d.')
            return f"({format1} 또는 {format2})"

        def format_range(start_date: datetime.date, end_date: datetime.date) -> str:
            return f"{start_date.strftime('%Y-%m-%d')}부터 {end_date.strftime('%Y-%m-%d')}까지"

        def day_replacer(match):
            try:
                num = int(match.group(1))
                direction = match.group(2)
                if direction == '후': target_date = today + timedelta(days=num)
                else: target_date = today - timedelta(days=num)
                return format_date_for_search(target_date)
            except ValueError: return match.group(0)
            
        query = re.sub(r'(\d+)\s*일\s*(후|전)', day_replacer, query)

        keywords = {
            "다음 주": lambda: format_range(today + timedelta(days=7-today.weekday()), today + timedelta(days=13-today.weekday())),
            "이번 주": lambda: format_range(today - timedelta(days=today.weekday()), today + timedelta(days=6-today.weekday())),
            "저번 주": lambda: format_range(today - timedelta(days=today.weekday()+7), today - timedelta(days=today.weekday()+1)),
            "내일": lambda: format_date_for_search(today + timedelta(days=1)),
            "어제": lambda: format_date_for_search(today - timedelta(days=1)),
            "오늘": lambda: format_date_for_search(today),
        }
        
        for keyword, calculator in keywords.items():
            pattern = re.compile(r'\b' + re.escape(keyword) + r'\b')
            if pattern.search(query):
                query = pattern.sub(calculator(), query)

        if "지금" in query or "현재" in query:
            replacement_string = f"{format_date_for_search(today)} {now.strftime('%H시 %M분')}"
            if "식당" in query or "메뉴" in query:
                hour = now.hour
                time_context = "현재"
                if 11 <= hour < 14: time_context = "점심"
                elif 17 <= hour < 19: time_context = "저녁"
                elif hour < 10: time_context = "아침"
                replacement_string = f"{format_date_for_search(today)} {time_context}"
            query = query.replace("지금", replacement_string).replace("현재", replacement_string)
            
        return query

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
        return all_chunks[:20]

    def _handle_casual(self, query: str) -> HandlerResponse:
        answer = "안녕하세요! 벼리입니다. 저는 경상남도인재개발원의 AI 어시스턴트입니다. 무엇을 도와드릴까요?"
        if self.client:
            try:
                response = self.client.chat.completions.create(
                    model=self.final_model,
                    messages=[{"role": "user", "content": f"친근한 AI 어시스턴트로서 다음 말에 존대말로 답변해주세요: {query}"}],
                    temperature=0.7, max_tokens=300
                )
                answer = response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"일상대화 LLM 호출 실패: {e}")
        
        return HandlerResponse(answer=answer, confidence=0.95, domain="casual", success=True)

    def _handle_no_handler(self, query: str) -> HandlerResponse:
        general_answer = "죄송하지만 해당 분야에 대해 전문적인 답변을 드리기 어렵습니다."
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
- 교육 만족도 통계 및 성과 분석
- 사이버 교육과정 소개
- 공지사항 안내 및 경남인재개발원 소개
- 경남인재개발원 구내식당 메뉴 안내
- 각종 발행물 및 공식자료 정보 제공

그래서 정확하지 않을 수 있지만 답변드리자면, {general_answer}

경남인재개발원 관련 질문을 다시 주시거나 직원과 연결을 원하시면 경상남도인재개발원(055-254-2051)으로 문의해주세요."""
        final_answer = answer_template.format(general_answer=general_answer)
        return HandlerResponse(answer=final_answer, confidence=0.3, domain="general", success=True)
        
    def _generate_final_answer(self, query: str, chunks: List[ChunkResult], conv_id: str) -> HandlerResponse:
        if not self.client:
            return HandlerResponse(answer="현재 AI 서비스를 사용할 수 없습니다.", confidence=0.0, domain="error", success=False)
        
        # --- [포인트 1: '참고 자료'와 '대화 기록' 변수 분리 및 순서 명확화] ---
        # 설명: LLM에게 정보를 논리적인 순서(대화 맥락 -> 참고 자료)로 제공하기 위해
        #       두 변수를 분리하여 관리합니다. 이렇게 하면 프롬프트 템플릿의 가독성과 유지보수성이 향상됩니다.
        
        # [수정 시작 1]
        # 1. '참고 자료' 생성
        reference_list = []
        for i, chunk in enumerate(chunks[:15]):
            source = chunk.chunk.metadata.get("source", "")
            content = chunk.chunk.content

            if "analysis" in source:
                reference_list.append(f"--- 참고자료 #{i+1} (출처: {chunk.domain} 데이터 분석) ---\n{content}")
            else:
                reference_list.append(f"--- 참고자료 #{i+1} (출처: {chunk.domain}) ---\n{content}...")
        
        references_text = "\n\n".join(reference_list)

        # 2. '대화 기록' 가져오기
        llm_context = self.conversation_manager.get_context_for_llm(conv_id)
        # [수정 끝 1]

        # --- [포인트 2: 최종 프롬프트 템플릿 변수명 통일] ---
        # 설명: 프롬프트 템플릿 내의 변수명 `{llm_context}`와 `{references}`가
        #       실제 format 메서드에 전달될 변수명과 일치하도록 수정합니다.
        #       이전 코드의 [이전 대화] 부분을 제거하고, [대화 기록]으로 일원화합니다.
        
        # [수정 시작 2]
        final_prompt_template = """
# 페르소나 설정(Persona) :
당신의 이름은 "벼리"(영문명: Byeoli)이며, 경상남도인재개발원의 친절하고 유능한 AI 어시스턴트입니다. 항상 밝고 정중하고 상냥한 존대말투를 사용하세요.

# 지침(Instruction) :
아래에 제공되는 [대화 기록]과 [참고 자료]를 바탕으로 [사용자 질문]에 대해 답변해야 합니다. 다음 규칙을 반드시 지켜주세요.

1.  **맥락 우선주의**: [대화 기록]을 먼저 분석해서 사용자가 무엇을 원하는지 정확히 파악하세요. 특히, 사용자가 '다른 것', '그거 말고', '추가로' 등의 표현을 사용하면 절대 이전에 했던 말을 반복하지 말고 새로운 정보를 제공해야 합니다.
2.  **자료는 근거로만**: [참고 자료]는 답변의 근거로만 사용하고, 내용을 그대로 읊지 마세요. 질문에 답변하는 데 필요한 정보만 뽑아서 자연스러운 대화체로 가공해야 합니다.
3.  **반복 금지**: 바로 이전 답변에서 이미 설명한 내용은 다시 반복하지 마세요. 예를 들어, 사용자가 행사에 대해 물어서 당신이 행사개요를 안내헸고, 이어서 사용자가 그 행사 참여 방법을 다시 물어보면 당신은 참여 방법만 알려주고 다시 행사 개요를 또 설명하지 마세요.
4.  **정형화된 데이터가 포함된 답변 제공 시 목록 또 마크다운 테이블 적극 활용** : 제공된 자료가 특성상 정형화된 데이터(표/테이블, 통계 및 수치형)거나 답변 시인성/가독성을 최대화하기 위해  **목록** 형태 또는 **마크다운 테이블**을 적극적으로 활용하세요.
5.  **인사는 한번만**: "안녕하세요!" 인사는 사용자가 먼저 인사할 경우에만 하세요.

---
[대화 기록]
{llm_context}

---

[참고 자료]
{references}

---

[사용자 질문]
{query}


답변:"""
        # [수정 끝 2]

        # --- [포인트 3: format 메서드에 올바른 변수 전달] ---
        # 설명: 위에서 분리하여 생성한 `llm_context`와 `references_text` 변수를
        #       템플릿의 `{llm_context}`, `{references}` 자리에 정확히 전달합니다.
        
        # [수정 시작 3]
        prompt = final_prompt_template.format(
            llm_context=llm_context, 
            references=references_text, 
            query=query
        )
        # [수정 끝 3]
        
        try:
            response = self.client.chat.completions.create(
                model=self.final_model, messages=[{"role": "user", "content": prompt}], temperature=0.1, max_tokens=2000
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
