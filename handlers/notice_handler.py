# handlers/notice_handler.py
"""
벼리톡@경상남도인재개발원 - 공지사항 핸들러 v1.0

교육 관련 공지사항, 알림, 안내사항 검색
코랩 테스트 검증 완료 (5/5 성공, confidence: 0.422~0.489)
"""

# =============================================================================
# 🔧 파인튜닝 설정 구역 - 모든 조정값을 여기서 관리
# =============================================================================

SEARCH_K = 3                    # 반환할 검색 결과 수
DOMAIN = "notice"               # 핸들러 도메인명

# Confidence 변환 함수 (코랩 검증 완료)
def distance_to_confidence(distance: float) -> float:
    """거리를 confidence로 변환 (0.0-1.0)"""
    return 1.0 / (1.0 + distance)

# =============================================================================

import logging
from typing import List

from utils.contracts import ChunkResult, TextChunk
from utils.index_manager import get_index_manager

logger = logging.getLogger(__name__)

class NoticeHandler:
    """공지사항 검색 핸들러"""
    
    def __init__(self):
        self.domain = DOMAIN
        self.search_k = SEARCH_K
        self.index_manager = get_index_manager()
        logger.info(f"NoticeHandler 초기화 완료 (k={self.search_k})")
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """공지사항 검색 메인 메서드"""
        try:
            vectorstore = self.index_manager.get_vectorstore(self.domain)
            if not vectorstore:
                logger.warning("공지사항 벡터스토어를 사용할 수 없습니다")
                return []
            
            # FAISS 검색 실행 (코랩 검증된 로직)
            docs_with_scores = vectorstore.similarity_search_with_score(
                query, k=self.search_k
            )
            
            if not docs_with_scores:
                return []
            
            # ChunkResult 생성
            chunk_results = []
            for i, (doc, distance) in enumerate(docs_with_scores):
                confidence = distance_to_confidence(distance)
                
                chunk_results.append(ChunkResult(
                    chunk=TextChunk(
                        content=doc.page_content,
                        metadata=doc.metadata
                    ),
                    confidence=confidence,
                    domain=self.domain,
                    metadata={
                        "rank": i + 1,
                        "raw_distance": distance,
                        "handler": "notice"
                    }
                ))
            
            logger.info(f"공지사항 검색 완료: {len(chunk_results)}개 결과")
            return chunk_results
            
        except Exception as e:
            logger.error(f"공지사항 검색 실패: {e}")
            return []
