# handlers/base/faiss_base_handler.py
"""
벼리톡@경상남도인재개발원 - FAISS 기반 핸들러 v1.0 (리팩토링)
모든 FAISS 벡터 검색 핸들러의 공통 로직을 포함하는 부모 클래스

설계 원칙:
- DRY(Don't Repeat Yourself): 중복 코드를 제거하고 상속을 통해 재사용
- 설정 중앙화: 모든 설정값은 config.py에서 로드
- 단일 책임: 이 클래스는 IndexManager로부터 Vectorstore를 받아 검색하고 결과를 반환하는 책임만 가짐

작성자: 이다니엘 from 경상남도인재개발원 (Gemini AI 리팩토링)
최종 수정: 2025-09-08
"""
import logging
from typing import List

# --- 프로젝트 모듈 ---
from utils.contracts import ChunkResult, TextChunk
from utils.index_manager import get_index_manager
from config.config import get_config

logger = logging.getLogger(__name__)

class BaseFaissHandler:
    """
    FAISS 핸들러의 모든 공통 기능을 제공하는 부모 클래스
    자식 클래스는 __init__에서 자신의 domain_name만 지정해주면 됩니다.
    """

    def __init__(self, domain_name: str):
        """
        핸들러 초기화. 중앙 설정(config.py)에서 모든 정보를 가져옵니다.

        Args:
            domain_name (str): 핸들러의 고유 도메인 이름 (예: 'general')
        """
        # =============================================================================
        # 🔧 1. 설정값 로드 (중앙 관리)
        # =============================================================================
        config = get_config()

        # --- 핸들러 공통 설정 ---
        common_settings = config.HANDLER_SETTINGS['faiss']
        self.confidence_function = common_settings['confidence_function']

        # --- 핸들러 개별 설정 (config에 개별 k값이 없으면 공통 기본값 사용) ---
        handler_settings = config.HANDLER_SETTINGS.get(domain_name, {})
        self.domain_name = domain_name
        self.search_k = handler_settings.get('k', common_settings['default_k'])
        
        # =============================================================================
        # ⚙️ 2. 내부 변수 및 IndexManager 초기화
        # =============================================================================
        self.index_manager = get_index_manager()
        
        logger.info(f"✅ {self.__class__.__name__} v1.0 초기화 완료 (도메인: {self.domain_name}, K={self.search_k})")

    def search_chunks(self, query: str) -> List[ChunkResult]:
        """
        🎯 CentralOrchestrator와 연동되는 메인 실행 메서드.
        Vectorstore 로드 -> 유사도 검색 -> ChunkResult 변환의 흐름을 따릅니다.
        """
        try:
            # 1. IndexManager로부터 해당 도메인의 벡터 저장소(FAISS)를 가져옴
            vectorstore = self.index_manager.get_vectorstore(self.domain_name)
            if not vectorstore:
                logger.warning(f"⚠️ {self.domain_name} 벡터스토어를 사용할 수 없습니다.")
                return []
            
            # 2. 🔥 핵심 알고리즘: FAISS 유사도 검색 실행 (거리 점수 포함)
            docs_with_scores = vectorstore.similarity_search_with_score(
                query, k=self.search_k
            )
            
            # 3. ✅ 검색 결과를 표준화된 ChunkResult 객체 리스트로 변환
            chunk_results = []
            for i, (doc, distance) in enumerate(docs_with_scores):
                # '거리(distance)'를 '신뢰도(confidence)' 점수로 변환 (0~1)
                confidence = self.confidence_function(distance)
                
                chunk_results.append(ChunkResult(
                    chunk=TextChunk(content=doc.page_content, metadata=doc.metadata),
                    confidence=confidence,
                    domain=self.domain_name,
                    metadata={"rank": i + 1, "raw_distance": distance}
                ))
            
            return chunk_results
            
        except Exception as e:
            logger.error(f"❌ {self.domain_name} 검색 실패: {e}")
            return [] # 실패 시 빈 리스트 반환
