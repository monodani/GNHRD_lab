# app.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 메인 애플리케이션 v4.1
Architecture.md 기준 모던 트렌디 UI/UX

핵심 기능:
- CentralOrchestrator 기반 통합 처리
- 실시간 피드백 시스템 (👍👎 버튼)
- 단어별 스트리밍 응답
- 모던 카드 디자인 UI
- 운영/개발 모드 구분
- 별도 관리자 대시보드

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-21
"""

import os
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import streamlit as st

# 프로젝트 모듈
try:
    from handlers.base_handler import process_query
    from utils.conversation_manager import get_conversation_manager
    from utils.feedback_manager import get_feedback_manager, save_user_feedback
    from utils.index_manager import preload_all_indexes, index_health_check
    from config.config import get_config
    from utils.contracts import QueryRequest
except ImportError as e:
    st.error(f"❌ 모듈 import 실패: {e}")
    st.stop()

# =============================================================================
# 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
# =============================================================================

# 앱 모드 설정
APP_MODE = os.environ.get('APP_MODE', 'development')  # development | production
IS_PRODUCTION = APP_MODE == 'production'

# 벼리 이미지 (핵심 5개만)
BYEOLI_IMAGES = {
    "default": "assets/Byeoli/advicing_Byeoli.png",     # 기본/상담
    "happy": "assets/Byeoli/happy_Byeoli.png",          # 긍정 응답
    "sorry": "assets/Byeoli/sorry_Byeoli.png",          # 오류/사과
    "excited": "assets/Byeoli/excited_Byeoli.png",      # 환영/식단
    "typing": "assets/Byeoli/typing_Byeoli.png"         # 처리 중
}

# 스트리밍 설정
STREAMING_WORD_DELAY = 0.05  # 단어당 지연시간 (초)
STREAMING_ENABLED = True     # 스트리밍 활성화 여부

# UI 설정
CHAT_CONTAINER_HEIGHT = 600  # 채팅 컨테이너 높이
MESSAGE_MAX_WIDTH = "75%"    # 메시지 최대 너비

# 성능 설정
MAX_CHAT_HISTORY = 50        # 최대 채팅 기록 보관 수
SESSION_TIMEOUT_HOURS = 24   # 세션 만료 시간

# =============================================================================
# 🔧 파인튜닝 설정 구역 끝
# =============================================================================

# 로깅 설정
logging.basicConfig(
    level=logging.WARNING if IS_PRODUCTION else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Streamlit 페이지 설정
st.set_page_config(
    page_title="벼리톡@경상남도인재개발원",
    page_icon="🌟",
    layout="wide",
    initial_sidebar_state="collapsed" if IS_PRODUCTION else "expanded"
)

# =============================================================================
# 모던 트렌디 CSS 스타일
# =============================================================================

def load_custom_css():
    """모던 트렌디 CSS 로드"""
    st.markdown("""
    <style>
    /* 전역 스타일 초기화 */
    .stApp {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    /* 메인 컨테이너 */
    .main-container {
        max-width: 1200px;
        margin: 0 auto;
        padding: 1rem;
    }
    
    /* 헤더 카드 */
    .header-card {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(20px);
        border-radius: 24px;
        padding: 2rem;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.2);
        text-align: center;
    }
    
    .header-title {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
        line-height: 1.2;
    }
    
    .header-subtitle {
        font-size: 1.1rem;
        color: #6b7280;
        margin: 0.5rem 0 0 0;
        font-weight: 400;
    }
    
    /* 채팅 컨테이너 */
    .chat-container {
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(20px);
        border-radius: 20px;
        padding: 2rem;
        height: 600px;
        overflow-y: auto;
        margin-bottom: 1rem;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.3);
    }
    
    /* 메시지 카드 */
    .message-card {
        margin: 1rem 0;
        animation: slideIn 0.3s ease-out;
    }
    
    @keyframes slideIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* 사용자 메시지 */
    .user-message {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.2rem 1.5rem;
        border-radius: 20px 20px 8px 20px;
        margin-left: auto;
        max-width: 75%;
        box-shadow: 0 4px 16px rgba(102, 126, 234, 0.3);
        font-weight: 500;
        line-height: 1.5;
        position: relative;
    }
    
    /* 벼리 메시지 */
    .assistant-message {
        background: white;
        color: #374151;
        padding: 1.2rem 1.5rem;
        border-radius: 20px 20px 20px 8px;
        margin-right: auto;
        max-width: 75%;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
        border: 1px solid rgba(229, 231, 235, 0.8);
        line-height: 1.6;
        position: relative;
    }
    
    /* 벼리 아바타 */
    .byeoli-avatar {
        width: 48px;
        height: 48px;
        border-radius: 50%;
        margin-right: 12px;
        vertical-align: top;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        border: 2px solid white;
    }
    
    /* 피드백 버튼 */
    .feedback-container {
        display: flex;
        gap: 8px;
        margin-top: 12px;
        align-items: center;
    }
    
    .feedback-btn {
        background: transparent;
        border: 2px solid #e5e7eb;
        border-radius: 24px;
        padding: 6px 12px;
        cursor: pointer;
        transition: all 0.2s ease;
        font-size: 14px;
        display: flex;
        align-items: center;
        gap: 4px;
    }
    
    .feedback-btn:hover {
        border-color: #667eea;
        background: rgba(102, 126, 234, 0.05);
        transform: translateY(-1px);
    }
    
    .feedback-btn.disabled {
        opacity: 0.5;
        cursor: not-allowed;
        background: #f3f4f6;
    }
    
    .feedback-btn.positive {
        border-color: #10b981;
        color: #10b981;
    }
    
    .feedback-btn.negative {
        border-color: #ef4444;
        color: #ef4444;
    }
    
    /* 입력 영역 */
    .input-container {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(20px);
        border-radius: 20px;
        padding: 1.5rem;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.3);
    }
    
    /* 커스텀 버튼 */
    .custom-button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 12px;
        padding: 0.75rem 2rem;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 16px rgba(102, 126, 234, 0.3);
    }
    
    .custom-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 32px rgba(102, 126, 234, 0.4);
    }
    
    /* 사이드바 (개발 모드) */
    .sidebar-card {
        background: rgba(255, 255, 255, 0.9);
        border-radius: 16px;
        padding: 1rem;
        margin: 1rem 0;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
    }
    
    /* 상태 표시기 */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 500;
        margin: 2px;
    }
    
    .status-success { 
        background: rgba(16, 185, 129, 0.1); 
        color: #059669;
        border: 1px solid rgba(16, 185, 129, 0.2);
    }
    
    .status-warning { 
        background: rgba(245, 158, 11, 0.1); 
        color: #d97706;
        border: 1px solid rgba(245, 158, 11, 0.2);
    }
    
    .status-error { 
        background: rgba(239, 68, 68, 0.1); 
        color: #dc2626;
        border: 1px solid rgba(239, 68, 68, 0.2);
    }
    
    /* 타이핑 애니메이션 */
    .typing-cursor {
        animation: blink 1s infinite;
        color: #667eea;
    }
    
    @keyframes blink {
        0%, 50% { opacity: 1; }
        51%, 100% { opacity: 0; }
    }
    
    /* 로딩 스피너 */
    .loading-spinner {
        display: inline-block;
        width: 16px;
        height: 16px;
        border: 2px solid #e5e7eb;
        border-radius: 50%;
        border-top-color: #667eea;
        animation: spin 1s ease-in-out infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    /* 반응형 디자인 */
    @media (max-width: 768px) {
        .header-title { font-size: 2rem; }
        .user-message, .assistant-message { max-width: 90%; }
        .chat-container { height: 500px; padding: 1rem; }
        .input-container { padding: 1rem; }
    }
    
    /* Streamlit 기본 요소 숨기기 */
    .stDeployButton { display: none; }
    #MainMenu { display: none; }
    footer { display: none; }
    header { display: none; }
    </style>
    """, unsafe_allow_html=True)

# =============================================================================
# 벼리 이미지 선택 로직
# =============================================================================

def get_byeoli_image(message_content: str = "", response_type: str = "default") -> str:
    """
    메시지 내용에 따른 벼리 이미지 선택 (간소화)
    
    Args:
        message_content: 메시지 내용
        response_type: 응답 타입
        
    Returns:
        str: 이미지 경로
    """
    try:
        content_lower = message_content.lower()
        
        # 오류/사과 관련
        if any(word in content_lower for word in ['죄송', '미안', '오류', '실패', '문제']):
            return BYEOLI_IMAGES["sorry"]
        
        # 긍정적/성공 관련
        if any(word in content_lower for word in ['완료', '성공', '좋', '훌륭', '감사']):
            return BYEOLI_IMAGES["happy"]
        
        # 식단/환영 관련
        if any(word in content_lower for word in ['식단', '메뉴', '안녕', '반갑']):
            return BYEOLI_IMAGES["excited"]
        
        # 기본값
        return BYEOLI_IMAGES["default"]
        
    except Exception as e:
        logger.warning(f"이미지 선택 오류: {e}")
        return BYEOLI_IMAGES["default"]

# =============================================================================
# 세션 상태 관리
# =============================================================================

def initialize_session_state():
    """세션 상태 초기화"""
    config = get_config()
    
    # 기본 세션 정보
    if 'conversation_id' not in st.session_state:
        st.session_state.conversation_id = str(uuid.uuid4())
    
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    if 'feedback_given' not in st.session_state:
        st.session_state.feedback_given = set()  # message_id 저장
    
    # 시스템 상태
    if 'system_initialized' not in st.session_state:
        st.session_state.system_initialized = False
    
    if 'conversation_manager' not in st.session_state:
        st.session_state.conversation_manager = get_conversation_manager()
    
    if 'feedback_manager' not in st.session_state:
        st.session_state.feedback_manager = get_feedback_manager()
    
    # 성능 통계 (개발 모드에서만)
    if not IS_PRODUCTION and 'performance_stats' not in st.session_state:
        st.session_state.performance_stats = {
            "total_queries": 0,
            "avg_response_time": 0.0,
            "success_rate": 100.0,
            "last_query_time": None
        }

    if 'pending_improvement_feedback' not in st.session_state:
        st.session_state.pending_improvement_feedback = {}  # {message_id: input_text}

def reset_session():
    """세션 초기화 (새 대화 시작)"""
    # 대화 관련 상태만 초기화
    st.session_state.conversation_id = str(uuid.uuid4())
    st.session_state.chat_history = []
    st.session_state.feedback_given = set()
    
    logger.info(f"새 대화 세션 시작: {st.session_state.conversation_id}")

# =============================================================================
# 시스템 초기화
# =============================================================================

@st.cache_data(ttl=3600)  # 1시간 캐시
def initialize_system():
    """시스템 초기화 (인덱스 로드 등)"""
    try:
        logger.info("🚀 벼리톡 시스템 초기화 시작")
        
        # 인덱스 사전 로드
        preload_result = preload_all_indexes()
        
        if not preload_result.get("success", False):
            logger.warning(f"인덱스 로드 실패: {preload_result.get('error')}")
            return {
                "success": False,
                "error": preload_result.get("error", "Unknown error"),
                "mode": "limited"
            }
        
        # 헬스 체크
        health_status = index_health_check()
        
        return {
            "success": True,
            "mode": "full",
            "health_status": health_status,
            "loaded_domains": preload_result.get("loaded_domains", []),
            "performance": preload_result.get("performance", {})
        }
        
    except Exception as e:
        logger.error(f"시스템 초기화 실패: {e}")
        return {
            "success": False,
            "error": str(e),
            "mode": "error"
        }

# =============================================================================
# UI 렌더링 함수들
# =============================================================================

def render_header():
    """헤더 렌더링"""
    col1, col2, col3 = st.columns([1, 6, 1])
    
    with col1:
        if Path(BYEOLI_IMAGES["default"]).exists():
            st.image(BYEOLI_IMAGES["default"], width=80)
    
    with col2:
        st.markdown("""
        <div class="header-card">
            <h1 class="header-title">🌟 벼리톡@경상남도인재개발원</h1>
            <p class="header-subtitle">경상남도인재개발원 AI 어시스턴트 - 궁금한 것이 있으시면 언제든 물어보세요!</p>
        </div>
        """, unsafe_allow_html=True)

def render_sidebar():
    """사이드바 렌더링 (개발 모드에서만)"""
    if IS_PRODUCTION:
        return
    
    with st.sidebar:
        st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
        
        # 시스템 상태
        st.markdown("### 🔧 시스템 상태")
        
        # API 키 상태
        config = get_config()
        if config.OPENAI_API_KEY:
            st.markdown('<span class="status-badge status-success">✅ API 연결됨</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-badge status-error">❌ API 키 없음</span>', unsafe_allow_html=True)
        
        # 인덱스 상태
        try:
            health = index_health_check()
            loaded = health.get('loaded_domains', 0)
            total = health.get('total_domains', 6)
            
            if loaded >= 3:
                st.markdown(f'<span class="status-badge status-success">✅ 인덱스 {loaded}/{total}</span>', unsafe_allow_html=True)
            else:
                st.markdown(f'<span class="status-badge status-warning">⚠️ 인덱스 {loaded}/{total}</span>', unsafe_allow_html=True)
        except:
            st.markdown('<span class="status-badge status-error">❌ 인덱스 오류</span>', unsafe_allow_html=True)
        
        st.markdown("---")
        
        # 성능 통계
        if 'performance_stats' in st.session_state:
            stats = st.session_state.performance_stats
            st.markdown("### 📊 성능 지표")
            st.metric("총 질문", stats["total_queries"])
            st.metric("평균 응답시간", f"{stats['avg_response_time']:.2f}초")
            st.metric("성공률", f"{stats['success_rate']:.1f}%")
        
        st.markdown("---")
        
        # 대화 정보
        st.markdown("### 💬 대화 정보")
        st.write(f"**세션**: `{st.session_state.conversation_id[:8]}...`")
        st.write(f"**대화 수**: {len(st.session_state.chat_history) // 2}회")
        
        # 컨트롤 버튼
        if st.button("🔄 새 대화 시작", use_container_width=True):
            reset_session()
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)

def render_chat_history():
   """채팅 기록 렌더링 - Streamlit 네이티브 버튼 사용"""
   st.markdown('<div class="chat-container">', unsafe_allow_html=True)
   
   if not st.session_state.chat_history:
       # 환영 메시지
       welcome_image = get_byeoli_image("안녕하세요! 반가워요!")
       
       st.markdown(f"""
       <div class="message-card">
           <div class="assistant-message">
               <img src="{welcome_image}" class="byeoli-avatar" onerror="this.style.display='none'">
               <strong>벼리</strong><br>
               안녕하세요! 경상남도인재개발원 AI 어시스턴트 벼리입니다! 🌟<br><br>
               교육과정, 만족도 조사, 구내식당 메뉴, 공지사항 등 궁금한 것이 있으시면 언제든 물어보세요!
           </div>
       </div>
       """, unsafe_allow_html=True)
   else:
       # 채팅 기록 표시
       for i, msg in enumerate(st.session_state.chat_history):
           if msg["role"] == "user":
               st.markdown(f"""
               <div class="message-card">
                   <div class="user-message">
                       <strong>사용자</strong><br>
                       {msg["content"]}
                   </div>
               </div>
               """, unsafe_allow_html=True)
           else:
               # 벼리 메시지
               byeoli_image = get_byeoli_image(msg["content"])
               message_id = msg.get("message_id", f"msg_{i}")
               
               # 메시지 본문 표시
               st.markdown(f"""
               <div class="message-card">
                   <div class="assistant-message">
                       <img src="{byeoli_image}" class="byeoli-avatar" onerror="this.style.display='none'">
                       <strong>벼리</strong><br>
                       {msg["content"]}
                   </div>
               </div>
               """, unsafe_allow_html=True)
               
               # 피드백 버튼 (Streamlit 네이티브 버튼 사용)
               if message_id not in st.session_state.feedback_given:
                   col1, col2, col3 = st.columns([1, 1, 4])
                   
                   with col1:
                       if st.button("👍 도움됨", key=f"pos_{message_id}", use_container_width=True):
                           # 피드백 처리
                           user_query = ""
                           bot_response = msg["content"]
                           
                           # 이전 사용자 메시지 찾기
                           if i > 0 and st.session_state.chat_history[i-1]["role"] == "user":
                               user_query = st.session_state.chat_history[i-1]["content"]
                           
                           success = save_user_feedback(
                               conversation_id=st.session_state.conversation_id,
                               message_id=message_id,
                               user_query=user_query,
                               bot_response=bot_response,
                               feedback_type="positive"
                           )
                           
                           if success:
                               st.session_state.feedback_given.add(message_id)
                               st.success("피드백 감사합니다! 🙏")
                               st.rerun()
                           else:
                               st.warning("피드백 저장에 실패했습니다.")
                   
                   with col2:
                       if st.button("👎 개선필요", key=f"neg_{message_id}", use_container_width=True):
                           # 개선사항 입력 모드 활성화 (바로 저장하지 않음)
                           st.session_state.pending_improvement_feedback[message_id] = True
                           st.rerun()
               
                   # 개선사항 입력창 추가 (피드백 버튼 바로 아래)
                   if st.session_state.pending_improvement_feedback.get(message_id, False):
                       with st.form(key=f"improvement_{message_id}"):
                           st.write("개선해야 될 사항을 입력해주세요:")
                           improvement_text = st.text_area("", placeholder="개선사항을 입력하세요 (선택사항)", key=f"textarea_{message_id}")
                           
                           col_submit, col_cancel = st.columns(2)
                           with col_submit:
                               if st.form_submit_button("제출", use_container_width=True):
                                   # 이전 사용자 메시지 찾기
                                   user_query = ""
                                   if i > 0 and st.session_state.chat_history[i-1]["role"] == "user":
                                       user_query = st.session_state.chat_history[i-1]["content"]
                                   
                                   success = save_user_feedback(
                                       conversation_id=st.session_state.conversation_id,
                                       message_id=message_id,
                                       user_query=user_query,
                                       bot_response=msg["content"],
                                       feedback_type="negative",
                                       feedback_reason=improvement_text  # 개선사항 추가
                                   )
                                   
                                   if success:
                                       st.session_state.feedback_given.add(message_id)
                                       st.session_state.pending_improvement_feedback.pop(message_id, None)
                                       st.success("피드백 감사합니다! 🙏")
                                       st.rerun()
                                   else:
                                       st.warning("피드백 저장에 실패했습니다.")
                           
                           with col_cancel:
                               if st.form_submit_button("취소", use_container_width=True):
                                   st.session_state.pending_improvement_feedback.pop(message_id, None)
                                   st.rerun()
               
               else:
                   # 피드백 완료 표시
                   st.markdown("""
                   <div style="padding: 8px; background: #f3f4f6; border-radius: 8px; 
                               margin-top: 8px; text-align: center; font-size: 14px; color: #6b7280;">
                       ✅ 피드백 완료
                   </div>
                   """, unsafe_allow_html=True)
               
               # 성능 정보 (개발 모드에서만)
               if not IS_PRODUCTION and msg.get("elapsed_ms"):
                   st.markdown(f"""
                   <div style="font-size: 11px; color: #9ca3af; margin-top: 8px;">
                       ⏱️ {msg['elapsed_ms']}ms | 🎯 {msg.get('confidence', 0):.2f} | 🔧 {msg.get('domain', 'unknown')}
                   </div>
                   """, unsafe_allow_html=True)
   
   st.markdown('</div>', unsafe_allow_html=True)


def render_input_section():
    """입력 섹션 렌더링 - label 경고 수정"""
    st.markdown('<div class="input-container">', unsafe_allow_html=True)
    
    with st.form(key="chat_form", clear_on_submit=True):
        col1, col2 = st.columns([5, 1])
        
        with col1:
            # label_visibility 추가하여 경고 해결
            user_input = st.text_input(
                "메시지 입력",  # 빈 문자열 대신 의미있는 label 제공
                placeholder="궁금한 것을 물어보세요... (예: 오늘 점심 메뉴는?, 2024년 교육 만족도는?)",
                label_visibility="collapsed"  # label을 숨김
            )
        
        with col2:
            submitted = st.form_submit_button("전송", use_container_width=True)
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    return user_input if submitted and user_input.strip() else None

def render_streaming_response(message_content: str, message_id: str):
    """단어별 스트리밍 응답 렌더링"""
    if not STREAMING_ENABLED:
        return
    
    byeoli_image = get_byeoli_image(message_content)
    placeholder = st.empty()
    
    words = message_content.split()
    displayed_text = ""
    
    for i, word in enumerate(words):
        displayed_text += word + " "
        
        with placeholder.container():
            st.markdown(f"""
            <div class="message-card">
                <div class="assistant-message">
                    <img src="{byeoli_image}" class="byeoli-avatar" onerror="this.style.display='none'">
                    <strong>벼리</strong><br>
                    {displayed_text}<span class="typing-cursor">▊</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        time.sleep(STREAMING_WORD_DELAY)
    
    # 최종 메시지 (타이핑 커서 제거)
    placeholder.empty()

def render_feedback_buttons(message_id: str, user_query: str, bot_response: str):
    """우아한 피드백 버튼 렌더링 - 기존 HTML 대체"""
    if message_id in st.session_state.feedback_given:
        st.markdown('<span class="feedback-btn disabled">피드백 완료</span>', unsafe_allow_html=True)
        return
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("👍 도움됨", key=f"pos_{message_id}", use_container_width=True):
            handle_feedback(message_id, "positive", user_query, bot_response)
            st.success("피드백 감사합니다! 🙏")
            st.rerun()
    
    with col2:
        if st.button("👎 개선필요", key=f"neg_{message_id}", use_container_width=True):
            st.session_state.pending_improvement_feedback[message_id] = True
            st.rerun()
    
    # 개선사항 입력창 (👎 클릭 시에만 나타남)
    if st.session_state.pending_improvement_feedback.get(message_id, False):
        with st.form(key=f"improvement_{message_id}"):
            improvement_text = st.text_area("개선해야 될 사항을 입력해주세요", placeholder="개선사항을 입력하세요 (선택사항)")
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                if st.form_submit_button("제출", use_container_width=True):
                    handle_feedback(message_id, "negative", user_query, bot_response, improvement_text)
                    st.session_state.pending_improvement_feedback.pop(message_id, None)
                    st.success("피드백 감사합니다! 🙏")
                    st.rerun()
            
            with col_cancel:
                if st.form_submit_button("취소", use_container_width=True):
                    st.session_state.pending_improvement_feedback.pop(message_id, None)
                    st.rerun()

# =============================================================================
# 피드백 시스템
# =============================================================================

def handle_feedback(message_id: str, feedback_type: str, user_query: str = "", bot_response: str = "", feedback_reason: str = ""):
    """피드백 처리 - feedback_reason 파라미터 추가"""
    try:
        # 피드백 저장
        success = save_user_feedback(
            conversation_id=st.session_state.conversation_id,
            message_id=message_id,
            user_query=user_query,
            bot_response=bot_response,
            feedback_type=feedback_type,
            feedback_reason=feedback_reason  # 이 파라미터 추가
        )
        
        if success:
            st.session_state.feedback_given.add(message_id)
            return True
        else:
            return False
            
    except Exception as e:
        logger.error(f"피드백 처리 오류: {e}")
        return False

# =============================================================================
# 쿼리 처리
# =============================================================================

def process_user_query(user_input: str):
    """사용자 쿼리 처리"""
    start_time = time.time()
    
    try:
        # 쿼리 요청 생성
        request = QueryRequest(
            query=user_input,
            conversation_id=st.session_state.conversation_id
        )
        
        # CentralOrchestrator를 통한 처리
        response = process_query(user_input, st.session_state.conversation_id)
        
        # 응답 처리
        elapsed_time = time.time() - start_time
        message_id = response.message_id
        
        # 성능 통계 업데이트 (개발 모드에서만)
        if not IS_PRODUCTION:
            update_performance_stats(elapsed_time, response.success)
        
        return {
            "success": response.success,
            "response": response,
            "message_id": message_id,
            "elapsed_time": elapsed_time
        }
        
    except Exception as e:
        logger.error(f"쿼리 처리 오류: {e}")
        elapsed_time = time.time() - start_time
        
        # 성능 통계 업데이트 (실패)
        if not IS_PRODUCTION:
            update_performance_stats(elapsed_time, False)
        
        return {
            "success": False,
            "error": str(e),
            "elapsed_time": elapsed_time
        }

def update_performance_stats(elapsed_time: float, success: bool):
    """성능 통계 업데이트 (개발 모드에서만)"""
    if IS_PRODUCTION:
        return
    
    stats = st.session_state.performance_stats
    stats["total_queries"] += 1
    stats["last_query_time"] = datetime.now()
    
    # 이동 평균으로 응답시간 계산
    if stats["avg_response_time"] == 0:
        stats["avg_response_time"] = elapsed_time
    else:
        stats["avg_response_time"] = (stats["avg_response_time"] * 0.8 + elapsed_time * 0.2)
    
    # 성공률 계산
    if success:
        stats["success_rate"] = min(stats["success_rate"] + 0.5, 100)
    else:
        stats["success_rate"] = max(stats["success_rate"] - 2, 0)

def add_to_chat_history(user_input: str, result: Dict):
    """채팅 기록에 추가"""
    # 최대 기록 수 체크
    if len(st.session_state.chat_history) >= MAX_CHAT_HISTORY * 2:
        st.session_state.chat_history = st.session_state.chat_history[-MAX_CHAT_HISTORY:]
    
    # 사용자 메시지 추가
    st.session_state.chat_history.append({
        "role": "user",
        "content": user_input,
        "timestamp": datetime.now()
    })
    
    # 어시스턴트 응답 추가
    if result["success"]:
        response = result["response"]
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response.answer,
            "message_id": result.get("message_id", str(uuid.uuid4())),
            "confidence": response.confidence,
            "domain": response.domain,
            "elapsed_ms": int(result["elapsed_time"] * 1000),
            "timestamp": datetime.now()
        })
    else:
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
            "message_id": str(uuid.uuid4()),
            "confidence": 0.0,
            "domain": "error",
            "elapsed_ms": int(result["elapsed_time"] * 1000),
            "timestamp": datetime.now()
        })

# =============================================================================
# 메인 애플리케이션
# =============================================================================

# 메인 함수의 JavaScript 주입 부분도 제거
def main():
    """메인 애플리케이션 로직"""
    
    # CSS 로드
    load_custom_css()
    
    # 세션 상태 초기화
    initialize_session_state()
    
    # 시스템 초기화 (첫 실행시에만)
    if not st.session_state.system_initialized:
        with st.spinner("시스템 초기화 중..."):
            init_result = initialize_system()
            
            if not init_result["success"]:
                if IS_PRODUCTION:
                    st.error("시스템 초기화에 실패했습니다. 관리자에게 문의해주세요.")
                else:
                    st.error(f"시스템 초기화 실패: {init_result.get('error')}")
                    st.code(init_result.get('error', ''))
                st.stop()
            
            st.session_state.system_initialized = True
            if not IS_PRODUCTION:
                st.success("✅ 시스템 초기화 완료!")
    
    # UI 렌더링
    render_header()
    
    # 메인 레이아웃
    if IS_PRODUCTION:
        # 운영 모드: 심플한 단일 컬럼
        render_chat_history()
        
        # 사용자 입력 처리
        user_input = render_input_section()
        
        if user_input:
            # 처리 중 표시
            with st.spinner(""):
                # 타이핑 이미지로 처리 중 표시
                typing_placeholder = st.empty()
                typing_placeholder.markdown(f"""
                <div class="message-card">
                    <div class="assistant-message">
                        <img src="{BYEOLI_IMAGES['typing']}" class="byeoli-avatar">
                        <strong>벼리</strong><br>
                        <span class="loading-spinner"></span> 생각하고 있어요...
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 쿼리 처리
                result = process_user_query(user_input)
                
                # 타이핑 표시 제거
                typing_placeholder.empty()
                
                # 채팅 기록에 추가
                add_to_chat_history(user_input, result)
                
                # 성공시 스트리밍 효과
                if result["success"]:
                    response = result["response"]
                    render_streaming_response(response.answer, result["message_id"])
                
                # 페이지 새로고침
                st.rerun()
    
    else:
        # 개발 모드: 사이드바 포함 레이아웃
        render_sidebar()
        
        col1, col2 = st.columns([4, 1])
        
        with col1:
            render_chat_history()
            
            # 사용자 입력 처리
            user_input = render_input_section()
            
            if user_input:
                # 처리 중 표시
                with st.spinner("쿼리 처리 중..."):
                    result = process_user_query(user_input)
                
                # 채팅 기록에 추가
                add_to_chat_history(user_input, result)
                
                # 성공시 스트리밍 효과
                if result["success"]:
                    response = result["response"]
                    render_streaming_response(response.answer, result["message_id"])
                    st.success("✅ 응답 완료!")
                else:
                    st.error("❌ 처리 중 오류가 발생했습니다.")
                    st.code(result.get("error", ""))
                
                # 페이지 새로고침
                st.rerun()
        
        with col2:
            # 개발 모드 추가 정보
            st.markdown("### 🛠️ 개발 도구")
            
            if st.button("💾 채팅 기록 저장", use_container_width=True):
                chat_data = {
                    "session_id": st.session_state.conversation_id,
                    "timestamp": datetime.now().isoformat(),
                    "chat_history": st.session_state.chat_history
                }
                st.download_button(
                    "📥 다운로드",
                    data=str(chat_data),
                    file_name=f"chat_log_{st.session_state.conversation_id[:8]}.json",
                    mime="application/json"
                )
            
            if st.button("🗑️ 채팅 기록 삭제", use_container_width=True):
                st.session_state.chat_history = []
                st.rerun()

# =============================================================================
# 피드백 버튼 JavaScript (클라이언트 사이드)
# =============================================================================

def inject_feedback_script():
    """피드백 버튼 JavaScript 주입"""
    st.markdown("""
    <script>
    function giveFeedback(messageId, feedbackType) {
        // Streamlit의 피드백 처리 함수 호출
        // 실제 구현에서는 Streamlit callback 사용
        alert(`피드백: ${feedbackType} for message ${messageId}`);
        
        // 버튼 비활성화
        const buttons = document.querySelectorAll(`[onclick*="${messageId}"]`);
        buttons.forEach(btn => {
            btn.classList.add('disabled');
            btn.onclick = null;
        });
        
        // 피드백 완료 메시지 표시
        const container = buttons[0].parentElement;
        container.innerHTML = '<span class="feedback-btn disabled">피드백 완료</span>';
    }
    </script>
    """, unsafe_allow_html=True)

# =============================================================================
# 애플리케이션 진입점
# =============================================================================

if __name__ == "__main__":
    try:
        # JavaScript 주입 제거 - 더 이상 필요없음
        # inject_feedback_script()  # 제거
        
        # 메인 앱 실행
        main()
        
    except Exception as e:
        logger.error(f"앱 실행 오류: {e}")
        st.error("애플리케이션 실행 중 오류가 발생했습니다.")
        if not IS_PRODUCTION:
            st.exception(e)
