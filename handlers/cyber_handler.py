# handlers/cyber_handler.py
"""
벼리톡@경상남도인재개발원 - 사이버교육 핸들러 v6.0 (순수 pandas agent)
CSV 데이터 기반 실시간 분석 + 캐시 시스템

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-09-04
"""

import logging
import hashlib
import time
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional

from utils.contracts import ChunkResult, TextChunk
from langchain_experimental.agents import create_pandas_dataframe_agent
from langchain_openai import ChatOpenAI

# =============================================================================
# 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
# =============================================================================

# 파일 경로
CSV_PATH = "data/cyber/cyber.csv"
CSV_ENCODINGS = ['utf-8', 'cp949', 'euc-kr']

# LLM 설정
LLM_MODEL = "gpt-4o"
LLM_TEMPERATURE = 0.1
AGENT_TIMEOUT = 20  # 복잡한 질문 기준

# 캐시 설정
CACHE_TTL_SECONDS = 3600  # 1시간
MAX_CACHE_SIZE = 100

# 메시지
FALLBACK_MESSAGE = "현재 사이버교육 정보를 확인할 수 없습니다. 잠시 후 다시 시도하거나 경남인재개발원으로 직접 문의해주세요."

# =============================================================================

logger = logging.getLogger(__name__)

class CyberHandler:
    """사이버교육 데이터 분석 핸들러 (pandas agent)"""
    
    def __init__(self):
        self.df = None
        self.agent = None
        self.cache = {}  # {query_hash: (result, timestamp)}
        self._load_data()
        self._init_agent()
        logger.info("CyberHandler v6.0 초기화 완료")
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """🎯 base_handler 연동 지점: pandas agent 실행"""
        try:
            # 캐시 확인
            cached_result = self._get_cached_result(query)
            if cached_result:
                return [self._create_chunk_result(cached_result)]
            
            # 🔥 핵심 알고리즘: pandas agent 실행
            agent_response = self.agent.invoke(query, handle_parsing_errors=True)
            answer = agent_response['output']
            
            # 캐시 저장
            self._cache_result(query, answer)
            
            # ✅ base_handler가 수집할 ChunkResult 반환
            return [self._create_chunk_result(answer)]
            
        except Exception as e:
            logger.error(f"사이버교육 분석 실패: {e}")
            return [self._create_chunk_result(FALLBACK_MESSAGE)]
    
    def _load_data(self):
        """CSV 데이터 로드"""
        csv_path = Path(CSV_PATH)
        
        for encoding in CSV_ENCODINGS:
            try:
                self.df = pd.read_csv(csv_path, encoding=encoding)
                logger.info(f"CSV 로드 성공 ({encoding}): {len(self.df)}개 과정")
                return
            except (UnicodeDecodeError, FileNotFoundError):
                continue
        
        raise Exception(f"CSV 파일 로드 실패: {csv_path}")
    
    def _init_agent(self):
        """pandas agent 초기화"""
        llm = ChatOpenAI(model=LLM_MODEL, temperature=LLM_TEMPERATURE)
        self.agent = create_pandas_dataframe_agent(
            llm, self.df, verbose=False, allow_dangerous_code=True
        )
    
    def _get_cached_result(self, query: str) -> Optional[str]:
        """캐시에서 결과 조회"""
        query_hash = hashlib.md5(query.encode()).hexdigest()
        
        if query_hash in self.cache:
            result, timestamp = self.cache[query_hash]
            if time.time() - timestamp < CACHE_TTL_SECONDS:
                return result
            else:
                del self.cache[query_hash]
        
        return None
    
    def _cache_result(self, query: str, result: str):
        """결과 캐싱"""
        # 캐시 크기 제한
        if len(self.cache) >= MAX_CACHE_SIZE:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
        
        query_hash = hashlib.md5(query.encode()).hexdigest()
        self.cache[query_hash] = (result, time.time())
    
    def _create_chunk_result(self, content: str) -> ChunkResult:
        """pandas agent 결과를 ChunkResult로 변환"""
        return ChunkResult(
            chunk=TextChunk(
                content=content,
                metadata={
                    "source": "cyber_analysis", 
                    "handler": "cyber",
                    "data_source": "cyber.csv"
                }
            ),
            confidence=0.5,  # 의미없는 고정값
            domain="cyber"
        )
