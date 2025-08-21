# handlers/satisfaction_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 만족도 조사 핸들러 v5.0
코랩 성공 패턴 + 파인튜닝 편의성 + 시스템 호환성 최적화

핵심 설계:
- 코랩 방식의 단순함과 직관성 유지
- 파인튜닝 설정 구역 집중 배치 
- 모든 시스템과 호환되는 안전한 코딩
- 에러 처리 및 디버깅 최적화

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-21
"""

import logging
from typing import List, Dict, Any, Optional
from utils.contracts import ChunkResult, TextChunk
from utils.index_manager import IndexManager

# =============================================================================
# 🔧 파인튜닝 설정 구역 - 모든 조정 가능한 값들
# =============================================================================

# 기본 설정
DOMAIN = "satisfaction"
HANDLER_THRESHOLD = 0.45
SEARCH_K = 5

# 만족도 점수 기준치
HIGH_SATISFACTION_THRESHOLD = 4.60    # 높은 만족도 기준
LOW_SATISFACTION_THRESHOLD = 4.15     # 낮은 만족도 기준

# 순위 기준치
COURSE_TOP_RANKING = 50      # 교육과정 상위권 (50위 이내)
SUBJECT_TOP_RANKING = 500    # 교과목 상위권 (500위 이내)  
COURSE_BOTTOM_RANKING = 130  # 교육과정 하위권 (130위 이상)
SUBJECT_BOTTOM_RANKING = 1500 # 교과목 하위권 (1500위 이상)

# Confidence 가중치
TYPE_MATCH_BOOST = 0.03           # 타입 매칭 보너스
HIGH_SATISFACTION_BOOST = 0.05    # 높은 만족도 보너스  
LOW_SATISFACTION_PENALTY = -0.03  # 낮은 만족도 페널티
TOP_RANKING_BOOST = 0.02          # 상위권 보너스
BOTTOM_RANKING_PENALTY = -0.02    # 하위권 페널티

# 키워드 매칭
COURSE_KEYWORDS = ["교육과정", "과정"]
SUBJECT_KEYWORDS = ["교과목", "강의", "수업"]

# 담당부서 정보 (코랩 방식: 직접 정의)
DEPARTMENT_INFO = {
    "department": "인재개발지원과 평가분석담당",
    "contact": "055-254-2021", 
    "description": "교육과정 및 교과목 만족도 분석"
}

# 디버깅 설정
DEBUG_MODE = True  # 상세 로그 출력 여부

# =============================================================================
# 🔧 파인튜닝 설정 구역 끝
# =============================================================================

logger = logging.getLogger(__name__)

class SatisfactionHandler:
    """
    만족도 조사 검색 핸들러 (v5.0 최적화)
    
    특징:
    - 코랩 성공 패턴 적용
    - 파인튜닝 편의성 극대화
    - 안전한 에러 처리
    - 시스템 호환성 보장
    """
    
    def __init__(self):
        """핸들러 초기화 - 단순하고 안전하게"""
        # 기본 설정
        self.domain = DOMAIN
        self.threshold = HANDLER_THRESHOLD
        self.search_k = SEARCH_K
        self.department_info = DEPARTMENT_INFO.copy()
        
        # IndexManager 안전 초기화
        try:
            self.index_manager = IndexManager()
            self.vectorstore = None
            self._load_vectorstore()
        except Exception as e:
            logger.error(f"❌ IndexManager 초기화 실패: {e}")
            self.index_manager = None
            self.vectorstore = None
        
        logger.info(f"✅ SatisfactionHandler 초기화 완료 (임계값: {self.threshold})")
    
    def _load_vectorstore(self):
        """벡터스토어 로드 - 안전한 방식"""
        if not self.index_manager:
            return
        
        try:
            self.vectorstore = self.index_manager.get_vectorstore(self.domain)
            if self.vectorstore:
                logger.info(f"✅ {self.domain} 벡터스토어 로드 성공")
            else:
                logger.warning(f"⚠️ {self.domain} 벡터스토어 로드 실패")
        except Exception as e:
            logger.error(f"❌ 벡터스토어 로드 오류: {e}")
            self.vectorstore = None
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """
        만족도 검색 메인 메서드
        
        Args:
            query: 사용자 질문
            
        Returns:
            List[ChunkResult]: 검색 결과 (상위 3개)
        """
        # 사전 체크
        if not self._is_ready():
            logger.error("만족도 핸들러가 준비되지 않음")
            return []
        
        try:
            if DEBUG_MODE:
                logger.info(f"🔍 만족도 검색 시작: '{query}'")
            
            # 1. FAISS 검색 실행
            docs_with_scores = self.vectorstore.similarity_search_with_score(
                query, k=self.search_k
            )
            
            if not docs_with_scores:
                logger.warning("검색 결과 없음")
                return []
            
            # 2. 쿼리 타입 분석
            preferred_type = self._analyze_query_type(query)
            if DEBUG_MODE and preferred_type:
                logger.info(f"📊 쿼리 타입 감지: {preferred_type}")
            
            # 3. ChunkResult 생성 및 가중치 적용
            chunk_results = []
            for i, (doc, distance_score) in enumerate(docs_with_scores):
                # 거리 → 유사도 변환 (코랩 방식)
                similarity = self._distance_to_similarity(distance_score)
                
                # 순위 페널티 적용
                rank_penalty = i * 0.02
                confidence = similarity - rank_penalty
                
                # 만족도 가중치 적용
                confidence = self._apply_satisfaction_weights(
                    confidence, doc.metadata, preferred_type
                )
                
                # 범위 제한
                confidence = max(0.0, min(1.0, confidence))
                
                # ChunkResult 생성
                chunk_result = ChunkResult(
                    chunk=TextChunk(
                        content=doc.page_content,
                        metadata=doc.metadata
                    ),
                    confidence=confidence,
                    domain=self.domain,
                    search_method="faiss",
                    metadata=self._create_metadata(doc, i + 1, distance_score, similarity)
                )
                
                chunk_results.append(chunk_result)
                
                if DEBUG_MODE:
                    logger.debug(f"  {i+1}. confidence={confidence:.3f} (유사도={similarity:.3f})")
            
            # 4. confidence 정렬 후 상위 3개 반환
            chunk_results.sort(key=lambda x: x.confidence, reverse=True)
            top_chunks = chunk_results[:3]
            
            logger.info(f"만족도 검색 완료: {len(top_chunks)}개 반환 (최고 confidence: {top_chunks[0].confidence:.3f})")
            
            return top_chunks
            
        except Exception as e:
            logger.error(f"만족도 검색 실패: {e}")
            if DEBUG_MODE:
                import traceback
                traceback.print_exc()
            return []
    
    def _is_ready(self) -> bool:
        """핸들러 준비 상태 체크"""
        return (
            self.index_manager is not None and 
            self.vectorstore is not None
        )
    
    def _analyze_query_type(self, query: str) -> Optional[str]:
        """쿼리 타입 분석 - 단순하고 명확하게"""
        query_lower = query.lower()
        
        # 교육과정 키워드 체크
        if any(keyword in query_lower for keyword in COURSE_KEYWORDS):
            return "course"
        
        # 교과목 키워드 체크  
        if any(keyword in query_lower for keyword in SUBJECT_KEYWORDS):
            return "subject"
        
        return None
    
    def _distance_to_similarity(self, distance: float) -> float:
        """
        FAISS 거리를 유사도로 변환 (코랩 검증된 방식)
        
        Args:
            distance: FAISS 거리 점수
            
        Returns:
            float: 유사도 점수 (0.0-1.0)
        """
        # 코랩에서 검증된 변환 공식
        similarity = 1.0 / (1.0 + distance)
        
        # 정규화 (실험을 통해 최적화된 값)
        if distance <= 0.1:
            similarity = max(0.9, similarity)
        elif distance >= 2.0:
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
            confidence: 기본 confidence
            metadata: 문서 메타데이터 
            preferred_type: 선호 타입
            
        Returns:
            float: 가중치 적용된 confidence
        """
        adjusted = confidence
        
        # 1. 타입 매칭 보너스
        satisfaction_type = metadata.get('satisfaction_type', '')
        if preferred_type and satisfaction_type == preferred_type:
            adjusted += TYPE_MATCH_BOOST
            if DEBUG_MODE:
                logger.debug(f"타입 매칭 보너스: +{TYPE_MATCH_BOOST}")
        
        # 2. 만족도 점수 기반 가중치
        satisfaction_score = self._get_satisfaction_score(metadata, satisfaction_type)
        
        if satisfaction_score >= HIGH_SATISFACTION_THRESHOLD:
            adjusted += HIGH_SATISFACTION_BOOST
            if DEBUG_MODE:
                logger.debug(f"높은 만족도 보너스: +{HIGH_SATISFACTION_BOOST} (점수: {satisfaction_score})")
        elif satisfaction_score <= LOW_SATISFACTION_THRESHOLD:
            adjusted += LOW_SATISFACTION_PENALTY
            if DEBUG_MODE:
                logger.debug(f"낮은 만족도 페널티: {LOW_SATISFACTION_PENALTY} (점수: {satisfaction_score})")
        
        # 3. 순위 기반 가중치
        self._apply_ranking_weights(adjusted, metadata, satisfaction_type)
        
        return adjusted
    
    def _get_satisfaction_score(self, metadata: Dict[str, Any], satisfaction_type: str) -> float:
        """만족도 점수 추출 - 안전한 방식"""
        if satisfaction_type == 'course':
            # 교육과정: 전반만족도 또는 종합만족도
            return (
                metadata.get('overall_satisfaction', 0) or 
                metadata.get('comprehensive_satisfaction', 0) or
                0.0
            )
        else:
            # 교과목: 강의만족도
            return metadata.get('lecture_satisfaction', 0.0)
    
    def _apply_ranking_weights(self, adjusted: float, metadata: Dict[str, Any], satisfaction_type: str) -> float:
        """순위 기반 가중치 적용"""
        if satisfaction_type == 'course':
            ranking = metadata.get('course_ranking', 999)
            if ranking <= COURSE_TOP_RANKING:
                adjusted += TOP_RANKING_BOOST
            elif ranking >= COURSE_BOTTOM_RANKING:
                adjusted += BOTTOM_RANKING_PENALTY
        
        elif satisfaction_type == 'subject':
            ranking = metadata.get('subject_ranking', 999)
            if ranking <= SUBJECT_TOP_RANKING:
                adjusted += TOP_RANKING_BOOST
            elif ranking >= SUBJECT_BOTTOM_RANKING:
                adjusted += BOTTOM_RANKING_PENALTY
        
        return adjusted
    
    def _create_metadata(
        self, 
        doc, 
        rank: int, 
        distance_score: float, 
        similarity_score: float
    ) -> Dict[str, Any]:
        """
        메타데이터 생성 - 안전하고 호환성 보장
        
        Args:
            doc: 검색된 문서
            rank: 검색 순위
            distance_score: FAISS 거리
            similarity_score: 변환된 유사도
            
        Returns:
            Dict: 완전한 메타데이터
        """
        # 기존 메타데이터 복사 (안전하게)
        try:
            base_metadata = doc.metadata.copy() if hasattr(doc, 'metadata') and doc.metadata else {}
        except Exception:
            base_metadata = {}
        
        # 핸들러 정보 추가 (코랩 방식 - 직접 설정)
        base_metadata.update({
            # 부서 정보
            "department": self.department_info.get("department", "평가분석담당"),
            "contact": self.department_info.get("contact", "055-254-2021"),
            "description": self.department_info.get("description", "교육 만족도 분석"),
            
            # 검색 정보
            "rank": rank,
            "distance_score": float(distance_score),
            "similarity_score": float(similarity_score),
            "handler_type": self.domain,
            "threshold": self.threshold,
            
            # 시스템 호환성
            "handler_version": "5.0",
            "search_method": "faiss"
        })
        
        return base_metadata
    
    def get_handler_info(self) -> Dict[str, Any]:
        """
        핸들러 정보 반환 (디버깅/모니터링용)
        
        Returns:
            Dict: 완전한 핸들러 정보
        """
        return {
            "domain": self.domain,
            "threshold": self.threshold,
            "search_k": self.search_k,
            "ready": self._is_ready(),
            "department_info": self.department_info.copy(),
            "tuning_settings": {
                "high_satisfaction_threshold": HIGH_SATISFACTION_THRESHOLD,
                "low_satisfaction_threshold": LOW_SATISFACTION_THRESHOLD,
                "course_top_ranking": COURSE_TOP_RANKING,
                "subject_top_ranking": SUBJECT_TOP_RANKING,
                "course_bottom_ranking": COURSE_BOTTOM_RANKING,
                "subject_bottom_ranking": SUBJECT_BOTTOM_RANKING,
                "type_match_boost": TYPE_MATCH_BOOST,
                "high_satisfaction_boost": HIGH_SATISFACTION_BOOST,
                "low_satisfaction_penalty": LOW_SATISFACTION_PENALTY,
                "top_ranking_boost": TOP_RANKING_BOOST,
                "bottom_ranking_penalty": BOTTOM_RANKING_PENALTY
            },
            "version": "5.0",
            "debug_mode": DEBUG_MODE
        }

# =============================================================================
# 편의 함수들
# =============================================================================

def create_satisfaction_handler() -> SatisfactionHandler:
    """
    SatisfactionHandler 인스턴스 생성 편의 함수
    
    Returns:
        SatisfactionHandler: 최적화된 핸들러 인스턴스
    """
    return SatisfactionHandler()

def update_tuning_settings(**kwargs):
    """
    파인튜닝 설정 업데이트 편의 함수
    
    사용법:
        update_tuning_settings(
            HIGH_SATISFACTION_THRESHOLD=4.7,
            SEARCH_K=10,
            DEBUG_MODE=False
        )
    """
    globals().update(kwargs)
    logger.info(f"✅ 파인튜닝 설정 업데이트: {kwargs}")

def get_tuning_settings() -> Dict[str, Any]:
    """현재 파인튜닝 설정 조회"""
    return {
        "HANDLER_THRESHOLD": HANDLER_THRESHOLD,
        "SEARCH_K": SEARCH_K,
        "HIGH_SATISFACTION_THRESHOLD": HIGH_SATISFACTION_THRESHOLD,
        "LOW_SATISFACTION_THRESHOLD": LOW_SATISFACTION_THRESHOLD,
        "COURSE_TOP_RANKING": COURSE_TOP_RANKING,
        "SUBJECT_TOP_RANKING": SUBJECT_TOP_RANKING,
        "TYPE_MATCH_BOOST": TYPE_MATCH_BOOST,
        "HIGH_SATISFACTION_BOOST": HIGH_SATISFACTION_BOOST,
        "DEBUG_MODE": DEBUG_MODE
    }

# =============================================================================
# 테스트 코드
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 만족도 핸들러 v5.0 테스트 ===")
    
    try:
        # 핸들러 초기화 테스트
        handler = SatisfactionHandler()
        print(f"✅ 핸들러 초기화 완료: {handler.domain}")
        
        # 설정 정보 출력
        info = handler.get_handler_info()
        print(f"✅ 준비 상태: {info['ready']}")
        print(f"✅ 담당부서: {info['department_info']['department']}")
        
        # 현재 파인튜닝 설정 확인
        settings = get_tuning_settings()
        print(f"✅ 현재 설정: {settings}")
        
        # 테스트 쿼리들
        test_queries = [
            "중견리더과정의 만족도는?",
            "리더십 강의 만족도는?", 
            "2024년 교육 만족도 순위"
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n--- 테스트 {i}: {query} ---")
            
            try:
                results = handler.search_chunks(query)
                print(f"검색 결과: {len(results)}개")
                
                for j, result in enumerate(results, 1):
                    print(f"  {j}. confidence: {result.confidence:.3f}")
                    print(f"     domain: {result.domain}")
                    print(f"     content: {result.chunk.content[:100]}...")
                    
            except Exception as e:
                print(f"❌ 테스트 {i} 실패: {e}")
        
        print("\n🎉 모든 테스트 완료!")
        
        # 파인튜닝 예시
        print("\n🔧 파인튜닝 예시:")
        print("update_tuning_settings(HIGH_SATISFACTION_THRESHOLD=4.7, DEBUG_MODE=False)")
        
    except Exception as e:
        print(f"\n❌ 핸들러 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
