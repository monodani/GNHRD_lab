# handlers/publish_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 발행물 핸들러 v4.0
Architecture.md 기반 검색 전용 핸들러

핵심 기능:
- 검색만 담당 (LLM 호출 없음)
- 절대적 Confidence 기반 (FAISS distance → similarity 변환)
- 공식 발행물 특성 고려한 단순화 방식
- 담당부서 자동 감지 및 연락처 제공
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
# PublishHandler 클래스
# =============================================================================

class PublishHandler:
    """
    발행물 검색 핸들러
    
    처리 범위:
    - 2025 교육훈련계획서 (2025plan.pdf)
    - 2024 종합평가서 (2024pyeongga.pdf)
    - 공식 발행물 정보 (정책, 계획, 성과, 통계 등)
    """
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
    # ================================================================
    
    # Confidence 가중치 설정 (단순화 방식)
    # 문서 타입 매칭 보너스는 제거됨 (순수 FAISS 유사도만 사용)
    
    # 담당부서 감지 키워드
    EVALUATION_KEYWORDS = ["평가", "만족도", "성과", "결과", "효과성", "분석"]
    PLANNING_KEYWORDS = ["계획", "목표", "방침", "전략", "운영", "일정"]
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 끝
    # ================================================================
    
    def __init__(self):
        """PublishHandler 초기화"""
        self.threshold = HANDLER_THRESHOLDS["publish"]  # 0.45
        self.department_info = DEPARTMENT_CONTACTS["publish"]
        self.index_manager = get_index_manager()
        
        logger.info(f"✅ PublishHandler 초기화 완료 (임계값: {self.threshold})")
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """
        발행물 검색 전용 메서드
        
        Args:
            query: 사용자 질문
            
        Returns:
            List[ChunkResult]: 검색 결과 (상위 3개)
        """
        try:
            # 1. FAISS 검색 수행
            vectorstore = self.index_manager.get_vectorstore("publish")
            docs_with_scores = vectorstore.similarity_search_with_score(query, k=5)
            
            if not docs_with_scores:
                logger.warning("발행물 검색 결과가 없습니다.")
                return []
            
            # 2. 담당부서 자동 감지
            detected_department = self._detect_content_category(query)
            
            # 3. ChunkResult 생성 (단순화 방식)
            chunk_results = []
            for i, (doc, distance_score) in enumerate(docs_with_scores):
                # 거리 → 유사도 변환
                similarity = self._distance_to_similarity(distance_score)
                
                # 순위 기반 미세 조정
                rank_penalty = i * 0.02  # 1등: 0, 2등: -0.02, 3등: -0.04, ...
                confidence = similarity - rank_penalty
                
                # confidence 범위 제한
                confidence = max(0.0, min(1.0, confidence))
                
                # ChunkResult 생성
                chunk_result = ChunkResult(
                    chunk=TextChunk(
                        content=doc.page_content,
                        metadata=doc.metadata
                    ),
                    confidence=confidence,
                    domain="publish",
                    search_method="faiss",
                    metadata=self._create_publish_metadata(
                        doc, i + 1, distance_score, similarity, detected_department
                    )
                )
                
                chunk_results.append(chunk_result)
            
            # 4. confidence 순으로 재정렬 후 상위 3개 반환
            chunk_results.sort(key=lambda x: x.confidence, reverse=True)
            top_chunks = chunk_results[:3]
            
            logger.info(
                f"발행물 검색 완료: {len(top_chunks)}개 반환 "
                f"(최고 confidence: {top_chunks[0].confidence:.3f})"
            )
            
            return top_chunks
            
        except Exception as e:
            logger.error(f"발행물 검색 실패: {e}")
            return []
    
    def _detect_content_category(self, query: str) -> Optional[str]:
        """
        담당부서 자동 감지
        
        Args:
            query: 사용자 질문
            
        Returns:
            Optional[str]: 담당부서 연락처 또는 None
        """
        query_lower = query.lower()
        
        # 평가 관련 키워드 체크
        if any(keyword in query_lower for keyword in self.EVALUATION_KEYWORDS):
            return '평가분석담당 (055-254-2021)'
        
        # 계획 관련 키워드 체크
        if any(keyword in query_lower for keyword in self.PLANNING_KEYWORDS):
            return '교육기획담당 (055-254-2051)'
        
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
    
    def _create_publish_metadata(
        self, 
        doc, 
        rank: int, 
        distance_score: float, 
        similarity_score: float,
        detected_department: Optional[str]
    ) -> Dict[str, Any]:
        """
        발행물 특화 메타데이터 생성
        
        Args:
            doc: 검색된 문서
            rank: 검색 순위
            distance_score: FAISS 거리 점수
            similarity_score: 변환된 유사도 점수
            detected_department: 감지된 담당부서
            
        Returns:
            Dict: 발행물 특화 메타데이터
        """
        base_metadata = doc.metadata.copy()
        
        # 기본 담당부서 정보
        department = self.department_info["department"]
        contact = self.department_info["phone"]
        
        # 감지된 담당부서가 있으면 우선 사용
        if detected_department:
            department = detected_department
            contact = detected_department  # 이미 연락처 포함된 형태
        
        # 발행물 핸들러 특화 정보 추가
        base_metadata.update({
            "department": department,
            "contact": contact,
            "description": self.department_info["description"],
            "rank": rank,
            "distance_score": distance_score,
            "similarity_score": similarity_score,
            "handler_type": "publish",
            "threshold": self.threshold,
            "detected_department": detected_department
        })
        
        return base_metadata
    
    def get_handler_info(self) -> Dict[str, Any]:
        """
        핸들러 정보 반환 (디버깅/모니터링용)
        
        Returns:
            Dict: 핸들러 설정 정보
        """
        return {
            "domain": "publish",
            "threshold": self.threshold,
            "department_info": self.department_info,
            "approach": "단순화 방식 (공식 문서 신뢰성 우선)",
            "features": [
                "순수 FAISS 유사도 기반",
                "담당부서 자동 감지",
                "공식 발행물 전용"
            ],
            "keywords": {
                "evaluation": self.EVALUATION_KEYWORDS,
                "planning": self.PLANNING_KEYWORDS
            },
            "supported_documents": [
                "2025 교육훈련계획서 (2025plan.pdf)",
                "2024 종합평가서 (2024pyeongga.pdf)"
            ]
        }

# =============================================================================
# 편의 함수들
# =============================================================================

def create_publish_handler() -> PublishHandler:
    """
    PublishHandler 인스턴스 생성 편의 함수
    
    Returns:
        PublishHandler: 발행물 핸들러 인스턴스
    """
    return PublishHandler()

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 발행물 핸들러 테스트 ===")
    
    try:
        # 핸들러 초기화 테스트
        handler = PublishHandler()
        print(f"✅ 핸들러 초기화: 임계값 = {handler.threshold}")
        
        # 설정 정보 출력
        info = handler.get_handler_info()
        print(f"✅ 핸들러 정보: {info['domain']}")
        print(f"✅ 담당부서: {info['department_info']['department']}")
        print(f"✅ 접근 방식: {info['approach']}")
        
        # 담당부서 감지 테스트
        test_queries = [
            "2025년 교육계획은?",           # 계획 → 교육기획담당
            "2024년 만족도 평가결과는?",     # 평가 → 평가분석담당
            "교육과정 운영 실적 알려줘",     # 일반 → 기본 담당부서
            "예산 규모는 어떻게 돼?",        # 일반 → 기본 담당부서
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n--- 테스트 {i}: {query} ---")
            
            # 담당부서 감지 테스트
            detected = handler._detect_content_category(query)
            print(f"감지된 담당부서: {detected or '기본 담당부서'}")
            
            try:
                results = handler.search_chunks(query)
                print(f"검색 결과: {len(results)}개")
                
                for j, result in enumerate(results):
                    print(f"  {j+1}. confidence: {result.confidence:.3f}")
                    print(f"     domain: {result.domain}")
                    print(f"     content: {result.chunk.content[:100]}...")
                    
            except Exception as e:
                print(f"❌ 검색 테스트 실패: {e}")
        
        print("\n🎉 모든 테스트 완료!")
        
    except Exception as e:
        print(f"\n❌ 핸들러 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
