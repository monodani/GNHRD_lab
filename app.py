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
최종 수정: 2025-09-08
"""

import os
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import base64
from pathlib import Path
import streamlit as st

def image_to_base64(image_path: str) -> str:
    """이미지 파일을 Base64 문자열로 변환합니다."""
    try:
        path = Path(image_path)
        if path.exists():
            with open(path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode()
                return f"data:image/png;base64,{encoded_string}"
    except Exception as e:
        # 이미지를 찾지 못할 경우 로깅하고 빈 문자열 반환
        logger.error(f"이미지 인코딩 실패: {image_path} - {e}")
        return ""
        
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
    "default": image_to_base64("assets/Byeoli/advicing_Byeoli.png"),
    "happy": image_to_base64("assets/Byeoli/happy_Byeoli.png"),
    "sorry": image_to_base64("assets/Byeoli/sorry_Byeoli.png"),
    "excited": image_to_base64("assets/Byeoli/excited_Byeoli.png"),
    "typing": image_to_base64("assets/Byeoli/typing_Byeoli.png")
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

# # 로깅 설정
# logging.basicConfig(
#     level=logging.WARNING if IS_PRODUCTION else logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# )
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
        background-color: #f8f9fa; /* 깔끔한 밝은 회색 배경 */
        font-family: 'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    
    /* 메인 컨테이너 */
    .main-container {
        max-width: 900px;
        margin: 0 auto; /* 좌우 여백을 자동으로 주어 중앙 정렬 */
        padding: 1rem;
    }
    
    /* 헤더 카드 */
    .header-card {
        display: flex; /* Flexbox 레이아웃 사용 */
        align-items: center; /* 수직 중앙 정렬 */
        justify-content: center; /* 수평 중앙 정렬 */
        gap: 20px; /* 이미지와 텍스트 사이 간격 */
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(20px);
        border-radius: 24px;
        padding: 2rem;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    .header-byeoli-avatar {
        width: 100px;
        height: 100px;
    }
    
    .header-title {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 0;
        line-height: 1.2;
        text-align: left;
    }
    
    .header-subtitle {
        font-size: 1.0rem;
        color: #6b7280;
        margin: 0.5rem 0 0 0;
        font-weight: 400;
        text-align: left;
    }
    
    .chat-area-card {
        background: white;
        border-radius: 24px;
        box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
        border: 1px solid #e5e7eb;
        padding: 1rem;
        margin-top: 1.5rem;
    }
    
    .chat-container {
        background: transparent;
        backdrop-filter: none;
        box-shadow: none;
        border: none;        
        padding: 1rem;
        max-height: 65vh;
        overflow-y: auto;
        margin-bottom: 0.5rem;
    }
    
    /* ... (메시지 카드, 사용자 메시지 등 다른 스타일은 여기에 그대로 위치) ... */
    .message-card { margin: 1rem 0; animation: slideIn 0.3s ease-out; }
    @keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
    .user-message { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 1.2rem 1.5rem; border-radius: 20px 20px 8px 20px; margin-left: auto; max-width: 75%; box-shadow: 0 4px 16px rgba(102, 126, 234, 0.3); font-weight: 500; line-height: 1.5; position: relative; }
    .assistant-message { background: white; color: #374151; padding: 1.2rem 1.5rem; border-radius: 20px 20px 20px 8px; margin-right: auto; max-width: 75%; box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08); border: 1px solid rgba(229, 231, 235, 0.8); line-height: 1.6; position: relative; }
    .byeoli-avatar { width: 48px; height: 48px; border-radius: 50%; margin-right: 12px; vertical-align: top; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1); border: 2px solid white; }
    /* ... (이하 다른 모든 기존 CSS 스타일은 여기에 그대로 위치) ... */
    
    .input-container {
        background: transparent;
        backdrop-filter: none;
        box-shadow: none;
        border: none;
        padding: 1rem 0 0 0;
    }

    /* --- ▼▼▼ Streamlit 버튼 줄바꿈 방지 ▼▼▼ --- */
    /* Streamlit의 기본 버튼 스타일을 대상으로 지정합니다. */
    .stButton > button {
        white-space: nowrap;
    }


    /* --- ▼▼▼ [통합 및 수정] 반응형 디자인 ▼▼▼ --- */
    /* 모든 모바일 관련 CSS 규칙을 이 하나의 @media 블록 안에 넣습니다. */
    @media (max-width: 768px) {
        /* 헤더: 모바일에서는 세로 배치 유지 */
        .header-card {
            flex-direction: column;
            gap: 12px;
            padding: 1.5rem 1rem;
        }

        .header-byeoli-avatar {
            width: 120px;
            height: 120px;
        }

        /* 1. 타이틀 h1 태그 자체를 가운데 정렬 */
        .header-title {
            text-align: center;
            /* 기존 그라데이션 색상 제거 */
            background: none;
            -webkit-background-clip: unset;
            -webkit-text-fill-color: unset;
            font-size: 1.5rem;
            white-space: nowrap;
        }

        /* 2. 별(★) 기호 스타일: 노란색 적용 */
        .header-star {
            color: #FFC700; /* 세련된 노란색 (골드) */
            vertical-align: middle; /* 텍스트와 세로 중앙 정렬 */
            margin-right: 2px; /* 텍스트와의 간격 살짝 주기 */
        }
        
        /* 3. 타이틀 텍스트 스타일: 전문적인 다크블루 색상 적용 */
        .header-text {
            color: #2c3e50; /* 전문적이고 시인성 좋은 다크블루 */
            vertical-align: middle; /* 별과 세로 중앙 정렬 */
        }

        /* 서브타이틀: 가운데 정렬 및 줄 간격 유지 */
        .header-subtitle {
            text-align: center;
            font-size: 0.9rem;
            line-height: 1.5;
        }

        /* 메시지 말풍선 너비 조정 */
        .user-message, .assistant-message {
            max-width: 90%;
        }

        /* 채팅 컨테이너 높이 조정 (기존 height: 500px 규칙을 덮어씀) */
        .chat-container {
             max-height: 70vh; /* 모바일에서는 높이를 좀 더 확보 */
             padding: 0.5rem;  /* 내부 여백도 살짝 줄임 */
        }

        /* 입력 영역 패딩 조정 */
        .input-container {
            padding: 1rem;
        }
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

    # [추가] 자동 스크롤을 위한 플래그
    if 'scroll_to_bottom' not in st.session_state:
        st.session_state.scroll_to_bottom = False

        # ▼▼▼ [핵심 수정] ▼▼▼
    # 사용자가 입력한 후, 봇이 처리해야 할 입력을 저장하는 상태
    if 'processing_user_input' not in st.session_state:
        st.session_state.processing_user_input = None



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

@st.cache_resource  # ttl 설정은 보통 불필요
def initialize_system():
    """시스템 초기화 (인덱스 로드 등)"""
    try:
        logger.info("🚀 벼리톡 시스템 초기화 시작 (Resource Caching)")
        
        # 인덱스 사전 로드
        preload_result = preload_all_indexes()
        
        if not preload_result.get("success", False):
            # 실패 시에도 결과를 반환하여 상태를 알림
            logger.error(f"인덱스 로드 실패: {preload_result.get('error')}")
            return {
                "success": False,
                "error": preload_result.get("error", "Unknown error"),
            }
        
        # 헬스 체크는 캐싱하지 않는 것이 좋으므로 필요시 별도 호출
        # health_status = index_health_check()
        
        return {
            "success": True,
            "loaded_domains": preload_result.get("loaded_domains", []),
            "performance": preload_result.get("performance", {}),
            # "health_status": health_status # 필요하다면 포함
        }
        
    except Exception as e:
        logger.error(f"시스템 초기화 중 심각한 예외 발생: {e}")
        return {
            "success": False,
            "error": str(e),
        }

# =============================================================================
# UI 렌더링 함수들
# =============================================================================

def render_header():
    """헤더 렌더링 - 최종 디자인 적용 (주석 완전 제거)"""
    header_image_src = BYEOLI_IMAGES["default"]

    st.markdown(f"""
    <div class="header-card">
        <img src="{header_image_src}" class="header-byeoli-avatar">
        <div>
            <h1 class="header-title">
                <span class="header-star">★</span>
                <span class="header-text">벼리톡@경상남도인재개발원</span>
            </h1>
            <p class="header-subtitle">
                경상남도인재개발원 AI 어시스턴트 ✨벼리입니다!
                <br>
                - 궁금한 것이 있으시면 언제든 물어보세요!
            </p>
        </div>
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
        
        # 🔥 [핵심 수정] 업그레이드된 index_health_check()를 사용하여 인덱스 상태를 정확하게 표시
        try:
            health = index_health_check()
            is_healthy = health.get('is_healthy', False)
            loaded = health.get('loaded_count', 0)
            total = health.get('total_count', 0)
            
            if is_healthy:
                st.markdown(f'<span class="status-badge status-success">✅ 인덱스 정상 ({loaded}/{total})</span>', unsafe_allow_html=True)
            else:
                st.markdown(f'<span class="status-badge status-error">❌ 인덱스 오류 ({loaded}/{total})</span>', unsafe_allow_html=True)
                 # 실패한 도메인이 있다면, 디버깅을 위해 사이드바에 표시
                failed_domains = health.get('failed_domains', [])
                if failed_domains:
                    st.error(f"로드 실패: {', '.join(failed_domains)}")
                    
        except Exception as e:
            st.markdown('<span class="status-badge status-error">❌ 인덱스 확인 불가</span>', unsafe_allow_html=True)
            logger.error(f"인덱스 상태 확인 중 오류: {e}")
        
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
               안녕하세요! 경상남도인재개발원 AI 어시스턴트 벼리입니다! 🌟<br>
               경남인재개발원 교육일정, 교육만족도 현황, 시설현황, 구내식당 메뉴, 공지사항 등 궁금한 것이 있으시면 언제든 물어보세요!
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
                   st.markdown('<div style="margin-top: -10px; margin-bottom: 10px;">', unsafe_allow_html=True)
               
                   col1, col2, col3 = st.columns([1, 1, 4])

                   # 🔥 [핵심 수정] key 값에 메시지 순번(i)을 추가하여 고유성 보장
                   unique_key_pos = f"pos_{message_id}_{i}"
                   unique_key_neg = f"neg_{message_id}_{i}"
                   
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



# [추가] 자동 스크롤을 위한 JavaScript 실행 함수
def trigger_autoscroll():
    """채팅 컨테이너를 맨 아래로 스크롤하는 JavaScript 코드를 실행합니다."""
    # st.components.v1.html을 사용하면 iframe 내에서 안전하게 JS 실행 가능
    # setTimeout을 줘서 렌더링이 완료된 후 스크롤이 일어나도록 보장
    js_code = """
    <script>
        setTimeout(function() {
            const chatContainer = parent.document.querySelector('.chat-container');
            if (chatContainer) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        }, 100); // 100ms 딜레이
    </script>
    """
    st.components.v1.html(js_code, height=0)
    


def render_input_section():
    """입력 섹션 렌더링 - label 경고 수정"""
    st.markdown('<div class="input-container">', unsafe_allow_html=True)
    
    with st.form(key="chat_form", clear_on_submit=True):
        col1, col2 = st.columns([5, 1])
        
        with col1:
            # label_visibility 추가하여 경고 해결
            user_input = st.text_input(
                "메시지 입력",  # 빈 문자열 대신 의미있는 label 제공
                placeholder="궁금한 것을 물어보세요! (예 : 오늘 점심 메뉴는?, AI 관련 온라인 강의는 뭐가 있어?)",
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
# 쿼리 처리 - 완전한 대화 맥락 연동 수정
# =============================================================================

def process_user_query(user_input: str):
    """사용자 쿼리 처리 - 대화 맥락 연동 완료 ✅"""
    start_time = time.time()
    
    try:
        # ✅ 1. conversation_manager와 Streamlit 세션 연동 
        conversation_manager = st.session_state.conversation_manager
        
        # ✅ 2. 기존 채팅 기록을 conversation_manager에 동기화
        # 최근 10개 메시지를 쌍으로 묶어서 동기화 (성능 최적화)
        recent_messages = st.session_state.chat_history[-10:]
        for i in range(0, len(recent_messages)-1, 2):
            if (recent_messages[i]["role"] == "user" and 
                i+1 < len(recent_messages) and 
                recent_messages[i+1]["role"] == "assistant"):
                
                # 사용자-AI 쌍을 conversation_manager에 추가
                try:
                    conversation_manager.add_turn(
                        conv_id=st.session_state.conversation_id,
                        user_message=recent_messages[i]["content"],
                        bot_response=recent_messages[i+1]["content"],
                        confidence=recent_messages[i+1].get("confidence", 0.0),
                        domain_used=recent_messages[i+1].get("domain", "general")
                    )
                except Exception as sync_error:
                    logger.warning(f"대화 기록 동기화 일부 실패: {sync_error}")
                    # 동기화 실패해도 계속 진행
        
        # ✅ 3. 쿼리 요청 생성
        request = QueryRequest(
            query=user_input,
            conversation_id=st.session_state.conversation_id
        )
        
        # ✅ 4. CentralOrchestrator를 통한 처리 (대화 맥락이 이제 연동됨!)
        response = process_query(user_input, st.session_state.conversation_id)
        
        # ✅ 5. 응답 처리 (기존과 동일)
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
        

def add_to_chat_history(role: str, content: dict):
    """지정된 역할의 메시지를 채팅 기록에 추가합니다."""
    # 최대 기록 수 체크
    if len(st.session_state.chat_history) >= MAX_CHAT_HISTORY * 2:
        st.session_state.chat_history = st.session_state.chat_history[-MAX_CHAT_HISTORY:]
    
    # 공통 정보 추가
    message = {
        "role": role,
        "timestamp": datetime.now(),
        **content # content 딕셔너리의 모든 키-값 쌍을 추가
    }
    st.session_state.chat_history.append(message)
    
    # 메시지가 추가되었으므로 스크롤 플래그 설정
    st.session_state.scroll_to_bottom = True


    
# =============================================================================
# 메인 애플리케이션 (간단하게 수정된 버전)
# =============================================================================
def main():
    """메인 애플리케이션 로직"""
    
    # --- 상단부 (수정 없음) ---
    load_custom_css()
    initialize_session_state()
    if not st.session_state.system_initialized:
        with st.spinner("시스템 초기화 중..."):
            init_result = initialize_system()
            if not init_result["success"]:
                st.error(f"시스템 초기화 실패: {init_result.get('error', 'Unknown error')}")
                st.stop()
            st.session_state.system_initialized = True
    
    st.markdown('<div class="main-container">', unsafe_allow_html=True)                
    render_header()
    
    # --- 메인 레이아웃 (운영/개발 분기) ---
    if IS_PRODUCTION:
        # [운영 모드]
        st.markdown('<div class="chat-area-card">', unsafe_allow_html=True)
        render_chat_history()

        # "생각 중..." 애니메이션 표시
        if st.session_state.get('processing_user_input'):
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
            st.session_state.scroll_to_bottom = True # 생각 중일 때도 스크롤
        
        # 자동 스크롤 실행
        if st.session_state.get('scroll_to_bottom', False):
            trigger_autoscroll()
            st.session_state.scroll_to_bottom = False

        user_input = render_input_section()
        st.markdown('</div>', unsafe_allow_html=True)
        
    else:
        # [개발 모드]
        render_sidebar()
        render_chat_history()
        if st.session_state.get('scroll_to_bottom', False):
            trigger_autoscroll()
            st.session_state.scroll_to_bottom = False
        user_input = render_input_section()

    # ▼▼▼ [핵심 수정] 사용자 입력과 봇 응답 처리를 if/elif로 분리 ▼▼▼

    # 1단계: 새로운 사용자 입력 접수
    if user_input:
        # 사용자 메시지만 먼저 기록에 추가
        add_to_chat_history(role="user", content={"content": user_input})
        # 다음 실행에서 처리하도록 입력값 저장
        st.session_state.processing_user_input = user_input
        # 화면을 즉시 새로고침하여 사용자 메시지 표시 및 스크롤 실행
        st.rerun()

    # 2단계: 접수된 입력 처리 (봇 응답 생성)
    elif query_to_process := st.session_state.get('processing_user_input'):
        # 처리 플래그를 먼저 비워서 중복 실행 방지
        st.session_state.processing_user_input = None
        
        # 쿼리 처리
        result = process_user_query(query_to_process)
        
        # 봇 응답을 기록에 추가
        if result["success"]:
            response = result["response"]
            bot_content = {
                "content": response.answer, "message_id": result.get("message_id"),
                "confidence": response.confidence, "domain": response.domain,
                "elapsed_ms": int(result["elapsed_time"] * 1000)
            }
            add_to_chat_history(role="assistant", content=bot_content)
        else:
            error_content = {
                "content": "죄송합니다. 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
                "message_id": str(uuid.uuid4()), "confidence": 0.0, "domain": "error",
                "elapsed_ms": int(result["elapsed_time"] * 1000)
            }
            add_to_chat_history(role="assistant", content=error_content)

        # "생각 중..." 애니메이션 제거 및 최종 화면 그리기를 위해 rerun
        # (스트리밍 효과는 rerun 전에 마지막으로 보여줘야 하므로 여기에 위치)
        if result["success"]:
            render_streaming_response(result["response"].answer, result["message_id"])

        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
    
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

# =============================================================================
# 테스트용 함수 (개발 모드에서만)
# =============================================================================

def test_conversation_context():
    """대화 맥락 연동 테스트 함수 (개발 모드에서만)"""
    if IS_PRODUCTION:
        return
    
    try:
        conversation_manager = st.session_state.conversation_manager
        conv_id = st.session_state.conversation_id
        
        # 현재 대화 통계 조회
        stats = conversation_manager.get_conversation_stats(conv_id)
        
        st.write("### 🔍 대화 맥락 테스트")
        st.json(stats)
        
        # 최근 맥락 확인
        recent_context = conversation_manager.get_recent_context_for_reference(conv_id)
        if recent_context:
            st.write("**최근 대화 맥락:**")
            st.text(recent_context[:200] + "..." if len(recent_context) > 200 else recent_context)
        
        return True
        
    except Exception as e:
        st.error(f"대화 맥락 테스트 실패: {e}")
        return False
