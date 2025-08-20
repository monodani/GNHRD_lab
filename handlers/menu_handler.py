# handlers/menu_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 구내식당 메뉴 핸들러 v4.0
Architecture.md 기반 검색 전용 핸들러

핵심 기능:
- 검색만 담당 (LLM 호출 없음)
- 절대적 Confidence 기반 (FAISS distance → similarity 변환)
- 최소 지능형: 시간 기반 간단한 가중치만 적용
- 메타데이터 활용 (별도 파싱 없음)
- 파인튜닝 편의성 극대화

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-20
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from utils.contracts import ChunkResult, TextChunk
from utils.index_manager import get_index_manager
from config.thresholds import HANDLER_THRESHOLDS, DEPARTMENT_CONTACTS

# =============================================================================
# 로거 설정
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# MenuHandler 클래스
# =============================================================================

class MenuHandler:
    """
    구내식당 메뉴 검색 핸들러
    
    처리 범위:
    - menu.png (ChatGPT API 파싱된 주간 식단표)
    - 요일별/식사별 메뉴 정보
    - 시간 기반 최소 지능형 가중치 적용
    """
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
    # ================================================================
    
    # 시간 기반 간단한 가중치 (최소 지능형)
    CURRENT_DAY_BOOST = 0.02         # 오늘 식단 보너스
    CURRENT_MEAL_BOOST = 0.03        # 현재 식사 시간 보너스
    WEEKEND_PENALTY = -0.01          # 주말 페널티 (구내식당 운영 확인 필요)
    
    # 요일 매핑 (한글 ↔ 영문)
    KOREAN_WEEKDAYS = {
        0: "월요일", 1: "화요일", 2: "수요일", 
        3: "목요일", 4: "금요일", 5: "토요일", 6: "일요일"
    }
    
    # 시간대별 식사 타입 매핑
    MEAL_TIME_MAPPING = {
        "morning": "조식",    # 0-9시
        "lunch": "중식",      # 9-14시  
        "dinner": "석식"      # 14-24시
    }
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 끝
    # ================================================================
    
    def __init__(self):
        """MenuHandler 초기화"""
        self.threshold = HANDLER_THRESHOLDS["menu"]  # 0.40
        self.department_info = DEPARTMENT_CONTACTS["menu"]
        self.index_manager = get_index_manager()
        
        logger.info(f"✅ MenuHandler 초기화 완료 (임계값: {self.threshold})")
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """
        구내식당 메뉴 검색 전용 메서드
        
        Args:
            query: 사용자 질문
            
        Returns:
            List[ChunkResult]: 검색 결과 (상위 3개)
        """
        try:
            # 1. FAISS 검색 수행
            vectorstore = self.index_manager.get_vectorstore("menu")
            docs_with_scores = vectorstore.similarity_search_with_score(query, k=5)
            
            if not docs_with_scores:
                logger.warning("구내식당 메뉴 검색 결과가 없습니다.")
                return []
            
            # 2. 현재 시간 정보 계산
            current_time = datetime.now()
            current_weekday = current_time.weekday()  # 0=월요일
            current_hour = current_time.hour
            current_korean_weekday = self.KOREAN_WEEKDAYS[current_weekday]
            current_meal_type = self._get_current_meal_type(current_hour)
            
            # 3. ChunkResult 생성 및 최소 지능형 가중치 적용
            chunk_results = []
            for i, (doc, distance_score) in enumerate(docs_with_scores):
                # 거리 → 유사도 변환
                similarity = self._distance_to_similarity(distance_score)
                
                # 순위 기반 미세 조정
                rank_penalty = i * 0.02  # 1등: 0, 2등: -0.02, 3등: -0.04, ...
                confidence = similarity - rank_penalty
                
                # 최소 지능형: 시간 기반 가중치 적용
                confidence = self._apply_time_based_weights(
                    confidence, doc.metadata, current_korean_weekday, 
                    current_meal_type, current_weekday
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
                    domain="menu",
                    search_method="faiss",
                    metadata=self._create_menu_metadata(
                        doc, i + 1, distance_score, similarity
                    )
                )
                
                chunk_results.append(chunk_result)
            
            # 4. confidence 순으로 재정렬 후 상위 3개 반환
            chunk_results.sort(key=lambda x: x.confidence, reverse=True)
            top_chunks = chunk_results[:3]
            
            logger.info(
                f"구내식당 메뉴 검색 완료: {len(top_chunks)}개 반환 "
                f"(최고 confidence: {top_chunks[0].confidence:.3f})"
            )
            
            return top_chunks
            
        except Exception as e:
            logger.error(f"구내식당 메뉴 검색 실패: {e}")
            return []
    
    def _get_current_meal_type(self, hour: int) -> str:
        """
        현재 시간 기준 식사 타입 반환
        
        Args:
            hour: 현재 시간 (0-23)
            
        Returns:
            str: "조식", "중식", "석식"
        """
        if hour < 9:
            return self.MEAL_TIME_MAPPING["morning"]  # 조식
        elif hour < 14:
            return self.MEAL_TIME_MAPPING["lunch"]    # 중식
        else:
            return self.MEAL_TIME_MAPPING["dinner"]   # 석식
    
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
    
    def _apply_time_based_weights(
        self, 
        confidence: float, 
        metadata: Dict[str, Any], 
        current_korean_weekday: str,
        current_meal_type: str,
        current_weekday: int
    ) -> float:
        """
        최소 지능형: 시간 기반 가중치 적용 (메타데이터 활용)
        
        Args:
            confidence: 기본 confidence 점수
            metadata: 문서 메타데이터 (loader에서 생성)
            current_korean_weekday: 현재 한글 요일 ("월요일")
            current_meal_type: 현재 식사 타입 ("중식")
            current_weekday: 현재 요일 번호 (0=월요일)
            
        Returns:
            float: 가중치 적용된 confidence
        """
        adjusted_confidence = confidence
        
        # 1. 오늘 식단 보너스 (메타데이터의 'day'와 현재 요일 비교)
        menu_day = metadata.get('day')
        if menu_day == current_korean_weekday:
            adjusted_confidence += self.CURRENT_DAY_BOOST
            logger.debug(f"오늘 식단 보너스 적용: +{self.CURRENT_DAY_BOOST} (요일: {menu_day})")
        
        # 2. 현재 식사 시간 보너스 (메타데이터의 'meal_type'과 현재 식사 시간 비교)
        menu_meal_type = metadata.get('meal_type')
        if menu_meal_type == current_meal_type:
            adjusted_confidence += self.CURRENT_MEAL_BOOST
            logger.debug(f"현재 식사 시간 보너스 적용: +{self.CURRENT_MEAL_BOOST} (식사: {menu_meal_type})")
        
        # 3. 주말 페널티 (토요일=5, 일요일=6)
        if current_weekday >= 5:  # 주말
            adjusted_confidence += self.WEEKEND_PENALTY
            logger.debug(f"주말 페널티 적용: {self.WEEKEND_PENALTY}")
        
        return adjusted_confidence
    
    def _create_menu_metadata(
        self, 
        doc, 
        rank: int, 
        distance_score: float, 
        similarity_score: float
    ) -> Dict[str, Any]:
        """
        구내식당 메뉴 특화 메타데이터 생성
        
        Args:
            doc: 검색된 문서
            rank: 검색 순위
            distance_score: FAISS 거리 점수
            similarity_score: 변환된 유사도 점수
            
        Returns:
            Dict: 구내식당 메뉴 특화 메타데이터
        """
        base_metadata = doc.metadata.copy()
        
        # 현재 시간 맥락 정보 추가
        current_time = datetime.now()
        current_weekday = current_time.weekday()
        current_korean_weekday = self.KOREAN_WEEKDAYS[current_weekday]
        current_meal_type = self._get_current_meal_type(current_time.hour)
        
        # 구내식당 핸들러 특화 정보 추가
        base_metadata.update({
            "department": self.department_info["department"],
            "contact": self.department_info["phone"],
            "description": self.department_info["description"],
            "rank": rank,
            "distance_score": distance_score,
            "similarity_score": similarity_score,
            "handler_type": "menu",
            "threshold": self.threshold,
            # 시간 맥락 정보 (디버깅/UI용)
            "current_weekday": current_korean_weekday,
            "current_meal_type": current_meal_type,
            "is_weekend": current_weekday >= 5,
            "is_current_day": base_metadata.get('day') == current_korean_weekday,
            "is_current_meal": base_metadata.get('meal_type') == current_meal_type
        })
        
        return base_metadata
    
    def get_handler_info(self) -> Dict[str, Any]:
        """
        핸들러 정보 반환 (디버깅/모니터링용)
        
        Returns:
            Dict: 핸들러 설정 정보
        """
        return {
            "domain": "menu",
            "threshold": self.threshold,
            "department_info": self.department_info,
            "approach": "최소 지능형 (시간 기반 간단 가중치)",
            "settings": {
                "current_day_boost": self.CURRENT_DAY_BOOST,
                "current_meal_boost": self.CURRENT_MEAL_BOOST,
                "weekend_penalty": self.WEEKEND_PENALTY,
                "korean_weekdays": self.KOREAN_WEEKDAYS,
                "meal_time_mapping": self.MEAL_TIME_MAPPING
            },
            "features": [
                "오늘 식단 우선 표시",
                "현재 식사 시간 고려",
                "주말 운영 안내",
                "메타데이터 기반 시간 맥락"
            ],
            "supported_data": [
                "주간 식단표 (menu.png)",
                "요일별 메뉴 (월~금)",
                "식사별 메뉴 (조식/중식/석식)"
            ]
        }

# =============================================================================
# 편의 함수들
# =============================================================================

def create_menu_handler() -> MenuHandler:
    """
    MenuHandler 인스턴스 생성 편의 함수
    
    Returns:
        MenuHandler: 구내식당 메뉴 핸들러 인스턴스
    """
    return MenuHandler()

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 구내식당 메뉴 핸들러 테스트 ===")
    
    try:
        # 핸들러 초기화 테스트
        handler = MenuHandler()
        print(f"✅ 핸들러 초기화: 임계값 = {handler.threshold}")
        
        # 설정 정보 출력
        info = handler.get_handler_info()
        print(f"✅ 핸들러 정보: {info['domain']}")
        print(f"✅ 담당부서: {info['department_info']['department']}")
        print(f"✅ 접근 방식: {info['approach']}")
        print(f"✅ 특징: {', '.join(info['features'])}")
        
        # 현재 시간 기준 테스트
        current_time = datetime.now()
        current_meal = handler._get_current_meal_type(current_time.hour)
        current_day = handler.KOREAN_WEEKDAYS[current_time.weekday()]
        print(f"✅ 현재 시간 맥락: {current_day} {current_meal} ({current_time.hour}시)")
        
        # 테스트 쿼리들
        test_queries = [
            "오늘 점심 메뉴가 뭐야?",           # 현재 식사 + 오늘
            "내일 아침 식단 알려줘",            # 미래 식사
            "이번주 월요일 저녁은?",            # 특정 요일
            "구내식당 운영시간은?",             # 일반 정보
            "금요일 전체 식단 보여줘"           # 하루 전체
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n--- 테스트 {i}: {query} ---")
            
            try:
                results = handler.search_chunks(query)
                print(f"검색 결과: {len(results)}개")
                
                for j, result in enumerate(results):
                    meta = result.metadata
                    print(f"  {j+1}. confidence: {result.confidence:.3f}")
                    print(f"     domain: {result.domain}")
                    print(f"     day: {result.chunk.metadata.get('day', 'unknown')}")
                    print(f"     meal_type: {result.chunk.metadata.get('meal_type', 'unknown')}")
                    print(f"     is_current_day: {meta.get('is_current_day', False)}")
                    print(f"     is_current_meal: {meta.get('is_current_meal', False)}")
                    
            except Exception as e:
                print(f"❌ 테스트 {i} 실패: {e}")
        
        print("\n🎉 모든 테스트 완료!")
        
    except Exception as e:
        print(f"\n❌ 핸들러 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
