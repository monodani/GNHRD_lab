# handlers/cyber_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 사이버교육 핸들러 v3.1
Architecture.md 기반 검색 전용 핸들러

핵심 기능:
- 검색만 담당 (LLM 호출 없음)
- 절대적 Confidence 기반 (FAISS distance → similarity 변환)
- 사이버교육 메타데이터 기반 지능형 필터링 및 가중치
- 학습시간/인정시간 효율성, 최신성, 평가유무 고려
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
# CyberHandler 클래스
# =============================================================================

class CyberHandler:
    """
    사이버교육 검색 핸들러
    
    처리 범위:
    - 민간위탁 사이버교육 (mingan.csv)
    - 나라배움터 사이버교육 (nara.csv)
    - 학습시간, 인정시간, 최신성, 평가유무 기반 지능형 필터링
    """
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
    # ================================================================
    
    # 학습시간 기준치 (시간)
    SHORT_LEARNING_THRESHOLD = 5.0      # 이 값 이하 = 짧은 교육 (바쁜 직장인 선호)
    LONG_LEARNING_THRESHOLD = 10.0      # 이 값 이상 = 긴 교육
    
    # 인정시간 효율성 기준치 (인정시간/학습시간 비율)
    HIGH_EFFICIENCY_RATIO = 0.8         # 80% 이상 = 높은 효율성 (학습시간 대비 많은 인정시간)
    LOW_EFFICIENCY_RATIO = 0.5          # 50% 이하 = 낮은 효율성
    
    # 최신성 기준치 (연도)
    RECENT_DEVELOPMENT_THRESHOLD = 2023  # 이 연도 이후 = 최신 콘텐츠
    OLD_DEVELOPMENT_THRESHOLD = 2020     # 이 연도 이전 = 오래된 콘텐츠
    
    # Confidence 가중치 설정
    PLATFORM_MATCH_BOOST = 0.03         # 플랫폼 타입 일치시 보너스
    SHORT_LEARNING_BOOST = 0.04         # 짧은 학습시간 보너스 (가장 중요)
    HIGH_EFFICIENCY_BOOST = 0.03        # 높은 인정시간 효율성 보너스
    RECENT_CONTENT_BOOST = 0.02         # 최신 콘텐츠 보너스
    EVALUATION_FREE_BOOST = 0.02        # 평가 없음 보너스 (나라배움터만)
    LONG_LEARNING_PENALTY = -0.02       # 긴 학습시간 페널티
    OLD_CONTENT_PENALTY = -0.02         # 오래된 콘텐츠 페널티
    
    # 쿼리 의도 분석 키워드
    PROFESSIONAL_KEYWORDS = ["전문", "심화", "자세한", "깊이", "상세한", "고급"]
    CONVENIENCE_KEYWORDS = ["바쁜", "간단한", "짧은", "빠른", "쉬운", "기본"]
    RECENT_KEYWORDS = ["최신", "신규", "새로운", "업데이트", "2024", "2025"]
    
    # 플랫폼 키워드
    MINGAN_KEYWORDS = ["민간", "민간위탁", "전문", "위탁"]
    NARA_KEYWORDS = ["나라", "나라배움터", "공공", "정부"]
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 끝
    # ================================================================
    
    def __init__(self):
        """CyberHandler 초기화"""
        self.threshold = HANDLER_THRESHOLDS["cyber"]  # 0.48
        self.department_info = DEPARTMENT_CONTACTS["cyber"]
        self.index_manager = get_index_manager()
        
        logger.info(f"✅ CyberHandler 초기화 완료 (임계값: {self.threshold})")
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """
        사이버교육 검색 전용 메서드
        
        Args:
            query: 사용자 질문
            
        Returns:
            List[ChunkResult]: 검색 결과 (상위 3개)
        """
        try:
            # 1. FAISS 검색 수행
            vectorstore = self.index_manager.get_vectorstore("cyber")
            docs_with_scores = vectorstore.similarity_search_with_score(query, k=5)
            
            if not docs_with_scores:
                logger.warning("사이버교육 검색 결과가 없습니다.")
                return []
            
            # 2. 쿼리 분석 (플랫폼, 의도, 키워드)
            preferred_platform = self._analyze_platform_preference(query)
            query_intent = self._analyze_query_intent(query)
            
            # 3. ChunkResult 생성 및 가중치 적용
            chunk_results = []
            for i, (doc, distance_score) in enumerate(docs_with_scores):
                # 거리 → 유사도 변환
                similarity = self._distance_to_similarity(distance_score)
                
                # 순위 기반 미세 조정
                rank_penalty = i * 0.02  # 1등: 0, 2등: -0.02, 3등: -0.04, ...
                confidence = similarity - rank_penalty
                
                # 사이버교육 메타데이터 기반 가중치 적용
                confidence = self._apply_cyber_weights(
                    confidence, doc.metadata, preferred_platform, query_intent
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
                    domain="cyber",
                    search_method="faiss",
                    metadata=self._create_cyber_metadata(
                        doc, i + 1, distance_score, similarity
                    )
                )
                
                chunk_results.append(chunk_result)
            
            # 4. confidence 순으로 재정렬 후 상위 3개 반환
            chunk_results.sort(key=lambda x: x.confidence, reverse=True)
            top_chunks = chunk_results[:3]
            
            logger.info(
                f"사이버교육 검색 완료: {len(top_chunks)}개 반환 "
                f"(최고 confidence: {top_chunks[0].confidence:.3f})"
            )
            
            return top_chunks
            
        except Exception as e:
            logger.error(f"사이버교육 검색 실패: {e}")
            return []
    
    def _analyze_platform_preference(self, query: str) -> Optional[str]:
        """
        쿼리에서 선호하는 플랫폼 분석
        
        Args:
            query: 사용자 질문
            
        Returns:
            Optional[str]: "mingan", "nara", 또는 None
        """
        query_lower = query.lower()
        
        # mingan 키워드 체크
        if any(keyword in query_lower for keyword in self.MINGAN_KEYWORDS):
            return "mingan"
        
        # nara 키워드 체크
        if any(keyword in query_lower for keyword in self.NARA_KEYWORDS):
            return "nara"
        
        return None
    
    def _analyze_query_intent(self, query: str) -> str:
        """
        쿼리 의도 분석 (전문성 vs 편의성 vs 최신성)
        
        Args:
            query: 사용자 질문
            
        Returns:
            str: "professional", "convenience", "recent", 또는 "general"
        """
        query_lower = query.lower()
        
        # 전문성 추구 키워드 체크
        if any(keyword in query_lower for keyword in self.PROFESSIONAL_KEYWORDS):
            return "professional"
        
        # 편의성 추구 키워드 체크
        if any(keyword in query_lower for keyword in self.CONVENIENCE_KEYWORDS):
            return "convenience"
        
        # 최신성 추구 키워드 체크
        if any(keyword in query_lower for keyword in self.RECENT_KEYWORDS):
            return "recent"
        
        return "general"
    
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
    
    def _apply_cyber_weights(
        self, 
        confidence: float, 
        metadata: Dict[str, Any], 
        preferred_platform: Optional[str],
        query_intent: str
    ) -> float:
        """
        사이버교육 메타데이터 기반 가중치 적용
        
        Args:
            confidence: 기본 confidence 점수
            metadata: 문서 메타데이터
            preferred_platform: 선호 플랫폼
            query_intent: 쿼리 의도
            
        Returns:
            float: 가중치 적용된 confidence
        """
        adjusted_confidence = confidence
        
        # 1. 플랫폼 매칭 보너스
        cyber_type = metadata.get('cyber_type')
        if preferred_platform and cyber_type == preferred_platform:
            adjusted_confidence += self.PLATFORM_MATCH_BOOST
            logger.debug(f"플랫폼 매칭 보너스 적용: +{self.PLATFORM_MATCH_BOOST}")
        
        # 2. 학습시간 기반 가중치 (쿼리 의도 고려)
        learning_hours = self._extract_learning_hours(metadata)
        
        if query_intent == "professional":
            # 전문성 추구: 긴 과정 페널티 제거
            if learning_hours <= self.SHORT_LEARNING_THRESHOLD:
                adjusted_confidence += self.SHORT_LEARNING_BOOST * 0.5  # 보너스 절반
        elif query_intent == "convenience":
            # 편의성 추구: 짧은 과정 보너스 강화
            if learning_hours <= self.SHORT_LEARNING_THRESHOLD:
                adjusted_confidence += self.SHORT_LEARNING_BOOST * 1.5  # 보너스 강화
            elif learning_hours >= self.LONG_LEARNING_THRESHOLD:
                adjusted_confidence += self.LONG_LEARNING_PENALTY * 1.5  # 페널티 강화
        else:
            # 일반적인 경우
            if learning_hours <= self.SHORT_LEARNING_THRESHOLD:
                adjusted_confidence += self.SHORT_LEARNING_BOOST
                logger.debug(f"짧은 학습시간 보너스: +{self.SHORT_LEARNING_BOOST} ({learning_hours}h)")
            elif learning_hours >= self.LONG_LEARNING_THRESHOLD:
                adjusted_confidence += self.LONG_LEARNING_PENALTY
                logger.debug(f"긴 학습시간 페널티: {self.LONG_LEARNING_PENALTY} ({learning_hours}h)")
        
        # 3. 인정시간 효율성 보너스
        recognition_hours = metadata.get('recognition_hours', 0)
        if learning_hours > 0 and recognition_hours > 0:
            efficiency_ratio = recognition_hours / learning_hours
            if efficiency_ratio >= self.HIGH_EFFICIENCY_RATIO:
                adjusted_confidence += self.HIGH_EFFICIENCY_BOOST
                logger.debug(f"높은 효율성 보너스: +{self.HIGH_EFFICIENCY_BOOST} (비율: {efficiency_ratio:.2f})")
        
        # 4. 최신성 가중치 (쿼리 의도 고려)
        dev_year = metadata.get('development_year', 0)
        if dev_year:
            try:
                year = int(dev_year)
                recent_boost = self.RECENT_CONTENT_BOOST
                old_penalty = self.OLD_CONTENT_PENALTY
                
                if query_intent == "recent":
                    # 최신성 추구: 최신 보너스 강화
                    recent_boost *= 2.0
                    old_penalty *= 2.0
                
                if year >= self.RECENT_DEVELOPMENT_THRESHOLD:
                    adjusted_confidence += recent_boost
                    logger.debug(f"최신 콘텐츠 보너스: +{recent_boost} ({year}년)")
                elif year <= self.OLD_DEVELOPMENT_THRESHOLD:
                    adjusted_confidence += old_penalty
                    logger.debug(f"오래된 콘텐츠 페널티: {old_penalty} ({year}년)")
            except ValueError:
                pass
        
        # 5. 평가 없음 보너스 (나라배움터만)
        if cyber_type == 'nara':
            evaluation = metadata.get('evaluation_required', '')
            if '없습니다' in evaluation:
                adjusted_confidence += self.EVALUATION_FREE_BOOST
                logger.debug(f"평가 없음 보너스: +{self.EVALUATION_FREE_BOOST}")
        
        return adjusted_confidence
    
    def _extract_learning_hours(self, metadata: Dict[str, Any]) -> float:
        """
        메타데이터에서 학습시간 추출 (mingan: learning_hours, nara: learning_sessions)
        
        Args:
            metadata: 문서 메타데이터
            
        Returns:
            float: 학습시간 (시간 단위)
        """
        cyber_type = metadata.get('cyber_type')
        
        if cyber_type == 'mingan':
            # 민간위탁: learning_hours 사용
            return metadata.get('learning_hours', 0)
        elif cyber_type == 'nara':
            # 나라배움터: learning_sessions를 학습시간으로 처리
            sessions = metadata.get('learning_sessions', '0')
            try:
                return float(str(sessions).strip())
            except (ValueError, TypeError):
                return 0
        
        return 0
    
    def _create_cyber_metadata(
        self, 
        doc, 
        rank: int, 
        distance_score: float, 
        similarity_score: float
    ) -> Dict[str, Any]:
        """
        사이버교육 특화 메타데이터 생성
        
        Args:
            doc: 검색된 문서
            rank: 검색 순위
            distance_score: FAISS 거리 점수
            similarity_score: 변환된 유사도 점수
            
        Returns:
            Dict: 사이버교육 특화 메타데이터
        """
        base_metadata = doc.metadata.copy()
        
        # 사이버교육 핸들러 특화 정보 추가
        base_metadata.update({
            "department": self.department_info["department"],
            "contact": self.department_info["contact"], 
            "description": self.department_info["description"],
            "rank": rank,
            "distance_score": distance_score,
            "similarity_score": similarity_score,
            "handler_type": "cyber",
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
            "domain": "cyber",
            "threshold": self.threshold,
            "department_info": self.department_info,
            "settings": {
                "short_learning_threshold": self.SHORT_LEARNING_THRESHOLD,
                "long_learning_threshold": self.LONG_LEARNING_THRESHOLD,
                "high_efficiency_ratio": self.HIGH_EFFICIENCY_RATIO,
                "low_efficiency_ratio": self.LOW_EFFICIENCY_RATIO,
                "recent_development_threshold": self.RECENT_DEVELOPMENT_THRESHOLD,
                "old_development_threshold": self.OLD_DEVELOPMENT_THRESHOLD,
                "platform_match_boost": self.PLATFORM_MATCH_BOOST,
                "short_learning_boost": self.SHORT_LEARNING_BOOST,
                "high_efficiency_boost": self.HIGH_EFFICIENCY_BOOST,
                "recent_content_boost": self.RECENT_CONTENT_BOOST,
                "evaluation_free_boost": self.EVALUATION_FREE_BOOST,
                "long_learning_penalty": self.LONG_LEARNING_PENALTY,
                "old_content_penalty": self.OLD_CONTENT_PENALTY
            },
            "keywords": {
                "professional": self.PROFESSIONAL_KEYWORDS,
                "convenience": self.CONVENIENCE_KEYWORDS,
                "recent": self.RECENT_KEYWORDS,
                "mingan": self.MINGAN_KEYWORDS,
                "nara": self.NARA_KEYWORDS
            }
        }

# =============================================================================
# 편의 함수들
# =============================================================================

def create_cyber_handler() -> CyberHandler:
    """
    CyberHandler 인스턴스 생성 편의 함수
    
    Returns:
        CyberHandler: 사이버교육 핸들러 인스턴스
    """
    return CyberHandler()

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 사이버교육 핸들러 테스트 ===")
    
    try:
        # 핸들러 초기화 테스트
        handler = CyberHandler()
        print(f"✅ 핸들러 초기화: 임계값 = {handler.threshold}")
        
        # 설정 정보 출력
        info = handler.get_handler_info()
        print(f"✅ 핸들러 정보: {info['domain']}")
        print(f"✅ 담당부서: {info['department_info']['department']}")
        
        # 테스트 쿼리들
        test_queries = [
            "나라배움터에서 짧은 교육 찾아줘",     # nara + convenience
            "민간위탁 전문 교육 추천해줘",         # mingan + professional
            "최신 IT 교육 과정 알려줘",           # recent intent
            "평가 없는 간단한 과정 있어?",        # convenience + evaluation_free
            "5시간 이하 교육 중 효율적인 거"      # short + efficiency
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
