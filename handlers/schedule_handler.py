# handlers/schedule_handler.py
"""
벼리톡@경상남도인재개발원 - 교육 일정 핸들러 v6.0 (순수 pandas agent)
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
CSV_PATH = "data/schedule/schedule.csv"
CSV_ENCODINGS = ['cp949', 'utf-8', 'euc-kr']  # 코랩 테스트 결과 cp949 우선

# LLM 설정
LLM_MODEL = "gpt-4o"
LLM_TEMPERATURE = 0.1
AGENT_TIMEOUT = 20

# 캐시 설정 (충돌 방지를 위한 schedule_ 접두사)
CACHE_TTL_SECONDS = 3600  # 1시간
MAX_CACHE_SIZE = 100
CACHE_KEY_PREFIX = "schedule_"  # 다른 핸들러와 캐시 키 구분

# 메시지
FALLBACK_MESSAGE = "현재 교육 일정 정보를 확인할 수 없습니다. 잠시 후 다시 시도하거나 경남인재개발원(055-254-2051)으로 직접 문의해주세요."

# =============================================================================

logger = logging.getLogger(__name__)

class ScheduleHandler:
    """교육 일정 분석 핸들러 (pandas agent)"""
    
    def __init__(self):
        self.df = None
        self.agent = None
        self.cache = {}  # {query_hash: (result, timestamp)}
        self._load_data()
        self._init_agent()
        logger.info("ScheduleHandler v6.0 초기화 완료")
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """🎯 base_handler 연동 지점: pandas agent 실행"""
        try:
            # 캐시 확인
            cached_result = self._get_cached_result(query)
            if cached_result:
                return [self._create_chunk_result(cached_result)]
            
            # 🔥 핵심 알고리즘: pandas agent 실행 (파싱 오류 안전 처리)
            response = self.agent.invoke(query, handle_parsing_errors=True)
            answer = response.get('output', FALLBACK_MESSAGE)
            
            # 빈 답변 처리
            if not answer or answer.strip() == "":
                answer = FALLBACK_MESSAGE
            
            # 캐시 저장
            self._cache_result(query, answer)
            
            # ✅ base_handler가 수집할 ChunkResult 반환
            return [self._create_chunk_result(answer)]
            
        except Exception as e:
            logger.error(f"교육 일정 분석 실패: {e}")
            return [self._create_chunk_result(FALLBACK_MESSAGE)]
    
    def _load_data(self):
        """CSV 데이터 로드 (인코딩 자동 감지)"""
        csv_path = Path(CSV_PATH)
        
        for encoding in CSV_ENCODINGS:
            try:
                self.df = pd.read_csv(csv_path, encoding=encoding)
                logger.info(f"교육 일정 CSV 로드 성공 ({encoding}): {len(self.df)}개 일정")
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
        """캐시에서 결과 조회 (schedule_ 접두사로 키 구분)"""
        query_hash = CACHE_KEY_PREFIX + hashlib.md5(query.encode()).hexdigest()
        
        if query_hash in self.cache:
            result, timestamp = self.cache[query_hash]
            if time.time() - timestamp < CACHE_TTL_SECONDS:
                return result
            else:
                del self.cache[query_hash]
        
        return None
    
    def _cache_result(self, query: str, result: str):
        """결과 캐싱 (schedule_ 접두사로 키 구분)"""
        # 캐시 크기 제한
        if len(self.cache) >= MAX_CACHE_SIZE:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest_key]
        
        query_hash = CACHE_KEY_PREFIX + hashlib.md5(query.encode()).hexdigest()
        self.cache[query_hash] = (result, time.time())
    
    def _create_chunk_result(self, content: str) -> ChunkResult:
        """pandas agent 결과를 ChunkResult로 변환"""
        return ChunkResult(
            chunk=TextChunk(
                content=content,
                metadata={
                    "source": "schedule_analysis", 
                    "handler": "schedule",
                    "data_source": "schedule.csv",
                    "department": "인재양성과 교육기획담당",
                    "contact": "055-254-2051"
                }
            ),
            confidence=0.5,  # 의미없는 고정값 (base_handler에서 처리)
            domain="schedule"
        )
