import logging
import hashlib
import time
import pandas as pd
from pathlib import Path
from typing import List, Optional

from utils.contracts import ChunkResult, TextChunk
from config.config import get_config
from langchain_experimental.agents import create_pandas_dataframe_agent
from langchain_openai import ChatOpenAI

# [수정] OutputParsingError는 더 이상 직접 임포트하여 사용하지 않습니다.
# from langchain_core.exceptions import OutputParsingError

logger = logging.getLogger(__name__)

AGENT_PROMPT_PREFIX_V2 = """
당신은 판다스 데이터프레임을 기반으로 하는 데이터분석 어시턴트입니다.
당신의 주요 목표는 사용자의 질문에 맞춰 Pandas DataFrame에서 관련 데이터를 추출하고, 명확하고 간결한 텍스트 기반 답변을 제공하는 것입니다.

다음 규칙들을 반드시 준수하세요.
- 먼저 분석하기: 사용자의 질문을 파악하고 DataFrame에서 어떤 데이터가 필요한지 결정합니다.
- 텍스트만 출력하기: 최종 답변은 반드시 일반 텍스트여야 합니다. 최종 결과물에 플롯, 시각화 또는 Python 코드를 생성하지 마십시오.
- 분석을 요하는 쿼리를 스마트하게 처리하기: '추세', '변화', '비교', 또는 '요약', '통계'와 관련된 질문의 경우, 이러한 분석에 사용될 원시 데이터를 찾아 명확하게 제시해야 합니다.
  정형화 된 답변이 필요할 경우, 리스트업을 하는 정도로만 시인성 좋게 편집하여 출력하되, 사용자가 테이블 형태의 출력을 원할 경우에는 마크다운 테이블을 사용하도록 하세요.
- 누락된 데이터에 대해 솔직하게 답변하기: 질문에 답할 데이터가 없는 경우, 그 사실을 명확하게 밝혀야 합니다.
- 간단한 질문, 간단한 답변: 간단한 조회를 요청하는 쿼리 시 그에 대한 직접적인 답변을 제공합니다.
"""

class BasePandasAgentHandler:
    def __init__(self, domain_name: str):
        config = get_config()
        common_settings = config.HANDLER_SETTINGS['pandas_agent']
        self.llm_model = common_settings['llm_model']
        self.llm_temperature = common_settings['llm_temperature']
        self.cache_ttl_seconds = common_settings['cache_ttl_seconds']
        self.confidence = common_settings['confidence_score']
        handler_settings = config.HANDLER_SETTINGS[domain_name]
        self.domain_name = domain_name
        self.csv_path = Path(handler_settings['csv_path'])
        self.data_context = common_settings.get('data_context', '')
        self.df: Optional[pd.DataFrame] = None
        self.agent = None
        self.cache: dict = {}
        self._load_data()
        self._init_agent()
        logger.info(f"✅ {self.__class__.__name__} v2.0 (최종 수정) 초기화 완료 (도메인: {self.domain_name})")

    def _load_data(self):
        if not self.csv_path.exists():
            logger.warning(f"⚠️ 데이터 파일을 찾을 수 없습니다: {self.csv_path}.")
            self.df = pd.DataFrame()
            return
        for encoding in ['utf-8', 'cp949', 'euc-kr']:
            try:
                self.df = pd.read_csv(self.csv_path, encoding=encoding)
                logger.info(f"  - {self.domain_name} CSV 로드 성공 ({encoding}): {len(self.df)} 행")
                return
            except UnicodeDecodeError:
                continue
        logger.error(f"❌ 모든 인코딩으로 CSV 파일 로드 실패: {self.csv_path}")
        self.df = pd.DataFrame()

    def _init_agent(self):
        if self.df is None or self.df.empty:
            logger.warning(f"⚠️ {self.domain_name} 데이터프레임이 비어있어 Agent를 초기화할 수 없습니다.")
            return
        
        llm = ChatOpenAI(model=self.llm_model, temperature=self.llm_temperature)
        
        self.agent = create_pandas_dataframe_agent(
            llm, 
            self.df, 
            prefix=AGENT_PROMPT_PREFIX_V2,
            verbose=False, 
            allow_dangerous_code=True
        )

    def search_chunks(self, query: str) -> List[ChunkResult]:
        if not self.agent:
            return []
            
        try:
            cached_result = self._get_cached_result(query)
            if cached_result:
                return [self._create_chunk_result(cached_result)]
            
            contextual_query = f"Context: {self.data_context}\n\nUser Question: {query}"
            
            # 🔥 [최종 수정] LangChain 권장 방식 적용
            # 1. try-except OutputParsingError 구문 제거
            # 2. agent.invoke 호출 시 handle_parsing_errors=True 옵션을 반드시 추가
            agent_response = self.agent.invoke(
                {"input": contextual_query},
                handle_parsing_errors=True  # 이 옵션이 핵심입니다.
            )
            
            # 이제 파싱 오류가 발생해도 agent_response['output']에 원본 텍스트가 담겨 반환됩니다.
            answer = agent_response.get('output', f"{self.domain_name} 정보를 조회하지 못했습니다.")

            self._cache_result(query, answer)
            return [self._create_chunk_result(answer)]
            
        except Exception as e:
            # 이제 이곳은 정말 예상치 못한 심각한 오류가 발생했을 때만 실행됩니다.
            logger.error(f"❌ {self.domain_name} 분석 중 심각한 오류 발생: {e}")
            return []

    # --- 나머지 헬퍼 메서드는 변경 없음 ---
    def _get_cached_result(self, query: str) -> Optional[str]:
        query_hash = hashlib.md5(query.encode()).hexdigest()
        if query_hash in self.cache:
            result, timestamp = self.cache[query_hash]
            if time.time() - timestamp < self.cache_ttl_seconds:
                return result
            else:
                del self.cache[query_hash]
        return None

    def _cache_result(self, query: str, result: str):
        if len(self.cache) >= 100:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
        query_hash = hashlib.md5(query.encode()).hexdigest()
        self.cache[query_hash] = (result, time.time())

    def _create_chunk_result(self, content: str) -> ChunkResult:
        return ChunkResult(
            chunk=TextChunk(
                content=content,
                metadata={
                    "source": f"{self.domain_name}_analysis",
                    "handler": self.domain_name,
                    "data_source": self.csv_path.name
                }
            ),
            confidence=self.confidence,
            domain=self.domain_name
        )
