# handlers/base/pandas_base_handler.py
"""
벼리톡@경상남도인재개발원 - Pandas Agent 기반 핸들러 v1.0 (리팩토링)
모든 Pandas Agent 핸들러의 공통 로직을 포함하는 부모 클래스

설계 원칙:
- DRY(Don't Repeat Yourself): 중복 코드를 제거하고 상속을 통해 재사용
- 설정 중앙화: 모든 설정값은 config.py에서 로드
- 단일 책임: 이 클래스는 CSV 데이터를 로드하고, Agent를 실행하며, 결과를 캐싱하는 책임만 가짐

작성자: 이다니엘 from 경상남도인재개발원 (Gemini AI 리팩토링)
최종 수정: 2025-09-08
"""
import logging
import hashlib
import time
import pandas as pd
from pathlib import Path
from typing import List, Optional

# --- 프로젝트 모듈 ---
from utils.contracts import ChunkResult, TextChunk
from config.config import get_config
from langchain_experimental.agents import create_pandas_dataframe_agent
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

class BasePandasAgentHandler:
    """
    Pandas Agent 핸들러의 모든 공통 기능을 제공하는 부모 클래스
    자식 클래스는 __init__에서 자신의 domain_name만 지정해주면 됩니다.
    """
    
    def __init__(self, domain_name: str):
        """
        핸들러 초기화. 중앙 설정(config.py)에서 모든 정보를 가져옵니다.

        Args:
            domain_name (str): 핸들러의 고유 도메인 이름 (예: 'course_satisfaction')
        """
        # =============================================================================
        # 🔧 1. 설정값 로드 (중앙 관리)
        # =============================================================================
        config = get_config()
        
        # --- 핸들러 공통 설정 ---
        common_settings = config.HANDLER_SETTINGS['pandas_agent']
        self.llm_model = common_settings['llm_model']
        self.llm_temperature = common_settings['llm_temperature']
        self.cache_ttl_seconds = common_settings['cache_ttl_seconds']
        self.confidence = common_settings['confidence_score']
        
        # --- 핸들러 개별 설정 ---
        handler_settings = config.HANDLER_SETTINGS[domain_name]
        self.domain_name = domain_name
        self.csv_path = Path(handler_settings['csv_path'])
        self.cache_key_prefix = handler_settings.get('cache_key_prefix', '') # 특정 핸들러만 사용
        
        # =============================================================================
        # ⚙️ 2. 내부 변수 및 Agent 초기화
        # =============================================================================
        self.df: Optional[pd.DataFrame] = None
        self.agent = None
        self.cache: dict = {}  # In-memory cache {query_hash: (result, timestamp)}
        
        # 🔥 핵심 로직: 데이터 로드 및 Agent 생성
        self._load_data()
        self._init_agent()
        
        logger.info(f"✅ {self.__class__.__name__} v1.0 초기화 완료 (도메인: {self.domain_name})")

    def search_chunks(self, query: str) -> List[ChunkResult]:
        """
        🎯 CentralOrchestrator와 연동되는 메인 실행 메서드.
        캐시 확인 -> Agent 실행 -> 결과 캐싱 -> ChunkResult 반환의 흐름을 따릅니다.
        """
        try:
            # 1. 캐시 확인
            cached_result = self._get_cached_result(query)
            if cached_result:
                logger.info(f"⚡️ 캐시 히트: ({self.domain_name})")
                return [self._create_chunk_result(cached_result)]
            
            # 2. 🔥 핵심 알고리즘: pandas agent 실행 (파싱 오류 발생 시에도 안전하게 처리)
            agent_response = self.agent.invoke(query, handle_parsing_errors=True)
            answer = agent_response.get('output', f"{self.domain_name} 정보를 조회하지 못했습니다.")
            
            # 3. 캐시 저장
            self._cache_result(query, answer)
            
            # 4. ✅ base_handler가 수집할 ChunkResult 형태로 변환하여 반환
            return [self._create_chunk_result(answer)]
            
        except Exception as e:
            logger.error(f"❌ {self.domain_name} 분석 실패: {e}")
            return [] # 실패 시 빈 리스트 반환

    def _load_data(self):
        """CSV 데이터 로드 (UTF-8, CP949, EUC-KR 순서로 인코딩 자동 감지)"""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"데이터 파일을 찾을 수 없습니다: {self.csv_path}")

        for encoding in ['utf-8', 'cp949', 'euc-kr']:
            try:
                self.df = pd.read_csv(self.csv_path, encoding=encoding)
                logger.info(f"  - {self.domain_name} CSV 로드 성공 ({encoding}): {len(self.df)} 행")
                return
            except UnicodeDecodeError:
                continue
        
        raise Exception(f"모든 인코딩으로 CSV 파일 로드 실패: {self.csv_path}")

    def _init_agent(self):
        """LangChain Pandas DataFrame Agent 초기화"""
        if self.df is None:
            raise ValueError("데이터프레임이 로드되지 않아 Agent를 초기화할 수 없습니다.")
        
        llm = ChatOpenAI(model=self.llm_model, temperature=self.llm_temperature)
        
        # 🔥 Agent 생성: LLM이 DataFrame을 다룰 수 있도록 설정
        self.agent = create_pandas_dataframe_agent(
            llm, self.df, verbose=False, allow_dangerous_code=True
        )

    def _get_cached_result(self, query: str) -> Optional[str]:
        """메모리 캐시에서 결과 조회"""
        query_hash = self.cache_key_prefix + hashlib.md5(query.encode()).hexdigest()
        
        if query_hash in self.cache:
            result, timestamp = self.cache[query_hash]
            if time.time() - timestamp < self.cache_ttl_seconds:
                return result
            else:
                del self.cache[query_hash]  # 만료된 캐시 삭제
        
        return None

    def _cache_result(self, query: str, result: str):
        """메모리 캐시에 결과 저장 (오래된 데이터는 자동 삭제)"""
        if len(self.cache) >= 100: # Max cache size
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
        
        query_hash = self.cache_key_prefix + hashlib.md5(query.encode()).hexdigest()
        self.cache[query_hash] = (result, time.time())

    def _create_chunk_result(self, content: str) -> ChunkResult:
        """Agent의 답변을 표준화된 ChunkResult 객체로 변환"""
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
