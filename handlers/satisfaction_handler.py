# handlers/satisfaction_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 만족도 조사 핸들러 v3.1
Architecture.md 기반 검색 전용 핸들러

핵심 기능:
- 검색만 담당 (LLM 호출 없음)
- 절대적 Confidence 기반 (FAISS distance → similarity 변환)
- 만족도 메타데이터 기반 지능형 필터링 및 가중치
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
# SatisfactionHandler 클래스
# =============================================================================

class SatisfactionHandler:
    """
    만족도 조사 검색 핸들러
    
    처리 범위:
    - 교육과정 만족도 (course_satisfaction.csv)
    - 교과목 만족도 (subject_satisfaction.csv)
    - 메타데이터 기반 지능형 필터링 및 가중치 적용
    """
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
    # ================================================================
    
    # 만족도 점수 기준치
    HIGH_SATISFACTION_THRESHOLD = 4.60    # 이 값 이상 = 높은/좋은 점수
    LOW_SATISFACTION_THRESHOLD = 4.15     # 이 값 이하 = 낮은/좋지 못한 점수
    
    # 순위 상위권 기준치
    COURSE_TOP_RANKING_THRESHOLD = 50     # 교육과정 상위권 기준 (50위 이내)
    SUBJECT_TOP_RANKING_THRESHOLD = 500   # 교과목 상위권 기준 (500위 이내)
    
    # 순위 하위권 기준치
    COURSE_BOTTOM_RANKING_THRESHOLD = 130   # 교육과정 하위권 기준 (130위 이상)
    SUBJECT_BOTTOM_RANKING_THRESHOLD = 1500 # 교과목 하위권 기준 (1500위 이상)
    
    # Confidence 가중치 설정
    TYPE_MATCH_BOOST = 0.03              # 타입 일치시 보너스
    HIGH_SATISFACTION_BOOST = 0.05       # 높은 만족도 보너스
    LOW_SATISFACTION_PENALTY = -0.03     # 낮은 만족도 페널티
    TOP_RANKING_BOOST = 0.02             # 상위권 보너스
    BOTTOM_RANKING_PENALTY = -0.02       # 하위권 페널티
    
    # 타입 필터링 키워드
    COURSE_KEYWORDS = ["교육과정"]
    SUBJECT_KEYWORDS = ["교과목", "강의"]
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 끝
    # ================================================================
    
    def __init__(self):
        """SatisfactionHandler 초기화"""
        self.threshold = HANDLER_THRESHOLDS["satisfaction"]  # 0.45
        self.department_info = DEPARTMENT_CONTACTS["satisfaction"]
        self.index_manager = get_index_manager()
        
        logger.info(f"✅ SatisfactionHandler 초기화 완료 (임계값: {self.threshold})")
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """
        만족도 조사 검색 전용 메서드
        
        Args:
            query: 사용자 질문
            
        Returns:
            List[ChunkResult]: 검색 결과 (상위 3개)
        """
        try:
            # 1. FAISS 검색 수행
            vectorstore = self.index_manager.get_vectorstore("satisfaction")
            docs_with_scores = vectorstore.similarity_search_with_score(query, k=5)
            
            if not docs_with_scores:
                logger.warning("만족도 검색 결과가 없습니다.")
                return []
            
            # 2. 쿼리 타입 분석 (course vs subject 우선순위)
            preferred_type = self._analyze_query_type(query)
            
            # 3. ChunkResult 생성 및 가중치 적용
            chunk_results = []
            for i, (doc, distance_score) in enumerate(docs_with_scores):
                # 거리 → 유사도 변환
                similarity = self._distance_to_similarity(distance_score)
                
                # 순위 기반 미세 조정
                rank_penalty = i * 0.02  # 1등: 0, 2등: -0.02, 3등: -0.04, ...
                confidence = similarity - rank_penalty
                
                # 만족도 메타데이터 기반 가중치 적용
                confidence = self._apply_satisfaction_weights(
                    confidence, doc.metadata, preferred_type
                )
                
                # confidence 범위 제한
                confidence = max(0.0, min(1.0, confidence))
                
                # ChunkResult 생성
                chunk_result = ChunkResult(
                    chunk=TextChunk(
                        content=doc.page_content,
                        metadata=doc.metadata
                    ),
                    confidence=confidence,
                    domain="satisfaction",
                    search_method="faiss",
                    metadata=self._create_satisfaction_metadata(
                        doc, i + 1, distance_score, similarity
                    )
                )
                
                chunk_results.append(chunk_result)
            
            # 4. confidence 순으로 재정렬 후 상위 3개 반환
            chunk_results.sort(key=lambda x: x.confidence, reverse=True)
            top_chunks = chunk_results[:3]
            
            logger.info(
                f"만족도 검색 완료: {len(top_chunks)}개 반환 "
                f"(최고 confidence: {top_chunks[0].confidence:.3f})"
            )
            
            return top_chunks
            
        except Exception as e:
            logger.error(f"만족도 검색 실패: {e}")
            return []
    
    def _analyze_query_type(self, query: str) -> Optional[str]:
        """
        쿼리에서 선호하는 데이터 타입 분석
        
        Args:
            query: 사용자 질문
            
        Returns:
            Optional[str]: "course", "subject", 또는 None
        """
        query_lower = query.lower()
        
        # course 키워드 체크
        if any(keyword in query_lower for keyword in self.COURSE_KEYWORDS):
            return "course"
        
        # subject 키워드 체크
        if any(keyword in query_lower for keyword in self.SUBJECT_KEYWORDS):
            return "subject"
        
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
    
    def _apply_satisfaction_weights(
        self, 
        confidence: float, 
        metadata: Dict[str, Any], 
        preferred_type: Optional[str]
    ) -> float:
        """
        만족도 메타데이터 기반 가중치 적용
        
        Args:
            confidence: 기본 confidence 점수
            metadata: 문서 메타데이터
            preferred_type: 선호 데이터 타입
            
        Returns:
            float: 가중치 적용된 confidence
        """
        adjusted_confidence = confidence
        
        # 1. 타입 매칭 보너스
        satisfaction_type = metadata.get('satisfaction_type')
        if preferred_type and satisfaction_type == preferred_type:
            adjusted_confidence += self.TYPE_MATCH_BOOST
            logger.debug(f"타입 매칭 보너스 적용: +{self.TYPE_MATCH_BOOST}")
        
        # 2. 만족도 점수 기반 가중치
        if satisfaction_type == 'course':
            # 교육과정: overall_satisfaction 또는 comprehensive_satisfaction 사용
            satisfaction_score = (
                metadata.get('overall_satisfaction', 0) or 
                metadata.get('comprehensive_satisfaction', 0)
            )
        else:
            # 교과목: lecture_satisfaction 사용
            satisfaction_score = metadata.get('lecture_satisfaction', 0)
        
        if satisfaction_score >= self.HIGH_SATISFACTION_THRESHOLD:
            adjusted_confidence += self.HIGH_SATISFACTION_BOOST
            logger.debug(f"높은 만족도 보너스 적용: +{self.HIGH_SATISFACTION_BOOST} (점수: {satisfaction_score})")
        elif satisfaction_score <= self.LOW_SATISFACTION_THRESHOLD:
            adjusted_confidence += self.LOW_SATISFACTION_PENALTY
            logger.debug(f"낮은 만족도 페널티 적용: {self.LOW_SATISFACTION_PENALTY} (점수: {satisfaction_score})")
        
        # 3. 순위 기반 가중치
        if satisfaction_type == 'course':
            ranking = metadata.get('course_ranking', 999)
            if ranking <= self.COURSE_TOP_RANKING_THRESHOLD:
                adjusted_confidence += self.TOP_RANKING_BOOST
                logger.debug(f"상위권 교육과정 보너스: +{self.TOP_RANKING_BOOST} (순위: {ranking})")
            elif ranking >= self.COURSE_BOTTOM_RANKING_THRESHOLD:
                adjusted_confidence += self.BOTTOM_RANKING_PENALTY
                logger.debug(f"하위권 교육과정 페널티: {self.BOTTOM_RANKING_PENALTY} (순위: {ranking})")
        
        elif satisfaction_type == 'subject':
            ranking = metadata.get('subject_ranking', 999)
            if ranking <= self.SUBJECT_TOP_RANKING_THRESHOLD:
                adjusted_confidence += self.TOP_RANKING_BOOST
                logger.debug(f"상위권 교과목 보너스: +{self.TOP_RANKING_BOOST} (순위: {ranking})")
            elif ranking >= self.SUBJECT_BOTTOM_RANKING_THRESHOLD:
                adjusted_confidence += self.BOTTOM_RANKING_PENALTY
                logger.debug(f"하위권 교과목 페널티: {self.BOTTOM_RANKING_PENALTY} (순위: {ranking})")
        
        return adjusted_confidence
    
    def _create_satisfaction_metadata(
        self, 
        doc, 
        rank: int, 
        distance_score: float, 
        similarity_score: float
    ) -> Dict[str, Any]:
        """
        만족도 특화 메타데이터 생성
        
        Args:
            doc: 검색된 문서
            rank: 검색 순위
            distance_score: FAISS 거리 점수
            similarity_score: 변환된 유사도 점수
            
        Returns:
            Dict: 만족도 특화 메타데이터
        """
        base_metadata = doc.metadata.copy()
        
        # 만족도 핸들러 특화 정보 추가
        base_metadata.update({
            "department": self.department_info("department", "평가분석담당"),
            "contact": self.department_info("contact", "055-254-2021"), 
            "description": self.department_info("description", "교육 만족도 분석"),
            "rank": rank,
            "distance_score": distance_score,
            "similarity_score": similarity_score,
            "handler_type": "satisfaction",
            "threshold": self.threshold
        })
        
        return base_metadata
    
    def get_handler_info(self) -> Dict[str, Any]:
        """
        핸들러 정보 반환 (디버깅/모니터링용)
        
        Returns:
            Dict: 핸들러 설정 정보
        """
        return {
            "domain": "satisfaction",
            "threshold": self.threshold,
            "department_info": self.department_info,
            "settings": {
                "high_satisfaction_threshold": self.HIGH_SATISFACTION_THRESHOLD,
                "low_satisfaction_threshold": self.LOW_SATISFACTION_THRESHOLD,
                "course_top_ranking": self.COURSE_TOP_RANKING_THRESHOLD,
                "subject_top_ranking": self.SUBJECT_TOP_RANKING_THRESHOLD,
                "course_bottom_ranking": self.COURSE_BOTTOM_RANKING_THRESHOLD,
                "subject_bottom_ranking": self.SUBJECT_BOTTOM_RANKING_THRESHOLD,
                "type_match_boost": self.TYPE_MATCH_BOOST,
                "high_satisfaction_boost": self.HIGH_SATISFACTION_BOOST,
                "low_satisfaction_penalty": self.LOW_SATISFACTION_PENALTY,
                "top_ranking_boost": self.TOP_RANKING_BOOST,
                "bottom_ranking_penalty": self.BOTTOM_RANKING_PENALTY
            }
        }

# =============================================================================
# 편의 함수들
# =============================================================================

def create_satisfaction_handler() -> SatisfactionHandler:
    """
    SatisfactionHandler 인스턴스 생성 편의 함수
    
    Returns:
        SatisfactionHandler: 만족도 핸들러 인스턴스
    """
    return SatisfactionHandler()

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 만족도 핸들러 테스트 ===")
    
    try:
        # 핸들러 초기화 테스트
        handler = SatisfactionHandler()
        print(f"✅ 핸들러 초기화: 임계값 = {handler.threshold}")
        
        # 설정 정보 출력
        info = handler.get_handler_info()
        print(f"✅ 핸들러 정보: {info['domain']}")
        print(f"✅ 담당부서: {info['department_info']['department']}")
        
        # 테스트 쿼리들
        test_queries = [
            "중견리더과정의 만족도는?",  # course 타입 매칭
            "리더십 강의 만족도는?",      # subject 타입 매칭
            "2024년 교육 만족도 순위",    # 일반 검색
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n--- 테스트 {i}: {query} ---")
            
            try:
                results = handler.search_chunks(query)
                print(f"검색 결과: {len(results)}개")
                
                for j, result in enumerate(results):
                    print(f"  {j+1}. confidence: {result.confidence:.3f}")
                    print(f"     domain: {result.domain}")
                    print(f"     content: {result.chunk.content[:100]}...")
                    
            except Exception as e:
                print(f"❌ 테스트 {i} 실패: {e}")
        
        print("\n🎉 모든 테스트 완료!")
        
    except Exception as e:
        print(f"\n❌ 핸들러 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
