# handlers/notice_handler.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 공지사항 핸들러 v4.0
Architecture.md 기반 검색 전용 핸들러

핵심 기능:
- 검색만 담당 (LLM 호출 없음)
- 절대적 Confidence 기반 (FAISS distance → similarity 변환)
- 공지사항 메타데이터 기반 지능형 필터링 및 가중치
- 시간 기반 우선순위, 긴급도 분류, 마감일 근접성 필터링
- 파인튜닝 편의성 극대화

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-20
"""

import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from utils.contracts import ChunkResult, TextChunk
from utils.index_manager import get_index_manager
from config.thresholds import HANDLER_THRESHOLDS, DEPARTMENT_CONTACTS

# =============================================================================
# 로거 설정
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# NoticeHandler 클래스
# =============================================================================

class NoticeHandler:
    """
    공지사항 검색 핸들러
    
    처리 범위:
    - notice.txt (동적 파싱된 공지사항)
    - 평가, 입교, 모집, 일정, 일반 공지 등 다양한 유형
    - 긴급도 및 마감일 기반 지능형 우선순위 처리
    """
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
    # ================================================================
    
    # 긴급도 키워드별 가중치
    URGENT_KEYWORDS = ["긴급", "즉시", "반드시", "중요", "주의", "필수"]
    DEADLINE_KEYWORDS = ["마감", "기한", "제출", "감점", "초과", "시간당"]
    
    # 타입별 우선순위 가중치 (evaluation이 가장 높음)
    TYPE_PRIORITY_BOOST = {
        "evaluation": 0.06,    # 평가 관련 최우선 (점수/마감일 중요)
        "enrollment": 0.04,    # 입교 관련 
        "recruitment": 0.03,   # 모집 관련
        "schedule": 0.02,      # 일정 관련
        "general": 0.01        # 일반 공지
    }
    
    # 시간 기반 가중치
    URGENT_BOOST = 0.05           # 긴급 키워드 발견시
    DEADLINE_BOOST = 0.04         # 마감일 키워드 발견시
    RECENT_BOOST = 0.03           # 최신 공지 (7일 이내)
    
    # 마감일 근접성 (현재 날짜 기준)
    DEADLINE_IMMINENT_BOOST = 0.07  # 3일 이내 마감 (가장 중요)
    DEADLINE_SOON_BOOST = 0.04      # 7일 이내 마감
    DEADLINE_THIS_MONTH_BOOST = 0.02  # 30일 이내 마감
    
    # 최신성 기준 (일 단위)
    RECENT_DAYS_THRESHOLD = 7      # 최신 공지 기준
    
    # 마감일 파싱 패턴
    DEADLINE_PATTERNS = [
        r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\.\s*\([^)]+\)\s*(\d{1,2}):(\d{2})',  # 2025. 9. 25.(목) 17:00
        r'(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})\s*(\d{1,2}):(\d{2})',  # 2025. 9. 25 17:00
        r'(\d{1,2})월\s*(\d{1,2})일\s*(\d{1,2}):(\d{2})',  # 9월 25일 17:00
        r'(\d{1,2})/(\d{1,2})\s*(\d{1,2}):(\d{2})',  # 9/25 17:00
    ]
    
    # ================================================================
    # 🔧 파인튜닝 설정 구역 끝
    # ================================================================
    
    def __init__(self):
        """NoticeHandler 초기화"""
        self.threshold = HANDLER_THRESHOLDS["notice"]  # 0.42
        self.department_info = DEPARTMENT_CONTACTS["notice"]
        self.index_manager = get_index_manager()
        
        logger.info(f"✅ NoticeHandler 초기화 완료 (임계값: {self.threshold})")
    
    def search_chunks(self, query: str) -> List[ChunkResult]:
        """
        공지사항 검색 전용 메서드
        
        Args:
            query: 사용자 질문
            
        Returns:
            List[ChunkResult]: 검색 결과 (상위 3개)
        """
        try:
            # 1. FAISS 검색 수행
            vectorstore = self.index_manager.get_vectorstore("notice")
            docs_with_scores = vectorstore.similarity_search_with_score(query, k=5)
            
            if not docs_with_scores:
                logger.warning("공지사항 검색 결과가 없습니다.")
                return []
            
            # 2. 쿼리 분석 (긴급도, 마감일 관련 키워드)
            query_urgency = self._analyze_query_urgency(query)
            
            # 3. ChunkResult 생성 및 가중치 적용
            chunk_results = []
            for i, (doc, distance_score) in enumerate(docs_with_scores):
                # 거리 → 유사도 변환
                similarity = self._distance_to_similarity(distance_score)
                
                # 순위 기반 미세 조정
                rank_penalty = i * 0.02  # 1등: 0, 2등: -0.02, 3등: -0.04, ...
                confidence = similarity - rank_penalty
                
                # 공지사항 메타데이터 기반 지능형 가중치 적용
                confidence = self._apply_notice_weights(
                    confidence, doc.page_content, doc.metadata, query_urgency
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
                    domain="notice",
                    search_method="faiss",
                    metadata=self._create_notice_metadata(
                        doc, i + 1, distance_score, similarity
                    )
                )
                
                chunk_results.append(chunk_result)
            
            # 4. confidence 순으로 재정렬 후 상위 3개 반환
            chunk_results.sort(key=lambda x: x.confidence, reverse=True)
            top_chunks = chunk_results[:3]
            
            logger.info(
                f"공지사항 검색 완료: {len(top_chunks)}개 반환 "
                f"(최고 confidence: {top_chunks[0].confidence:.3f})"
            )
            
            return top_chunks
            
        except Exception as e:
            logger.error(f"공지사항 검색 실패: {e}")
            return []
    
    def _analyze_query_urgency(self, query: str) -> str:
        """
        쿼리에서 긴급성 및 시간 민감도 분석
        
        Args:
            query: 사용자 질문
            
        Returns:
            str: "urgent", "deadline", "recent", "general"
        """
        query_lower = query.lower()
        
        # 긴급성 키워드 체크
        if any(keyword in query_lower for keyword in self.URGENT_KEYWORDS):
            return "urgent"
        
        # 마감일 관련 키워드 체크
        if any(keyword in query_lower for keyword in self.DEADLINE_KEYWORDS):
            return "deadline"
        
        # 시간 관련 키워드 체크
        time_keywords = ["오늘", "내일", "이번주", "최신", "새로운", "최근"]
        if any(keyword in query_lower for keyword in time_keywords):
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
    
    def _apply_notice_weights(
        self, 
        confidence: float, 
        content: str, 
        metadata: Dict[str, Any], 
        query_urgency: str
    ) -> float:
        """
        공지사항 메타데이터 및 내용 기반 가중치 적용
        
        Args:
            confidence: 기본 confidence 점수
            content: 공지사항 내용
            metadata: 문서 메타데이터
            query_urgency: 쿼리 긴급성 분석 결과
            
        Returns:
            float: 가중치 적용된 confidence
        """
        adjusted_confidence = confidence
        
        # 1. 타입별 우선순위 가중치
        topic_type = metadata.get('topic_type', 'general')
        type_boost = self.TYPE_PRIORITY_BOOST.get(topic_type, 0.01)
        adjusted_confidence += type_boost
        logger.debug(f"타입별 가중치 적용: +{type_boost} (타입: {topic_type})")
        
        # 2. 긴급도 키워드 가중치
        content_lower = content.lower()
        if any(keyword in content_lower for keyword in self.URGENT_KEYWORDS):
            boost = self.URGENT_BOOST
            if query_urgency == "urgent":
                boost *= 1.5  # 쿼리도 긴급성이면 가중치 강화
            adjusted_confidence += boost
            logger.debug(f"긴급도 키워드 가중치: +{boost}")
        
        # 3. 마감일 관련 키워드 가중치
        if any(keyword in content_lower for keyword in self.DEADLINE_KEYWORDS):
            boost = self.DEADLINE_BOOST
            if query_urgency == "deadline":
                boost *= 1.3  # 쿼리도 마감일 관련이면 가중치 강화
            adjusted_confidence += boost
            logger.debug(f"마감일 키워드 가중치: +{boost}")
        
        # 4. 실제 마감일 파싱 및 근접성 가중치
        deadline_boost = self._calculate_deadline_proximity_boost(content)
        if deadline_boost > 0:
            adjusted_confidence += deadline_boost
            logger.debug(f"마감일 근접성 가중치: +{deadline_boost}")
        
        # 5. 최신성 가중치 (등록일 기준)
        recent_boost = self._calculate_recency_boost(metadata)
        if recent_boost > 0:
            adjusted_confidence += recent_boost
            logger.debug(f"최신성 가중치: +{recent_boost}")
        
        return adjusted_confidence
    
    def _calculate_deadline_proximity_boost(self, content: str) -> float:
        """
        공지사항 내용에서 마감일을 파싱하여 근접성 가중치 계산
        
        Args:
            content: 공지사항 내용
            
        Returns:
            float: 마감일 근접성 가중치
        """
        try:
            current_date = datetime.now()
            
            # 다양한 마감일 패턴으로 파싱 시도
            for pattern in self.DEADLINE_PATTERNS:
                matches = re.findall(pattern, content)
                if matches:
                    for match in matches:
                        try:
                            # 패턴별로 날짜 파싱
                            if len(match) == 5:  # 년월일시분 패턴
                                year, month, day, hour, minute = map(int, match)
                                deadline = datetime(year, month, day, hour, minute)
                            elif len(match) == 4:  # 월일시분 패턴 (현재 년도 가정)
                                month, day, hour, minute = map(int, match)
                                deadline = datetime(current_date.year, month, day, hour, minute)
                            else:
                                continue
                            
                            # 현재 시간과의 차이 계산
                            time_diff = deadline - current_date
                            days_until_deadline = time_diff.days
                            
                            # 이미 지난 마감일은 무시
                            if days_until_deadline < 0:
                                continue
                            
                            # 근접성별 가중치 반환
                            if days_until_deadline <= 3:
                                return self.DEADLINE_IMMINENT_BOOST  # 3일 이내
                            elif days_until_deadline <= 7:
                                return self.DEADLINE_SOON_BOOST      # 7일 이내
                            elif days_until_deadline <= 30:
                                return self.DEADLINE_THIS_MONTH_BOOST  # 30일 이내
                            
                        except (ValueError, TypeError):
                            continue
            
            return 0.0  # 마감일을 찾지 못하거나 파싱 실패
            
        except Exception as e:
            logger.warning(f"마감일 파싱 중 오류: {e}")
            return 0.0
    
    def _calculate_recency_boost(self, metadata: Dict[str, Any]) -> float:
        """
        메타데이터의 등록일을 기준으로 최신성 가중치 계산
        
        Args:
            metadata: 문서 메타데이터
            
        Returns:
            float: 최신성 가중치
        """
        try:
            processing_date = metadata.get('processing_date')
            if not processing_date:
                return 0.0
            
            # ISO 형태의 날짜 파싱
            if isinstance(processing_date, str):
                process_datetime = datetime.fromisoformat(processing_date.replace('Z', '+00:00'))
            else:
                return 0.0
            
            current_date = datetime.now()
            time_diff = current_date - process_datetime
            days_since_processed = time_diff.days
            
            # 최신성 가중치 계산
            if days_since_processed <= self.RECENT_DAYS_THRESHOLD:
                return self.RECENT_BOOST
            
            return 0.0
            
        except Exception as e:
            logger.warning(f"최신성 계산 중 오류: {e}")
            return 0.0
    
    def _extract_contact_from_content(self, content: str) -> Optional[str]:
        """
        공지사항 내용에서 연락처 정보 추출
        
        Args:
            content: 공지사항 내용
            
        Returns:
            Optional[str]: 추출된 연락처 정보
        """
        # 연락처 패턴들
        contact_patterns = [
            r'문의\s*[:：]\s*([^:\n]+)',
            r'연락처\s*[:：]\s*([^:\n]+)', 
            r'담당\s*[:：]\s*([^:\n]+)',
            r'(\d{3}-\d{3}-\d{4})',  # 전화번호 패턴
            r'(055-\d{3}-\d{4})',    # 경남 지역번호 우선
        ]
        
        for pattern in contact_patterns:
            match = re.search(pattern, content)
            if match:
                contact = match.group(1).strip()
                # 유효한 연락처인지 확인 (전화번호 포함)
                if re.search(r'\d{3}-\d{3}-\d{4}', contact):
                    return contact
        
        return None
    
    def _create_notice_metadata(
        self, 
        doc, 
        rank: int, 
        distance_score: float, 
        similarity_score: float
    ) -> Dict[str, Any]:
        """
        공지사항 특화 메타데이터 생성
        
        Args:
            doc: 검색된 문서
            rank: 검색 순위
            distance_score: FAISS 거리 점수
            similarity_score: 변환된 유사도 점수
            
        Returns:
            Dict: 공지사항 특화 메타데이터
        """
        base_metadata = doc.metadata.copy()
        
        # 공지사항 내용에서 연락처 추출 시도
        extracted_contact = self._extract_contact_from_content(doc.page_content)
        
        # 연락처 결정: 추출된 연락처 우선, 없으면 기본 담당부서
        if extracted_contact:
            department = f"해당 공지 담당부서"
            contact = extracted_contact
        else:
            department = self.department_info["department"]
            contact = self.department_info["phone"]
        
        # 공지사항 핸들러 특화 정보 추가
        base_metadata.update({
            "department": department,
            "contact": contact,
            "description": self.department_info["description"],
            "rank": rank,
            "distance_score": distance_score,
            "similarity_score": similarity_score,
            "handler_type": "notice",
            "threshold": self.threshold,
            "extracted_contact": extracted_contact  # 디버깅용
        })
        
        return base_metadata
    
    def get_handler_info(self) -> Dict[str, Any]:
        """
        핸들러 정보 반환 (디버깅/모니터링용)
        
        Returns:
            Dict: 핸들러 설정 정보
        """
        return {
            "domain": "notice",
            "threshold": self.threshold,
            "department_info": self.department_info,
            "settings": {
                "urgent_keywords": self.URGENT_KEYWORDS,
                "deadline_keywords": self.DEADLINE_KEYWORDS,
                "type_priority_boost": self.TYPE_PRIORITY_BOOST,
                "urgent_boost": self.URGENT_BOOST,
                "deadline_boost": self.DEADLINE_BOOST,
                "recent_boost": self.RECENT_BOOST,
                "deadline_imminent_boost": self.DEADLINE_IMMINENT_BOOST,
                "deadline_soon_boost": self.DEADLINE_SOON_BOOST,
                "deadline_this_month_boost": self.DEADLINE_THIS_MONTH_BOOST,
                "recent_days_threshold": self.RECENT_DAYS_THRESHOLD
            },
            "features": [
                "시간 기반 우선순위",
                "긴급도 키워드 분류",
                "마감일 근접성 필터링",
                "실제 마감일 파싱",
                "공지별 연락처 자동 추출",
                "타입별 차별화 가중치"
            ]
        }

# =============================================================================
# 편의 함수들
# =============================================================================

def create_notice_handler() -> NoticeHandler:
    """
    NoticeHandler 인스턴스 생성 편의 함수
    
    Returns:
        NoticeHandler: 공지사항 핸들러 인스턴스
    """
    return NoticeHandler()

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 공지사항 핸들러 테스트 ===")
    
    try:
        # 핸들러 초기화 테스트
        handler = NoticeHandler()
        print(f"✅ 핸들러 초기화: 임계값 = {handler.threshold}")
        
        # 설정 정보 출력
        info = handler.get_handler_info()
        print(f"✅ 핸들러 정보: {info['domain']}")
        print(f"✅ 담당부서: {info['department_info']['department']}")
        print(f"✅ 특징: {', '.join(info['features'])}")
        
        # 마감일 파싱 테스트
        test_content = "제출기한 : 2025. 9. 25.(목) 17:00까지 반드시 제출해야 합니다."
        deadline_boost = handler._calculate_deadline_proximity_boost(test_content)
        print(f"✅ 마감일 파싱 테스트: 가중치 = {deadline_boost}")
        
        # 연락처 추출 테스트
        test_content2 = "관련문의 : 인재개발지원과 사무실(5층) 방문 및 유선연락(055-254-2023)"
        contact = handler._extract_contact_from_content(test_content2)
        print(f"✅ 연락처 추출 테스트: {contact}")
        
        # 테스트 쿼리들
        test_queries = [
            "오늘 마감인 긴급 과제 있나요?",     # urgent + deadline
            "평가 관련 공지사항 확인",           # evaluation type
            "최신 입교 준비사항 알려주세요",      # recent + enrollment
            "모집 공고 중 중요한 것",           # recruitment + urgent
            "일반 공지사항 확인"                # general
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n--- 테스트 {i}: {query} ---")
            
            urgency = handler._analyze_query_urgency(query)
            print(f"쿼리 긴급성 분석: {urgency}")
            
            try:
                results = handler.search_chunks(query)
                print(f"검색 결과: {len(results)}개")
                
                for j, result in enumerate(results):
                    print(f"  {j+1}. confidence: {result.confidence:.3f}")
                    print(f"     domain: {result.domain}")
                    print(f"     topic_type: {result.chunk.metadata.get('topic_type', 'unknown')}")
                    print(f"     contact: {result.metadata.get('contact', 'N/A')}")
                    
            except Exception as e:
                print(f"❌ 테스트 {i} 실패: {e}")
        
        print("\n🎉 모든 테스트 완료!")
        
    except Exception as e:
        print(f"\n❌ 핸들러 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
