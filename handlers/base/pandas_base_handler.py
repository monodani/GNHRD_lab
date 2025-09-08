# handlers/base/pandas_base_handler.py (v1.3 - 스마트 프롬프트)
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

# 🔥 [핵심 수정] Pandas Agent의 역할을 더욱 스마트하게 지시하는 프롬프트
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
        
        self._load_data()
        self._init_agent()
        
        logger.info(f"✅ {self.__class__.__name__} v1.3 초기화 완료 (도메인: {self.domain_name})")

    def _init_agent(self):
        """LangChain Pandas DataFrame Agent 초기화 (스마트 프롬프트 적용)"""
        if self.df is None:
            raise ValueError("데이터프레임이 로드되지 않아 Agent를 초기화할 수 없습니다.")
        
        llm = ChatOpenAI(model=self.llm_model, temperature=self.llm_temperature)
        
        # 🔥 [핵심 수정] Agent 생성 시, 새로운 스마트 프롬프트(V2)를 주입
        self.agent = create_pandas_dataframe_agent(
            llm, 
            self.df, 
            prefix=AGENT_PROMPT_PREFIX_V2, # 스마트 프롬프트 주입
            verbose=False, 
            allow_dangerous_code=True,
            # 파싱 오류 발생 시 Agent가 스스로 재시도하도록 설정 (안정성 강화)
            handle_parsing_errors=True 
        )

    def search_chunks(self, query: str) -> List[ChunkResult]:
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

    # (이하 나머지 코드는 변경 없습니다)
    def _load_data(self):
        # ... (이전과 동일)
        pass
    def _get_cached_result(self, query: str) -> Optional[str]:
        # ... (이전과 동일)
        pass
    def _cache_result(self, query: str, result: str):
        # ... (이전과 동일)
        pass
    def _create_chunk_result(self, content: str) -> ChunkResult:
        # ... (이전과 동일)
        pass
