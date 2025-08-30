# handlers/general_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 일반 정보 핸들러 v4.0
Architecture.md 기반 검색 전용 핸들러

핵심 기능:
- 검색만 담당 (LLM 호출 없음)
- 절대적 Confidence 기반 (FAISS distance → similarity 변환)
- 최소 지능형: 문서 타입 감지 (규정/연락처/운영계획)
- 메타데이터 보강으로 사용자 경험 향상
- 파인튜닝 편의성 극대화

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-20
"""

import logging
from typing import List, Dict, Any, Optional
from utils.contracts import ChunkResult, TextChunk
from utils.index_manager import get_index_manager
from config.thresholds import HANDLER_THRESHOLDS, DEPARTMENT_CONTACTS

# =============================================================================
# 로거 설정
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# GeneralHandler 클래스
# =============================================================================

class GeneralHandler:
    """
    일반 정보 검색 핸들러
    
    처리 범위:
    - 학칙+전결규정 (hakchik.pdf)
    - 업무담당자 연락처 (task_telephone.csv)
    - 운영평가계획 (operation_test.pdf)
    """
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
    # ================================================================
    
    # 문서 타입별 키워드 (최소 지능형)
    REGULATIONS_KEYWORDS = ["학칙", "규정", "조항", "제", "전결", "감점", "기준"]
    CONTACT_KEYWORDS = ["담당자", "연락처", "부서", "전화", "업무", "담당"]
    OPERATIONS_KEYWORDS = ["운영", "계획", "평가", "절차", "시행", "방침"]
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 끝
    # ================================================================
    
    def __init__(self):
        """GeneralHandler 초기화"""
        self.threshold = HANDLER_THRESHOLDS["general"]  # 0.42
        self.department_info = DEPARTMENT_CONTACTS["general"]
        self.index_manager = get_index_manager()
        
        logger.info(f"✅ GeneralHandler 초기화 완료 (임계값: {self.threshold})")
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """
        일반 정보 검색 전용 메서드

        Returns:
            List[ChunkResult]: 검색 결과 (상위 3개)
        """
        try:
            # 1. FAISS 검색 수행
            vectorstore = self.index_manager.get_vectorstore("general")
            docs_with_scores = vectorstore.similarity_search_with_score(query, k=5)

            if not docs_with_scores:
                logger.warning("일반 정보 검색 결과가 없습니다.")
                return []

            # 2. 쿼리 타입 분석 (최소 지능형)
            preferred_type = self._analyze_query_type(query)

            # =========================
            # [MOD] 점수모드 자동감지 + 유사도 변환 함수 정의
            # - raw score가 1.0을 초과하는 값이 다수면 'distance'로 간주
            # - distance → similarity: 1 - min(d,1)
            # - similarity 이미 [0,1] 범위면 그대로 사용
            # =========================
            raw_scores = [s for _, s in docs_with_scores]
            over_one = sum(1 for s in raw_scores if s > 1.0)
            score_mode = "distance" if over_one >= max(1, len(raw_scores)//4) else "similarity"
            to_sim = (lambda s: 1.0 - min(s, 1.0)) if score_mode == "distance" else (lambda s: max(0.0, min(s, 1.0)))

            # 3. ChunkResult 생성 (유사도 기반)
            scored = []
            for i, (doc, raw_score) in enumerate(docs_with_scores, 1):
                # [MOD] 거리→유사도 단순 변환, rank 패널티 삭제
                similarity = to_sim(raw_score)
                confidence = similarity  # [MOD] confidence = similarity (0~1)

                # 나중 정렬을 위해 중간 구조로 보관
                scored.append((doc, raw_score, similarity, confidence))

            # =========================
            # [MOD] 유사도 내림차순 정렬
            # =========================
            scored.sort(key=lambda x: x[2], reverse=True)

            # 상위 3개만 반환 (정책 유지)
            top = scored[:3]
            chunk_results: List[ChunkResult] = []
            for rank, (doc, raw_score, similarity, confidence) in enumerate(top, start=1):
                chunk_results.append(ChunkResult(
                    chunk=TextChunk(content=doc.page_content, metadata=doc.metadata),
                    confidence=confidence,
                    domain="general",
                    search_method="faiss",
                    metadata=self._create_general_metadata(
                        doc=doc,
                        rank=rank,
                        distance_score=raw_score,       # 원시 점수 그대로 유지
                        similarity_score=similarity,    # 변환된 유사도(0~1)
                        preferred_type=preferred_type
                    ) | {"score_mode": score_mode}       # [MOD] 모드 기록(디버깅/튜닝용)
                ))

            # [MOD] 로그에 모드/탑유사도 추가
            logger.info(
                f"일반 정보 검색 완료: {len(chunk_results)}개 반환 "
                f"(score_mode={score_mode}, top_similarity={chunk_results[0].confidence:.3f})"
            )
            return chunk_results

        except Exception as e:
            logger.error(f"일반 정보 검색 실패: {e}")
            return []
    
    def _analyze_query_type(self, query: str) -> Optional[str]:
        """
        쿼리에서 선호하는 문서 타입 분석 (최소 지능형)
        
        Args:
            query: 사용자 질문
            
        Returns:
            Optional[str]: "regulations", "contact", "operations", 또는 None
        """
        query_lower = query.lower()
        
        # regulations 키워드 체크
        if any(keyword in query_lower for keyword in self.REGULATIONS_KEYWORDS):
            return "regulations"
        
        # contact 키워드 체크
        if any(keyword in query_lower for keyword in self.CONTACT_KEYWORDS):
            return "contact"
        
        # operations 키워드 체크
        if any(keyword in query_lower for keyword in self.OPERATIONS_KEYWORDS):
            return "operations"
        
        return None
    
    def _distance_to_similarity(self, distance: float) -> float:
        """
        FAISS 거리를 유사도로 변환
        
        Args:
            distance: FAISS 거리 점수
            
        Returns:
            float: 유사도 점수 (0.0-1.0)
        """
        similarity = 1.0 / (1.0 + distance)
        
        # 추가 정규화
        if distance <= 0.1:  # 매우 유사
            similarity = max(0.9, similarity)
        elif distance >= 2.0:  # 매우 다름
            similarity = min(0.3, similarity)
        
        return max(0.0, min(1.0, similarity))
    
    def _create_general_metadata(
        self, 
        doc, 
        rank: int, 
        distance_score: float, 
        similarity_score: float,
        preferred_type: Optional[str]
    ) -> Dict[str, Any]:
        """
        일반 정보 특화 메타데이터 생성
        
        Args:
            doc: 검색된 문서
            rank: 검색 순위
            distance_score: FAISS 거리 점수
            similarity_score: 변환된 유사도 점수
            preferred_type: 감지된 선호 문서 타입
            
        Returns:
            Dict: 일반 정보 특화 메타데이터
        """
        base_metadata = doc.metadata.copy()
        
        # 문서 타입별 특화 정보 추가
        doc_category = base_metadata.get('category', 'general')
        
        # 담당부서 정보 (문서 타입에 따라 세분화)
        if doc_category == 'regulations':
            department_detail = "학칙 및 규정 관련"
        elif doc_category == 'contact':
            department_detail = "업무담당자 연락처"
        elif doc_category == 'operations':
            department_detail = "운영 및 평가계획"
        else:
            department_detail = self.department_info["description"]
        
        # 일반 핸들러 특화 정보 추가
        base_metadata.update({
            "department": self.department_info["department"],
            "contact": self.department_info["phone"],
            "description": department_detail,
            "rank": rank,
            "distance_score": distance_score,
            "similarity_score": similarity_score,
            "handler_type": "general",
            "threshold": self.threshold,
            "preferred_type": preferred_type,
            "document_category": doc_category
        })
        
        return base_metadata

# =============================================================================
# 편의 함수들
# =============================================================================

def create_general_handler() -> GeneralHandler:
    """
    GeneralHandler 인스턴스 생성 편의 함수
    
    Returns:
        GeneralHandler: 일반 정보 핸들러 인스턴스
    """
    return GeneralHandler()

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 일반 정보 핸들러 테스트 ===")
    
    try:
        # 핸들러 초기화 테스트
        handler = GeneralHandler()
        print(f"✅ 핸들러 초기화: 임계값 = {handler.threshold}")
        
        # 문서 타입 분석 테스트
        test_queries = [
            "학칙 제5조 내용은?",           # regulations
            "교육기획담당 연락처는?",        # contact
            "운영계획 절차 알려줘",         # operations
            "인재개발원 정보 궁금해",       # general
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n--- 테스트 {i}: {query} ---")
            
            # 문서 타입 분석 테스트
            detected = handler._analyze_query_type(query)
            print(f"감지된 문서 타입: {detected or '일반'}")
            
            try:
                results = handler.search_chunks(query)
                print(f"검색 결과: {len(results)}개")
                
                for j, result in enumerate(results):
                    print(f"  {j+1}. confidence: {result.confidence:.3f}")
                    print(f"     domain: {result.domain}")
                    print(f"     category: {result.chunk.metadata.get('category', 'unknown')}")
                    print(f"     content: {result.chunk.content[:100]}...")
                    
            except Exception as e:
                print(f"❌ 검색 테스트 실패: {e}")
        
        print("\n🎉 모든 테스트 완료!")
        
    except Exception as e:
        print(f"\n❌ 핸들러 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
