# utils/feedback_manager.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 피드백 시스템 관리자 v3.1
Firestore 기반 실시간 피드백 수집 및 관리

핵심 기능:
- 실시간 피드백 저장 (Firestore)
- 연결 실패시 session_state 백업 + 자동 재시도
- 관리자 대시보드용 통계 조회 (24시간 캐시)
- Graceful degradation (앱 중단 없음)

설계 원칙:
- config.py 완전 연동
- contracts.py FeedbackData 활용
- 사용자 친화적 에러 처리
- 군더더기 없는 아름다운 구조

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-18
"""

import json
import logging
import streamlit as st
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import asdict

try:
    from google.cloud import firestore
    from google.oauth2 import service_account
    from google.api_core.exceptions import GoogleAPIError, DeadlineExceeded
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False

from config.config import get_feedback_config
from utils.contracts import FeedbackData, FeedbackType

# =============================================================================
# 로거 설정
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# 상수 정의 (사용자 메시지)
# =============================================================================

SUCCESS_MESSAGE = "피드백 감사합니다! 🙏"
NETWORK_ERROR_MESSAGE = "네트워크 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
SAVE_ERROR_MESSAGE = "피드백 전송에 실패했습니다. 죄송합니다. 잠시 후 다시 시도해 주세요."
FIRESTORE_UNAVAILABLE_MESSAGE = "피드백 시스템이 일시적으로 사용할 수 없습니다."

# 한국 시간대 설정
KST = timezone(timedelta(hours=9))

# =============================================================================
# FeedbackManager 클래스
# =============================================================================

class FeedbackManager:
    """
    Firestore 기반 피드백 시스템 관리자
    
    주요 기능:
    - 피드백 저장 (실패시 session_state 백업)
    - 통계 조회 (24시간 캐시)
    - 에러 로깅
    - 자동 재시도 메커니즘
    """
    
    def __init__(self):
        """FeedbackManager 초기화"""
        self.config = get_feedback_config()
        self.db = None
        self.is_firestore_available = False
        
        # Firestore 초기화 시도
        if self.config['enabled'] and FIRESTORE_AVAILABLE:
            self._initialize_firestore()
        else:
            logger.warning("피드백 시스템이 비활성화되었거나 Firestore 라이브러리가 없습니다.")
    
    def _initialize_firestore(self) -> None:
        """
        Firestore 클라이언트 초기화
        
        Streamlit Secrets에서 JSON 키를 로드하여 인증
        실패해도 앱이 중단되지 않도록 안전하게 처리
        """
        try:
            firestore_key = self.config.get('firestore_key')
            if not firestore_key:
                logger.warning("FIRESTORE_KEY가 설정되지 않았습니다.")
                return
            
            # JSON 키 파싱
            if isinstance(firestore_key, str):
                key_dict = json.loads(firestore_key)
            else:
                key_dict = firestore_key
            
            # 서비스 계정 인증
            credentials = service_account.Credentials.from_service_account_info(key_dict)
            
            # Firestore 클라이언트 생성
            self.db = firestore.Client(
                project=self.config['project_id'],
                credentials=credentials
            )
            
            # 연결 테스트 (간단한 쿼리)
            test_collection = self.db.collection(self.config['collection_feedbacks'])
            test_collection.limit(1).get()
            
            self.is_firestore_available = True
            logger.info("✅ Firestore 연결 성공")
            
        except json.JSONDecodeError as e:
            logger.error(f"Firestore 키 JSON 파싱 실패: {e}")
        except GoogleAPIError as e:
            logger.error(f"Firestore API 에러: {e}")
        except Exception as e:
            logger.error(f"Firestore 초기화 실패: {e}")
    
    def save_feedback(self, feedback_data: FeedbackData) -> bool:
        """
        피드백 데이터 저장

        Args:
            feedback_data: 저장할 피드백 데이터

        Returns:
            bool: 저장 성공 여부

        처리 순서:
        1. 백업된 피드백들 먼저 재시도
        2. 현재 피드백 저장 시도
        3. 실패시 session_state에 백업
        """
        if not self.is_firestore_available:
            logger.warning("Firestore를 사용할 수 없어 피드백을 백업합니다.")
            self._backup_to_session_state(feedback_data)
            return False

        try:
            # 1. 백업된 피드백들 먼저 재시도
            self._retry_pending_feedbacks()

            # 2. 현재 피드백 저장 시도
            feedback_dict = feedback_data.to_dict()

            # 한국 시간으로 타임스탬프 설정
            feedback_dict['timestamp'] = datetime.now(KST)

            # Firestore에 저장 (자동 문서 ID)
            doc_ref = self.db.collection(self.config['collection_feedbacks']).add(feedback_dict)

            logger.info(f"피드백 저장 성공: {doc_ref[1].id}")
            return True

        except Exception as e:
            logger.error(f"피드백 저장 실패: {e}")
            self._backup_to_session_state(feedback_data)
            return False

    
    def _backup_to_session_state(self, feedback_data: FeedbackData) -> None:
        """
        세션 상태에 피드백 백업
        
        Args:
            feedback_data: 백업할 피드백 데이터
        """
        if 'pending_feedbacks' not in st.session_state:
            st.session_state.pending_feedbacks = []
        
        feedback_dict = feedback_data.to_dict()
        feedback_dict['timestamp'] = datetime.now(KST).isoformat()  # 직렬화 가능한 형태
        
        st.session_state.pending_feedbacks.append(feedback_dict)
        
        logger.info(f"피드백 백업 저장 완료. 총 {len(st.session_state.pending_feedbacks)}개 대기 중")
    
    def _retry_pending_feedbacks(self) -> int:
        """
        백업된 피드백들 재시도
        
        Returns:
            int: 성공한 재시도 개수
        """
        if 'pending_feedbacks' not in st.session_state or not st.session_state.pending_feedbacks:
            return 0
        
        if not self.is_firestore_available:
            return 0
        
        success_count = 0
        remaining_feedbacks = []
        
        for feedback_dict in st.session_state.pending_feedbacks:
            try:
                # 타임스탬프 복원
                if isinstance(feedback_dict['timestamp'], str):
                    feedback_dict['timestamp'] = datetime.fromisoformat(feedback_dict['timestamp'])
                
                # Firestore에 저장
                self.db.collection(self.config['collection_feedbacks']).add(feedback_dict)
                success_count += 1
                
            except Exception as e:
                logger.warning(f"백업 피드백 재시도 실패: {e}")
                remaining_feedbacks.append(feedback_dict)
        
        # 성공한 것들은 제거, 실패한 것들만 유지
        st.session_state.pending_feedbacks = remaining_feedbacks
        
        if success_count > 0:
            logger.info(f"백업 피드백 {success_count}개 재전송 성공")
        
        return success_count
    
    @st.cache_data(ttl=86400)  # 24시간 캐시
    def get_feedback_stats(_self) -> Dict[str, Any]:
        """
        피드백 통계 조회 (24시간 캐시)
        
        Returns:
            Dict: 통계 데이터
        """
        if not _self.is_firestore_available:
            return {
                'total': 0,
                'positive': 0,
                'negative': 0,
                'positive_rate': 0.0,
                'error': 'Firestore 연결 불가'
            }
        
        try:
            feedbacks_ref = _self.db.collection(_self.config['collection_feedbacks'])
            
            # 효율적인 카운트 쿼리
            positive_count = len(feedbacks_ref.where('feedback_type', '==', 'positive').get())
            negative_count = len(feedbacks_ref.where('feedback_type', '==', 'negative').get())
            
            total = positive_count + negative_count
            positive_rate = round(positive_count / total * 100, 1) if total > 0 else 0.0
            
            return {
                'total': total,
                'positive': positive_count,
                'negative': negative_count,
                'positive_rate': positive_rate,
                'last_updated': datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')
            }
            
        except Exception as e:
            logger.error(f"피드백 통계 조회 실패: {e}")
            return {
                'total': 0,
                'positive': 0,
                'negative': 0,
                'positive_rate': 0.0,
                'error': str(e)
            }
    
    def get_recent_feedbacks(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        최근 피드백 목록 조회
        
        Args:
            limit: 조회할 최대 개수
            
        Returns:
            List[Dict]: 피드백 목록
        """
        if not self.is_firestore_available:
            return []
        
        try:
            feedbacks_ref = self.db.collection(self.config['collection_feedbacks'])
            docs = feedbacks_ref.order_by('timestamp', direction=firestore.Query.DESCENDING)\
                               .limit(limit)\
                               .stream()
            
            feedbacks = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                
                # 타임스탬프 포맷팅
                if 'timestamp' in data and data['timestamp']:
                    if hasattr(data['timestamp'], 'strftime'):
                        data['timestamp_formatted'] = data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        data['timestamp_formatted'] = str(data['timestamp'])
                
                feedbacks.append(data)
            
            return feedbacks
            
        except Exception as e:
            logger.error(f"최근 피드백 조회 실패: {e}")
            return []
    
    def get_pending_feedback_count(self) -> int:
        """
        백업된 피드백 개수 조회
        
        Returns:
            int: 대기 중인 피드백 개수
        """
        if 'pending_feedbacks' not in st.session_state:
            return 0
        return len(st.session_state.pending_feedbacks)
    
    def clear_pending_feedbacks(self) -> None:
        """백업된 피드백 삭제 (관리자용)"""
        if 'pending_feedbacks' in st.session_state:
            del st.session_state.pending_feedbacks
        logger.info("백업된 피드백을 모두 삭제했습니다.")
    
    def _log_error(self, error_type: str, error_message: str, session_id: str = None) -> None:
        """
        에러 로그를 Firestore에 저장
        
        Args:
            error_type: 에러 타입
            error_message: 에러 메시지
            session_id: 세션 ID (선택사항)
        """
        if not self.is_firestore_available:
            logger.error(f"에러 로그 저장 불가 - {error_type}: {error_message}")
            return
        
        try:
            error_data = {
                'error_type': error_type,
                'error_message': error_message,
                'timestamp': datetime.now(KST),
                'session_id': session_id or st.session_state.get('session_id', 'unknown')
            }
            
            self.db.collection(self.config['collection_errors']).add(error_data)
            logger.info(f"에러 로그 저장 완료: {error_type}")
            
        except Exception as e:
            logger.error(f"에러 로그 저장 실패: {e}")
    
    def get_error_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        에러 로그 조회 (관리자용)
        
        Args:
            limit: 조회할 최대 개수
            
        Returns:
            List[Dict]: 에러 로그 목록
        """
        if not self.is_firestore_available:
            return []
        
        try:
            errors_ref = self.db.collection(self.config['collection_errors'])
            docs = errors_ref.order_by('timestamp', direction=firestore.Query.DESCENDING)\
                            .limit(limit)\
                            .stream()
            
            errors = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                
                # 타임스탬프 포맷팅
                if 'timestamp' in data and data['timestamp']:
                    if hasattr(data['timestamp'], 'strftime'):
                        data['timestamp_formatted'] = data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        data['timestamp_formatted'] = str(data['timestamp'])
                
                errors.append(data)
            
            return errors
            
        except Exception as e:
            logger.error(f"에러 로그 조회 실패: {e}")
            return []
    
    def export_to_csv(self) -> str:
        """
        피드백 데이터를 CSV 형태로 내보내기 (관리자용)
        
        Returns:
            str: CSV 데이터
        """
        if not self.is_firestore_available:
            return "conversation_id,message_id,user_query,bot_response,feedback_type,feedback_reason,timestamp\n"
        
        try:
            feedbacks_ref = self.db.collection(self.config['collection_feedbacks'])
            docs = feedbacks_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
            
            csv_lines = ['conversation_id,message_id,user_query,bot_response,feedback_type,feedback_reason,timestamp']
            
            for doc in docs:
                data = doc.to_dict()
                
                # CSV 행 생성 (콤마와 줄바꿈 이스케이프)
                row = [
                    f'"{str(data.get("conversation_id", "")).replace('"', '""')}"',
                    f'"{str(data.get("message_id", "")).replace('"', '""')}"',
                    f'"{str(data.get("user_query", "")).replace('"', '""')}"',
                    f'"{str(data.get("bot_response", "")).replace('"', '""')}"',
                    f'"{str(data.get("feedback_type", "")).replace('"', '""')}"',
                    f'"{str(data.get("feedback_reason", "") or "").replace('"', '""')}"',
                    f'"{str(data.get("timestamp", "")).replace('"', '""')}"'
                ]
                
                csv_lines.append(','.join(row))
            
            return '\n'.join(csv_lines)
            
        except Exception as e:
            logger.error(f"CSV 내보내기 실패: {e}")
            return f"# 내보내기 실패: {str(e)}\n"
    
    def health_check(self) -> Dict[str, Any]:
        """
        시스템 상태 체크 (관리자용)
        
        Returns:
            Dict: 상태 정보
        """
        status = {
            'firestore_available': self.is_firestore_available,
            'config_loaded': bool(self.config),
            'pending_feedbacks': self.get_pending_feedback_count(),
            'timestamp': datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S KST')
        }
        
        if self.is_firestore_available:
            try:
                # 간단한 연결 테스트
                test_ref = self.db.collection(self.config['collection_feedbacks']).limit(1)
                list(test_ref.stream())
                status['firestore_connection'] = 'OK'
            except Exception as e:
                status['firestore_connection'] = f'Error: {str(e)}'
                self.is_firestore_available = False
        else:
            status['firestore_connection'] = 'Not Available'
        
        return status

# =============================================================================
# 전역 인스턴스 (싱글톤 패턴)
# =============================================================================

_feedback_manager: Optional[FeedbackManager] = None

def get_feedback_manager() -> FeedbackManager:
    """
    전역 FeedbackManager 인스턴스 반환 (싱글톤)
    
    Returns:
        FeedbackManager: 피드백 관리자 인스턴스
    """
    global _feedback_manager
    if _feedback_manager is None:
        _feedback_manager = FeedbackManager()
    return _feedback_manager

# =============================================================================
# 편의 함수들
# =============================================================================

def save_user_feedback(
    conversation_id: str,
    message_id: str,
    user_query: str,
    bot_response: str,
    feedback_type: str,
    feedback_reason: Optional[str] = None
) -> bool:
    """
    사용자 피드백 저장 편의 함수
    
    Args:
        conversation_id: 대화 ID
        message_id: 메시지 ID
        user_query: 사용자 질문
        bot_response: 봇 응답
        feedback_type: 피드백 타입 ("positive" | "negative")
        feedback_reason: 피드백 사유 (선택사항)
        
    Returns:
        bool: 저장 성공 여부
    """
    try:
        feedback_data = FeedbackData(
            conversation_id=conversation_id,
            message_id=message_id,
            user_query=user_query,
            bot_response=bot_response,
            feedback_type=FeedbackType(feedback_type),
            feedback_reason=feedback_reason
        )
        
        feedback_manager = get_feedback_manager()
        return feedback_manager.save_feedback(feedback_data)
        
    except Exception as e:
        logger.error(f"피드백 저장 편의 함수 실패: {e}")
        return False

def get_user_message(success: bool) -> str:
    """
    피드백 결과에 따른 사용자 메시지 반환
    
    Args:
        success: 저장 성공 여부
        
    Returns:
        str: 사용자 메시지
    """
    return SUCCESS_MESSAGE if success else SAVE_ERROR_MESSAGE

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 피드백 시스템 테스트 ===")
    
    try:
        # FeedbackManager 초기화 테스트
        fm = FeedbackManager()
        print(f"✅ FeedbackManager 초기화: Firestore 사용 가능 = {fm.is_firestore_available}")
        
        # 상태 체크
        health = fm.health_check()
        print(f"✅ 시스템 상태: {health}")
        
        # 편의 함수 테스트
        success = save_user_feedback(
            conversation_id="test_conv_123",
            message_id="test_msg_456",
            user_query="테스트 질문입니다",
            bot_response="테스트 답변입니다",
            feedback_type="positive"
        )
        print(f"✅ 편의 함수 테스트: 성공 = {success}")
        
        # 메시지 테스트
        message = get_user_message(success)
        print(f"✅ 사용자 메시지: {message}")
        
        # 통계 조회 테스트 (캐시 동작 확인)
        if fm.is_firestore_available:
            stats = fm.get_feedback_stats()
            print(f"✅ 통계 조회 테스트: {stats}")
        
        print("\n🎉 모든 테스트 통과!")
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
