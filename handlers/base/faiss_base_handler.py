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
        
        # 🔥 [핵심 추가] 설정 파일에서 검색 타입(mmr or similarity)을 읽어옵니다.
        self.search_type = handler_settings.get('search_type', common_settings.get('search_type', 'similarity'))
        
        # =============================================================================
        # ⚙️ 2. 내부 변수 및 IndexManager 초기화
        # =============================================================================
        self.index_manager = get_index_manager()
        
        logger.info(f"✅ {self.__class__.__name__} v1.0 초기화 완료 (도메인: {self.domain_name}, K={self.search_k}, 검색타입: {self.search_type})")

# handlers/base/faiss_base_handler.py

    def search_chunks(self, query: str) -> List[ChunkResult]:
        """
        🎯 CentralOrchestrator와 연동되는 메인 실행 메서드.
        (수정) 설정된 search_type에 따라 MMR 또는 유사도 검색을 동적으로 수행합니다.
        """
        try:
            # 1. IndexManager로부터 벡터 저장소를 가져옵니다. (변경 없음)
            vectorstore = self.index_manager.get_vectorstore(self.domain_name)
            if not vectorstore:
                logger.warning(f"⚠️ {self.domain_name} 벡터스토어를 사용할 수 없습니다.")
                return []

            chunk_results = []

            # =========================================================================
            # 🔥 핵심 변경: self.search_type 값에 따라 분기 처리
            # =========================================================================

            if self.search_type == "mmr":
                # --- 2-A. MMR 검색 로직 ---
                logger.debug(f"Executing MMR search for domain '{self.domain_name}' with k={self.search_k}")
                retriever = vectorstore.as_retriever(
                    search_type="mmr",
                    search_kwargs={'k': self.search_k}
                )
                docs = retriever.invoke(query)
                
                # --- 3-A. MMR 결과 변환 (순위 기반 신뢰도) ---
                for i, doc in enumerate(docs):
                    # MMR은 거리 점수를 반환하지 않으므로, 순위에 따라 신뢰도를 계산합니다.
                    # 예: 1위=1.0, 2위=0.95, 3위=0.9 ...
                    confidence = max(0, 1.0 - (i * 0.05))

                    chunk_results.append(ChunkResult(
                        chunk=TextChunk(content=doc.page_content, metadata=doc.metadata),
                        confidence=confidence,
                        domain=self.domain_name,
                        metadata={"rank": i + 1} # raw_distance는 없으므로 제거
                    ))

            else: # 기본값 또는 'similarity'로 설정된 경우
                # --- 2-B. 기존 유사도 검색 로직 ---
                logger.debug(f"Executing similarity search for domain '{self.domain_name}' with k={self.search_k}")
                docs_with_scores = vectorstore.similarity_search_with_score(
                    query, k=self.search_k
                )
                
                # --- 3-B. 유사도 검색 결과 변환 (거리 기반 신뢰도) ---
                for i, (doc, distance) in enumerate(docs_with_scores):
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
            return []
