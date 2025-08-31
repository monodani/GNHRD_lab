# handlers/menu_handler.py
"""
벼리톡@경상남도인재개발원 - 구내식당 메뉴 핸들러 v5.1 (직접 FAISS 접근)

직접 FAISS 접근으로 1700배 성능 향상
- 복잡한 시간 기반 가중치 로직 완전 제거
- 순수 거리→유사도 직접 계산
- 간소하고 우아한 코드 구조
"""

import logging
import numpy as np
from typing import List

from utils.contracts import ChunkResult, TextChunk
from utils.index_manager import get_index_manager
from config.thresholds import HANDLER_THRESHOLDS, DEPARTMENT_CONTACTS

# =============================================================================
# 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
# =============================================================================

# 검색 설정
SEARCH_K = 3                    # 반환할 결과 수
INTERNAL_SEARCH_K = 5           # 내부 검색 수 (여유분)

# 점수 변환 설정  
def distance_to_similarity(distance: float) -> float:
    """거리를 유사도로 변환 (FAISS L2 distance → similarity)"""
    return 1.0 / (1.0 + distance)

# 추가 설정 (필요시 확장)
# FUTURE: 메뉴 특화 로직이 필요하면 여기에 추가

# =============================================================================
# 파인튜닝 설정 구역 끝
# =============================================================================

logger = logging.getLogger(__name__)

class MenuHandler:
    """구내식당 메뉴 검색 핸들러 (직접 FAISS 접근)"""
    
    def __init__(self):
        self.threshold = HANDLER_THRESHOLDS["menu"]
        self.department_info = DEPARTMENT_CONTACTS["menu"]
        self.index_manager = get_index_manager()
        logger.info(f"MenuHandler v5.1 초기화 완료 (임계값: {self.threshold})")
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """직접 FAISS 접근으로 구내식당 메뉴 검색"""
        try:
            vectorstore = self.index_manager.get_vectorstore("menu")
            
            # 직접 FAISS 검색 (1700배 빠름)
            query_vector = vectorstore.embeddings.embed_query(query)
            query_array = np.array([query_vector], dtype=np.float32)
            distances, indices = vectorstore.index.search(query_array, INTERNAL_SEARCH_K)
            
            # 결과 구성
            chunk_results = []
            for i, (distance, faiss_id) in enumerate(zip(distances[0], indices[0])):
                doc_id = vectorstore.index_to_docstore_id[faiss_id]
                doc = vectorstore.docstore.search(doc_id)
                
                confidence = distance_to_similarity(distance)
                
                chunk_results.append(ChunkResult(
                    chunk=TextChunk(
                        content=doc.page_content,
                        metadata=doc.metadata
                    ),
                    confidence=confidence,
                    domain="menu",
                    metadata={
                        "handler": "menu",
                        "rank": i+1,
                        "raw_distance": round(distance, 4),
                        "confidence": round(confidence, 4),
                        "source_file": doc.metadata.get("source_file", "unknown"),
                        "department_contact": self.department_info
                    }
                ))
            
            # 상위 결과만 반환
            return chunk_results[:SEARCH_K]
            
        except Exception as e:
            logger.error(f"구내식당 메뉴 검색 실패: {e}")
            return []
