# handlers/base/pandas_base_handler.py (v1.4 - 최종 완성)
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

logger = logging.getLogger(__name__)

# Pandas Agent의 역할을 스마트하게 지시하는 프롬프트
AGENT_PROMPT_PREFIX_V2 = """
You are a data analysis assistant working with a pandas DataFrame.
Your primary goal is to extract relevant data and provide a clear, concise, text-based answer to the user's question.

Follow these rules STRICTLY:
1.  **Analyze First:** Understand the user's question and determine what data is needed from the DataFrame.
2.  **Text-Only Output:** Your final answer MUST BE plain text. DO NOT generate plots, visualizations, or Python code in the final output.
3.  **Handle Analytical Queries Smartly:** For questions about "trends," "changes," "comparisons," or "summaries," you MUST find the underlying raw data that would be used for such analysis and present it clearly. A markdown table is an excellent format for this.
4.  **Be Honest About Missing Data:** If the data to answer the question is not available in the DataFrame, you MUST state that clearly. For example: "The DataFrame does not contain data for [topic]."
5.  **Simple Questions, Simple Answers:** For simple lookup questions (e.g., "What is the satisfaction score for course X?"), provide the direct answer.
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
        
        # 🔥 [핵심 복원] 데이터 로드 및 Agent 생성 호출
        self._load_data()
        self._init_agent()
        
        logger.info(f"✅ {self.__class__.__name__} v1.4 초기화 완료 (도메인: {self.domain_name})")

    # 🔥 [핵심 복원] _load_data 메서드의 전체 구현
    def _load_data(self):
        """CSV 데이터 로드 (UTF-8, CP949, EUC-KR 순서로 인코딩 자동 감지)"""
        if not self.csv_path.exists():
            # 파일이 없을 경우 에러를 발생시키는 대신, 경고를 기록하고 빈 데이터프레임으로 초기화
            logger.warning(f"⚠️ 데이터 파일을 찾을 수 없습니다: {self.csv_path}. 핸들러가 비활성화 상태로 작동합니다.")
            self.df = pd.DataFrame() # 빈 데이터프레임
            return

        for encoding in ['utf-8', 'cp949', 'euc-kr']:
            try:
                self.df = pd.read_csv(self.csv_path, encoding=encoding)
                logger.info(f"  - {self.domain_name} CSV 로드 성공 ({encoding}): {len(self.df)} 행")
                return
            except UnicodeDecodeError:
                continue
        
        logger.error(f"❌ 모든 인코딩으로 CSV 파일 로드 실패: {self.csv_path}")
        self.df = pd.DataFrame() # 로드 실패 시에도 빈 데이터프레임으로 초기화

    def _init_agent(self):
        """LangChain Pandas DataFrame Agent 초기화"""
        # 데이터프레임이 비어있으면 Agent를 초기화하지 않고 경고만 남김
        if self.df is None or self.df.empty:
            logger.warning(f"⚠️ {self.domain_name} 데이터프레임이 비어있어 Agent를 초기화할 수 없습니다.")
            return
        
        llm = ChatOpenAI(model=self.llm_model, temperature=self.llm_temperature)
        
        self.agent = create_pandas_dataframe_agent(
            llm, 
            self.df, 
            prefix=AGENT_PROMPT_PREFIX_V2,
            verbose=False, 
            allow_dangerous_code=True,
            handle_parsing_errors=True 
        )

    def search_chunks(self, query: str) -> List[ChunkResult]:
        # Agent가 성공적으로 초기화되었는지 먼저 확인
        if not self.agent:
            logger.warning(f"⚠️ {self.domain_name} Agent가 초기화되지 않아 검색을 건너뜁니다.")
            return []
            
        try:
            cached_result = self._get_cached_result(query)
            if cached_result:
                return [self._create_chunk_result(cached_result)]
            
            contextual_query = f"Context: {self.data_context}\n\nUser Question: {query}"
            
            agent_response = self.agent.invoke(contextual_query)
            answer = agent_response.get('output', f"{self.domain_name} 정보를 조회하지 못했습니다.")
            
            self._cache_result(query, answer)
            return [self._create_chunk_result(answer)]
            
        except Exception as e:
            logger.error(f"❌ {self.domain_name} 분석 실패: {e}")
            return []

    # 🔥 [핵심 복원] 나머지 헬퍼 메서드들의 전체 구현
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
