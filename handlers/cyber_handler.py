# handlers/cyber_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 사이버교육 핸들러 v5.0
satisfaction_handler 성공 패턴 적용 + 파인튜닝 편의성 + 시스템 호환성 최적화

핵심 설계:
- satisfaction_handler와 동일한 안전한 패턴 적용
- 파인튜닝 설정 구역 집중 배치 
- 모든 시스템과 호환되는 안전한 코딩
- 사이버교육 특화 지능형 필터링 유지

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
DOMAIN = "cyber"
HANDLER_THRESHOLD = 0.48
SEARCH_K = 5

# 학습시간 기준치 (시간)
SHORT_LEARNING_THRESHOLD = 5.0      # 이 값 이하 = 짧은 교육 (바쁜 직장인 선호)
LONG_LEARNING_THRESHOLD = 10.0      # 이 값 이상 = 긴 교육

# 인정시간 효율성 기준치 (인정시간/학습시간 비율)
HIGH_EFFICIENCY_RATIO = 0.8         # 80% 이상 = 높은 효율성
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

# 담당부서 정보 (코랩 방식: 직접 정의)
DEPARTMENT_INFO = {
    "department": "인재양성과 사이버담당",
    "contact": "055-254-2081", 
    "description": "사이버교육(온라인 교육) 수강 및 관리"
}

# 디버깅 설정
DEBUG_MODE = True  # 상세 로그 출력 여부

# =============================================================================
# 🔧 파인튜닝 설정 구역 끝
# =============================================================================

logger = logging.getLogger(__name__)

class CyberHandler:
    """
    사이버교육 검색 핸들러 (v5.0 최적화)
    
    특징:
    - satisfaction_handler 성공 패턴 적용
    - 사이버교육 특화 지능형 필터링
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
        
        logger.info(f"✅ CyberHandler 초기화 완료 (임계값: {self.threshold})")
    
    def _load_vectorstore(self):
        """벡터스토어 로드 - 진단 정보 포함"""
        if not self.index_manager:
            logger.error("❌ IndexManager가 None입니다")
            return
        
        try:
            # 상세 진단 정보 출력
            if DEBUG_MODE:
                logger.info(f"🔍 {self.domain} 벡터스토어 로드 시도...")
            
            # 벡터스토어 획득 시도
            self.vectorstore = self.index_manager.get_vectorstore(self.domain)
            
            if self.vectorstore:
                logger.info(f"✅ {self.domain} 벡터스토어 로드 성공")
                # 벡터스토어 정보 출력
                if hasattr(self.vectorstore, 'index') and hasattr(self.vectorstore.index, 'ntotal'):
                    doc_count = self.vectorstore.index.ntotal
                    if DEBUG_MODE:
                        logger.info(f"📄 {self.domain} 문서 개수: {doc_count}")
            else:
                logger.error(f"❌ {self.domain} 벡터스토어가 None입니다")
                logger.info("🔧 IndexManager preload 시도...")
                
                # 수동으로 preload 시도
                preload_result = self.index_manager.preload_all_indexes()
                if DEBUG_MODE:
                    logger.info(f"📊 Preload 결과: {preload_result}")
                
                # 재시도
                self.vectorstore = self.index_manager.get_vectorstore(self.domain)
                if self.vectorstore:
                    logger.info(f"✅ {self.domain} 재로드 성공!")
                else:
                    logger.error(f"❌ {self.domain} 재로드도 실패")
                    
        except Exception as e:
            logger.error(f"❌ 벡터스토어 로드 오류: {e}")
            if DEBUG_MODE:
                import traceback
                traceback.print_exc()
            self.vectorstore = None
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """
        사이버교육 검색 메인 메서드
        
        Args:
            query: 사용자 질문
            
        Returns:
            List[ChunkResult]: 검색 결과 (상위 3개)
        """
        # 사전 체크
        if not self._is_ready():
            logger.error("사이버교육 핸들러가 준비되지 않음")
            return []
        
        try:
            if DEBUG_MODE:
                logger.info(f"🔍 사이버교육 검색 시작: '{query}'")
            
            # 1. FAISS 검색 실행
            docs_with_scores = self.vectorstore.similarity_search_with_score(
                query, k=self.search_k
            )
            
            if not docs_with_scores:
                logger.warning("검색 결과 없음")
                return []
            
            # 2. 쿼리 분석 (플랫폼, 의도, 키워드)
            preferred_platform = self._analyze_platform_preference(query)
            query_intent = self._analyze_query_intent(query)
            
            if DEBUG_MODE and preferred_platform:
                logger.info(f"📱 플랫폼 선호: {preferred_platform}")
            if DEBUG_MODE and query_intent != "general":
                logger.info(f"🎯 쿼리 의도: {query_intent}")
            
            # 3. ChunkResult 생성 및 가중치 적용
            chunk_results = []
            for i, (doc, distance_score) in enumerate(docs_with_scores):
                # 거리 → 유사도 변환 (코랩 방식)
                similarity = self._distance_to_similarity(distance_score)
                
                # 순위 페널티 적용
                rank_penalty = i * 0.02
                confidence = similarity - rank_penalty
                
                # 사이버교육 가중치 적용
                confidence = self._apply_cyber_weights(
                    confidence, doc.metadata, preferred_platform, query_intent
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
            
            logger.info(f"사이버교육 검색 완료: {len(top_chunks)}개 반환 (최고 confidence: {top_chunks[0].confidence:.3f})")
            
            return top_chunks
            
        except Exception as e:
            logger.error(f"사이버교육 검색 실패: {e}")
            if DEBUG_MODE:
                import traceback
                traceback.print_exc()
            return []
    
    def _is_ready(self) -> bool:
        """핸들러 준비 상태 체크 - 상세 진단"""
        ready = (
            self.index_manager is not None and 
            self.vectorstore is not None
        )
        
        if not ready:
            logger.error("❌ 사이버교육 핸들러 준비 실패:")
            logger.error(f"   - IndexManager: {'✅' if self.index_manager else '❌'}")
            logger.error(f"   - Vectorstore: {'✅' if self.vectorstore else '❌'}")
            
            # 추가 진단 정보
            if self.index_manager:
                try:
                    health = self.index_manager.health_check()
                    logger.error(f"   - 시스템 상태: {health.get('service_available', False)}")
                    logger.error(f"   - 로드된 도메인: {health.get('loaded_domains', 0)}/{health.get('total_domains', 6)}")
                    
                    # cyber 도메인 상세 상태
                    domain_status = health.get('domain_status', {}).get('cyber', {})
                    logger.error(f"   - cyber 상태: {domain_status}")
                except Exception as e:
                    logger.error(f"   - 상태 체크 실패: {e}")
        
        return ready
    
    def _analyze_platform_preference(self, query: str) -> Optional[str]:
        """쿼리에서 선호하는 플랫폼 분석"""
        query_lower = query.lower()
        
        # mingan 키워드 체크
        if any(keyword in query_lower for keyword in MINGAN_KEYWORDS):
            return "mingan"
        
        # nara 키워드 체크
        if any(keyword in query_lower for keyword in NARA_KEYWORDS):
            return "nara"
        
        return None
    
    def _analyze_query_intent(self, query: str) -> str:
        """쿼리 의도 분석 (전문성 vs 편의성 vs 최신성)"""
        query_lower = query.lower()
        
        # 전문성 추구 키워드 체크
        if any(keyword in query_lower for keyword in PROFESSIONAL_KEYWORDS):
            return "professional"
        
        # 편의성 추구 키워드 체크
        if any(keyword in query_lower for keyword in CONVENIENCE_KEYWORDS):
            return "convenience"
        
        # 최신성 추구 키워드 체크
        if any(keyword in query_lower for keyword in RECENT_KEYWORDS):
            return "recent"
        
        return "general"
    
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
        adjusted = confidence
        
        # 1. 플랫폼 매칭 보너스
        cyber_type = metadata.get('cyber_type', '')
        if preferred_platform and cyber_type == preferred_platform:
            adjusted += PLATFORM_MATCH_BOOST
            if DEBUG_MODE:
                logger.debug(f"플랫폼 매칭 보너스: +{PLATFORM_MATCH_BOOST}")
        
        # 2. 학습시간 기반 가중치 (쿼리 의도 고려)
        learning_hours = self._extract_learning_hours(metadata)
        
        if query_intent == "professional":
            # 전문성 추구: 긴 과정 페널티 제거
            if learning_hours <= SHORT_LEARNING_THRESHOLD:
                adjusted += SHORT_LEARNING_BOOST * 0.5  # 보너스 절반
        elif query_intent == "convenience":
            # 편의성 추구: 짧은 과정 보너스 강화
            if learning_hours <= SHORT_LEARNING_THRESHOLD:
                adjusted += SHORT_LEARNING_BOOST * 1.5  # 보너스 강화
                if DEBUG_MODE:
                    logger.debug(f"편의성 추구 - 짧은 학습시간 보너스 강화: +{SHORT_LEARNING_BOOST * 1.5} ({learning_hours}h)")
            elif learning_hours >= LONG_LEARNING_THRESHOLD:
                adjusted += LONG_LEARNING_PENALTY * 1.5  # 페널티 강화
        else:
            # 일반적인 경우
            if learning_hours <= SHORT_LEARNING_THRESHOLD:
                adjusted += SHORT_LEARNING_BOOST
                if DEBUG_MODE:
                    logger.debug(f"짧은 학습시간 보너스: +{SHORT_LEARNING_BOOST} ({learning_hours}h)")
            elif learning_hours >= LONG_LEARNING_THRESHOLD:
                adjusted += LONG_LEARNING_PENALTY
                if DEBUG_MODE:
                    logger.debug(f"긴 학습시간 페널티: {LONG_LEARNING_PENALTY} ({learning_hours}h)")
        
        # 3. 인정시간 효율성 보너스
        recognition_hours = metadata.get('recognition_hours', 0)
        if learning_hours > 0 and recognition_hours > 0:
            try:
                efficiency_ratio = float(recognition_hours) / float(learning_hours)
                if efficiency_ratio >= HIGH_EFFICIENCY_RATIO:
                    adjusted += HIGH_EFFICIENCY_BOOST
                    if DEBUG_MODE:
                        logger.debug(f"높은 효율성 보너스: +{HIGH_EFFICIENCY_BOOST} (비율: {efficiency_ratio:.2f})")
            except (ValueError, TypeError, ZeroDivisionError):
                pass
        
        # 4. 최신성 가중치 (쿼리 의도 고려)
        dev_year = metadata.get('development_year', 0)
        if dev_year:
            try:
                year = int(dev_year)
                recent_boost = RECENT_CONTENT_BOOST
                old_penalty = OLD_CONTENT_PENALTY
                
                if query_intent == "recent":
                    # 최신성 추구: 최신 보너스 강화
                    recent_boost *= 2.0
                    old_penalty *= 2.0
                
                if year >= RECENT_DEVELOPMENT_THRESHOLD:
                    adjusted += recent_boost
                    if DEBUG_MODE:
                        logger.debug(f"최신 콘텐츠 보너스: +{recent_boost} ({year}년)")
                elif year <= OLD_DEVELOPMENT_THRESHOLD:
                    adjusted += old_penalty
                    if DEBUG_MODE:
                        logger.debug(f"오래된 콘텐츠 페널티: {old_penalty} ({year}년)")
            except (ValueError, TypeError):
                pass
        
        # 5. 평가 없음 보너스 (나라배움터만)
        if cyber_type == 'nara':
            evaluation = metadata.get('evaluation_required', '')
            if '없습니다' in str(evaluation):
                adjusted += EVALUATION_FREE_BOOST
                if DEBUG_MODE:
                    logger.debug(f"평가 없음 보너스: +{EVALUATION_FREE_BOOST}")
        
        return adjusted
    
    def _extract_learning_hours(self, metadata: Dict[str, Any]) -> float:
        """
        메타데이터에서 학습시간 추출 (안전한 방식)
        
        Args:
            metadata: 문서 메타데이터
            
        Returns:
            float: 학습시간 (시간 단위)
        """
        cyber_type = metadata.get('cyber_type', '')
        
        try:
            if cyber_type == 'mingan':
                # 민간위탁: learning_hours 사용
                return float(metadata.get('learning_hours', 0))
            elif cyber_type == 'nara':
                # 나라배움터: learning_sessions를 학습시간으로 처리
                sessions = metadata.get('learning_sessions', '0')
                return float(str(sessions).strip())
        except (ValueError, TypeError):
            pass
        
        return 0.0
    
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
            "department": self.department_info.get("department", "사이버담당"),
            "contact": self.department_info.get("contact", "055-254-2081"),
            "description": self.department_info.get("description", "사이버교육 관리"),
            
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
                "short_learning_threshold": SHORT_LEARNING_THRESHOLD,
                "long_learning_threshold": LONG_LEARNING_THRESHOLD,
                "high_efficiency_ratio": HIGH_EFFICIENCY_RATIO,
                "low_efficiency_ratio": LOW_EFFICIENCY_RATIO,
                "recent_development_threshold": RECENT_DEVELOPMENT_THRESHOLD,
                "old_development_threshold": OLD_DEVELOPMENT_THRESHOLD,
                "platform_match_boost": PLATFORM_MATCH_BOOST,
                "short_learning_boost": SHORT_LEARNING_BOOST,
                "high_efficiency_boost": HIGH_EFFICIENCY_BOOST,
                "recent_content_boost": RECENT_CONTENT_BOOST,
                "evaluation_free_boost": EVALUATION_FREE_BOOST,
                "long_learning_penalty": LONG_LEARNING_PENALTY,
                "old_content_penalty": OLD_CONTENT_PENALTY
            },
            "keywords": {
                "professional": PROFESSIONAL_KEYWORDS,
                "convenience": CONVENIENCE_KEYWORDS,
                "recent": RECENT_KEYWORDS,
                "mingan": MINGAN_KEYWORDS,
                "nara": NARA_KEYWORDS
            },
            "version": "5.0",
            "debug_mode": DEBUG_MODE
        }

# =============================================================================
# 편의 함수들
# =============================================================================

def create_cyber_handler() -> CyberHandler:
    """
    CyberHandler 인스턴스 생성 편의 함수
    
    Returns:
        CyberHandler: 최적화된 핸들러 인스턴스
    """
    return CyberHandler()

def update_tuning_settings(**kwargs):
    """
    파인튜닝 설정 업데이트 편의 함수
    
    사용법:
        update_tuning_settings(
            SHORT_LEARNING_THRESHOLD=4.0,
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
        "SHORT_LEARNING_THRESHOLD": SHORT_LEARNING_THRESHOLD,
        "LONG_LEARNING_THRESHOLD": LONG_LEARNING_THRESHOLD,
        "HIGH_EFFICIENCY_RATIO": HIGH_EFFICIENCY_RATIO,
        "RECENT_DEVELOPMENT_THRESHOLD": RECENT_DEVELOPMENT_THRESHOLD,
        "PLATFORM_MATCH_BOOST": PLATFORM_MATCH_BOOST,
        "SHORT_LEARNING_BOOST": SHORT_LEARNING_BOOST,
        "DEBUG_MODE": DEBUG_MODE
    }

# =============================================================================
# 테스트 코드
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 사이버교육 핸들러 v5.0 테스트 ===")
    
    try:
        # 핸들러 초기화 테스트
        handler = CyberHandler()
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
                
                for j, result in enumerate(results, 1):
                    print(f"  {j}. confidence: {result.confidence:.3f}")
                    print(f"     domain: {result.domain}")
                    print(f"     content: {result.chunk.content[:100]}...")
                    
            except Exception as e:
                print(f"❌ 테스트 {i} 실패: {e}")
        
        print("\n🎉 모든 테스트 완료!")
        
        # 파인튜닝 예시
        print("\n🔧 파인튜닝 예시:")
        print("update_tuning_settings(SHORT_LEARNING_THRESHOLD=4.0, DEBUG_MODE=False)")
        
    except Exception as e:
        print(f"\n❌ 핸들러 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
