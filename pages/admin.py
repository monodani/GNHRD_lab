# pages/admin.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 관리자 대시보드 v4.1
개발 모드 전용 관리자 페이지

핵심 기능:
- 피드백 통계 및 분석
- 인덱스 상태 및 재로드
- 채팅 로그 확인
- 시스템 모니터링
- 비밀번호 보호 (개발 모드에서만)

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-21
"""

import os
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# 프로젝트 모듈
try:
    from utils.feedback_manager import get_feedback_manager
    from utils.index_manager import get_index_manager, index_health_check
    from config.config import get_feedback_config
except ImportError as e:
    st.error(f"❌ 모듈 import 실패: {e}")
    st.stop()

# =============================================================================
# 🔧 파인튜닝 설정 구역
# =============================================================================

# 접근 제어
APP_MODE = os.environ.get('APP_MODE', 'development')
IS_PRODUCTION = APP_MODE == 'production'
ADMIN_PASSWORD = "byeoli2024"  # 기본 비밀번호

# 대시보드 설정
REFRESH_INTERVAL = 30  # 초
MAX_RECENT_LOGS = 100  # 최대 로그 표시 수
CHART_HEIGHT = 400     # 차트 높이

# =============================================================================
# 로깅 설정
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# 접근 제어
# =============================================================================

def check_admin_access():
    """관리자 접근 권한 확인"""
    # 운영 모드에서는 관리자 페이지 비활성화
    if IS_PRODUCTION:
        st.error("🚫 관리자 페이지는 개발 모드에서만 접근 가능합니다.")
        st.stop()
    
    # 세션에 인증 상태 확인
    if 'admin_authenticated' not in st.session_state:
        st.session_state.admin_authenticated = False
    
    # 인증되지 않은 경우 로그인 폼 표시
    if not st.session_state.admin_authenticated:
        show_login_form()
        st.stop()

def show_login_form():
    """관리자 로그인 폼"""
    st.markdown("""
    <div style="max-width: 400px; margin: 100px auto; padding: 2rem; 
                background: white; border-radius: 20px; box-shadow: 0 4px 24px rgba(0,0,0,0.1);">
        <h2 style="text-align: center; color: #667eea;">🔐 관리자 로그인</h2>
        <p style="text-align: center; color: #6b7280;">벼리톡 관리자 대시보드</p>
    </div>
    """, unsafe_allow_html=True)
    
    with st.form("admin_login"):
        password = st.text_input("비밀번호", type="password", placeholder="관리자 비밀번호를 입력하세요")
        submitted = st.form_submit_button("로그인", use_container_width=True)
        
        if submitted:
            if password == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.success("✅ 로그인 성공!")
                st.rerun()
            else:
                st.error("❌ 잘못된 비밀번호입니다.")

# =============================================================================
# 데이터 로드 함수들
# =============================================================================

@st.cache_data(ttl=300)  # 5분 캐시
def load_feedback_stats():
    """피드백 통계 로드"""
    try:
        feedback_manager = get_feedback_manager()
        stats = feedback_manager.get_feedback_stats()
        recent_feedbacks = feedback_manager.get_recent_feedbacks(50)
        
        return {
            "stats": stats,
            "recent_feedbacks": recent_feedbacks,
            "timestamp": datetime.now()
        }
    except Exception as e:
        logger.error(f"피드백 통계 로드 실패: {e}")
        return {
            "stats": {"error": str(e)},
            "recent_feedbacks": [],
            "timestamp": datetime.now()
        }

@st.cache_data(ttl=60)  # 1분 캐시
def load_system_status():
    """시스템 상태 로드"""
    try:
        health = index_health_check()
        
        # 인덱스 매니저 상태
        index_manager = get_index_manager()
        
        return {
            "health": health,
            "index_manager": {
                "available": True,
                "domains": health.get('domain_status', {}),
                "loaded_count": health.get('loaded_domains', 0),
                "total_count": health.get('total_domains', 6)
            },
            "timestamp": datetime.now()
        }
    except Exception as e:
        logger.error(f"시스템 상태 로드 실패: {e}")
        return {
            "health": {"error": str(e)},
            "index_manager": {"available": False, "error": str(e)},
            "timestamp": datetime.now()
        }

def load_chat_logs():
    """채팅 로그 로드 (세션 상태에서)"""
    if 'chat_history' in st.session_state:
        return st.session_state.chat_history[-MAX_RECENT_LOGS:]
    return []

# =============================================================================
# 대시보드 컴포넌트들
# =============================================================================

def render_dashboard_header():
    """대시보드 헤더"""
    col1, col2, col3 = st.columns([2, 4, 2])
    
    with col1:
        if st.button("🔄 새로고침"):
            st.cache_data.clear()
            st.rerun()
    
    with col2:
        st.markdown("""
        <h1 style="text-align: center; color: #667eea; margin: 0;">
            🛠️ 벼리톡 관리자 대시보드
        </h1>
        """, unsafe_allow_html=True)
    
    with col3:
        if st.button("🚪 로그아웃"):
            st.session_state.admin_authenticated = False
            st.rerun()

def render_feedback_dashboard():
    """피드백 대시보드"""
    st.markdown("## 📊 피드백 통계")
    
    feedback_data = load_feedback_stats()
    stats = feedback_data["stats"]
    recent_feedbacks = feedback_data["recent_feedbacks"]
    
    if "error" in stats:
        st.error(f"피드백 데이터 로드 실패: {stats['error']}")
        return
    
    # 전체 통계
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("총 피드백", stats.get('total', 0))
    
    with col2:
        st.metric("긍정 피드백", stats.get('positive', 0))
    
    with col3:
        st.metric("부정 피드백", stats.get('negative', 0))
    
    with col4:
        positive_rate = stats.get('positive_rate', 0)
        st.metric("만족도", f"{positive_rate}%")
    
    # 피드백 차트
    if stats.get('total', 0) > 0:
        col1, col2 = st.columns(2)
        
        with col1:
            # 파이 차트
            fig_pie = go.Figure(data=[go.Pie(
                labels=['긍정', '부정'],
                values=[stats.get('positive', 0), stats.get('negative', 0)],
                hole=0.4,
                marker_colors=['#10b981', '#ef4444']
            )])
            fig_pie.update_layout(
                title="피드백 분포",
                height=CHART_HEIGHT,
                showlegend=True
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        
        with col2:
            # 시간별 트렌드 (최근 피드백 기준)
            if recent_feedbacks:
                df_feedbacks = pd.DataFrame(recent_feedbacks)
                
                if 'timestamp_formatted' in df_feedbacks.columns:
                    df_feedbacks['date'] = pd.to_datetime(df_feedbacks['timestamp_formatted']).dt.date
                    daily_counts = df_feedbacks.groupby(['date', 'feedback_type']).size().unstack(fill_value=0)
                    
                    fig_trend = go.Figure()
                    if 'positive' in daily_counts.columns:
                        fig_trend.add_trace(go.Scatter(
                            x=daily_counts.index,
                            y=daily_counts['positive'],
                            mode='lines+markers',
                            name='긍정',
                            line=dict(color='#10b981')
                        ))
                    if 'negative' in daily_counts.columns:
                        fig_trend.add_trace(go.Scatter(
                            x=daily_counts.index,
                            y=daily_counts['negative'],
                            mode='lines+markers',
                            name='부정',
                            line=dict(color='#ef4444')
                        ))
                    
                    fig_trend.update_layout(
                        title="일별 피드백 트렌드",
                        height=CHART_HEIGHT,
                        xaxis_title="날짜",
                        yaxis_title="피드백 수"
                    )
                    st.plotly_chart(fig_trend, use_container_width=True)
    
    # 최근 피드백 목록
    st.markdown("### 📝 최근 피드백")
    
    if recent_feedbacks:
        feedback_df = pd.DataFrame(recent_feedbacks)
        
        # 표시할 컬럼 선택
        display_columns = ['timestamp_formatted', 'feedback_type', 'user_query', 'feedback_reason']
        available_columns = [col for col in display_columns if col in feedback_df.columns]
        
        if available_columns:
            display_df = feedback_df[available_columns].head(20)
            display_df.columns = ['시간', '타입', '질문', '사유']
            
            # 타입에 따른 색상 적용
            def highlight_feedback(row):
                if row['타입'] == 'positive':
                    return ['background-color: rgba(16, 185, 129, 0.1)'] * len(row)
                elif row['타입'] == 'negative':
                    return ['background-color: rgba(239, 68, 68, 0.1)'] * len(row)
                return [''] * len(row)
            
            st.dataframe(
                display_df.style.apply(highlight_feedback, axis=1),
                use_container_width=True,
                height=300
            )
        else:
            st.info("표시할 피드백 데이터가 없습니다.")
    else:
        st.info("최근 피드백이 없습니다.")
    
    # 피드백 내보내기
    st.markdown("### 📤 데이터 내보내기")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📊 피드백 CSV 다운로드", use_container_width=True):
            try:
                feedback_manager = get_feedback_manager()
                csv_data = feedback_manager.export_to_csv()
                
                st.download_button(
                    "💾 다운로드",
                    data=csv_data,
                    file_name=f"feedback_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"CSV 내보내기 실패: {e}")
    
    with col2:
        if st.button("🗑️ 대기 중인 피드백 삭제", use_container_width=True):
            try:
                feedback_manager = get_feedback_manager()
                pending_count = feedback_manager.get_pending_feedback_count()
                
                if pending_count > 0:
                    feedback_manager.clear_pending_feedbacks()
                    st.success(f"✅ {pending_count}개 대기 피드백 삭제 완료")
                else:
                    st.info("삭제할 대기 피드백이 없습니다.")
            except Exception as e:
                st.error(f"피드백 삭제 실패: {e}")

def render_system_dashboard():
    """시스템 대시보드"""
    st.markdown("## ⚙️ 시스템 상태")
    
    system_data = load_system_status()
    health = system_data["health"]
    index_info = system_data["index_manager"]
    
    if "error" in health:
        st.error(f"시스템 상태 로드 실패: {health['error']}")
        return
    
    # 전체 시스템 상태
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        service_available = health.get('service_available', False)
        status_color = "🟢" if service_available else "🔴"
        st.metric("서비스 상태", f"{status_color} {'정상' if service_available else '오류'}")
    
    with col2:
        loaded = health.get('loaded_domains', 0)
        total = health.get('total_domains', 6)
        st.metric("로드된 도메인", f"{loaded}/{total}")
    
    with col3:
        success_rate = health.get('success_rate', 0)
        st.metric("성공률", f"{success_rate}%")
    
    with col4:
        embeddings_ok = health.get('embeddings_available', False)
        embed_status = "🟢 정상" if embeddings_ok else "🔴 오류"
        st.metric("임베딩", embed_status)
    
    # 도메인별 상태
    st.markdown("### 📋 도메인별 인덱스 상태")
    
    domain_status = health.get('domain_status', {})
    if domain_status:
        domain_df = pd.DataFrame([
            {
                "도메인": domain,
                "로드 상태": "✅ 성공" if status['loaded'] else "❌ 실패",
                "사용 가능": "✅ 가능" if status['available'] else "❌ 불가"
            }
            for domain, status in domain_status.items()
        ])
        
        st.dataframe(domain_df, use_container_width=True, hide_index=True)
    else:
        st.info("도메인 상태 정보가 없습니다.")
    
    # 시스템 제어
    st.markdown("### 🔧 시스템 제어")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 인덱스 재로드", use_container_width=True):
            try:
                with st.spinner("인덱스 재로드 중..."):
                    index_manager = get_index_manager()
                    result = index_manager.reload_all_domains()
                    
                    if result.get("success", False):
                        st.success("✅ 인덱스 재로드 완료!")
                        st.cache_data.clear()  # 캐시 클리어
                        st.rerun()
                    else:
                        st.error(f"❌ 재로드 실패: {result.get('error')}")
            except Exception as e:
                st.error(f"❌ 재로드 중 오류: {e}")
    
    with col2:
        if st.button("🗑️ 캐시 클리어", use_container_width=True):
            st.cache_data.clear()
            st.success("✅ 캐시 클리어 완료!")
            st.rerun()
    
    with col3:
        if st.button("📊 상태 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    
    # 시스템 로그 (간단한 버전)
    st.markdown("### 📜 시스템 정보")
    
    system_info = {
        "마지막 업데이트": system_data["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
        "로드 시간": health.get('load_time', 'N/A'),
        "마지막 로드": health.get('last_loaded', 'N/A'),
        "앱 모드": APP_MODE,
        "Python 버전": f"{os.sys.version_info.major}.{os.sys.version_info.minor}",
    }
    
    for key, value in system_info.items():
        st.write(f"**{key}**: {value}")

def render_chat_logs():
    """채팅 로그 대시보드"""
    st.markdown("## 💬 채팅 로그")
    
    chat_logs = load_chat_logs()
    
    if not chat_logs:
        st.info("현재 세션에 채팅 로그가 없습니다.")
        return
    
    # 통계
    total_messages = len(chat_logs)
    user_messages = len([msg for msg in chat_logs if msg.get('role') == 'user'])
    assistant_messages = len([msg for msg in chat_logs if msg.get('role') == 'assistant'])
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("전체 메시지", total_messages)
    
    with col2:
        st.metric("사용자 메시지", user_messages)
    
    with col3:
        st.metric("벼리 응답", assistant_messages)
    
    with col4:
        avg_confidence = 0
        confidence_msgs = [msg for msg in chat_logs if msg.get('role') == 'assistant' and 'confidence' in msg]
        if confidence_msgs:
            avg_confidence = sum(msg['confidence'] for msg in confidence_msgs) / len(confidence_msgs)
        st.metric("평균 신뢰도", f"{avg_confidence:.2f}")
    
    # 도메인별 통계
    st.markdown("### 🏷️ 도메인별 응답 분포")
    
    domain_counts = {}
    for msg in chat_logs:
        if msg.get('role') == 'assistant' and 'domain' in msg:
            domain = msg['domain']
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
    
    if domain_counts:
        domain_df = pd.DataFrame([
            {"도메인": domain, "응답 수": count, "비율": f"{count/assistant_messages*100:.1f}%"}
            for domain, count in domain_counts.items()
        ])
        st.dataframe(domain_df, use_container_width=True, hide_index=True)
        
        # 도메인 차트
        fig_domain = px.pie(
            values=list(domain_counts.values()),
            names=list(domain_counts.keys()),
            title="도메인별 응답 분포"
        )
        fig_domain.update_layout(height=400)
        st.plotly_chart(fig_domain, use_container_width=True)
    
    # 채팅 로그 상세 보기
    st.markdown("### 📜 채팅 로그 상세")
    
    # 필터링 옵션
    col1, col2, col3 = st.columns(3)
    
    with col1:
        role_filter = st.selectbox("역할 필터", ["전체", "사용자", "벼리"])
    
    with col2:
        domain_filter = st.selectbox("도메인 필터", ["전체"] + list(domain_counts.keys()))
    
    with col3:
        show_count = st.number_input("표시 개수", min_value=10, max_value=100, value=20)
    
    # 필터 적용
    filtered_logs = chat_logs
    
    if role_filter != "전체":
        role_map = {"사용자": "user", "벼리": "assistant"}
        filtered_logs = [msg for msg in filtered_logs if msg.get('role') == role_map[role_filter]]
    
    if domain_filter != "전체":
        filtered_logs = [msg for msg in filtered_logs if msg.get('domain') == domain_filter]
    
    # 로그 표시
    filtered_logs = filtered_logs[-show_count:]  # 최근 N개만
    
    for i, msg in enumerate(reversed(filtered_logs)):
        timestamp = msg.get('timestamp', datetime.now())
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        
        role_icon = "👤" if msg.get('role') == 'user' else "🤖"
        role_name = "사용자" if msg.get('role') == 'user' else "벼리"
        
        with st.expander(f"{role_icon} {role_name} - {timestamp.strftime('%H:%M:%S')}"):
            st.write(f"**내용**: {msg.get('content', '')}")
            
            if msg.get('role') == 'assistant':
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**신뢰도**: {msg.get('confidence', 0):.2f}")
                with col2:
                    st.write(f"**도메인**: {msg.get('domain', 'unknown')}")
                with col3:
                    st.write(f"**응답시간**: {msg.get('elapsed_ms', 0)}ms")
    
    # 로그 내보내기
    st.markdown("### 📤 로그 내보내기")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("💾 JSON 다운로드", use_container_width=True):
            import json
            log_data = {
                "export_time": datetime.now().isoformat(),
                "total_messages": len(chat_logs),
                "chat_logs": chat_logs
            }
            
            st.download_button(
                "📥 다운로드",
                data=json.dumps(log_data, ensure_ascii=False, indent=2),
                file_name=f"chat_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True
            )
    
    with col2:
        if st.button("📊 CSV 다운로드", use_container_width=True):
            if chat_logs:
                # CSV용 데이터 변환
                csv_data = []
                for msg in chat_logs:
                    csv_data.append({
                        "timestamp": msg.get('timestamp', ''),
                        "role": msg.get('role', ''),
                        "content": msg.get('content', ''),
                        "confidence": msg.get('confidence', ''),
                        "domain": msg.get('domain', ''),
                        "elapsed_ms": msg.get('elapsed_ms', '')
                    })
                
                df = pd.DataFrame(csv_data)
                csv_string = df.to_csv(index=False, encoding='utf-8-sig')
                
                st.download_button(
                    "📥 다운로드",
                    data=csv_string,
                    file_name=f"chat_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )

# =============================================================================
# 메인 대시보드
# =============================================================================

def main():
    """메인 대시보드 함수"""
    
    # 접근 권한 확인
    check_admin_access()
    
    # 페이지 설정
    st.set_page_config(
        page_title="벼리톡 관리자 대시보드",
        page_icon="🛠️",
        layout="wide"
    )
    
    # CSS 스타일
    st.markdown("""
    <style>
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
    }
    
    .status-success { color: #10b981; }
    .status-warning { color: #f59e0b; }
    .status-error { color: #ef4444; }
    
    .dashboard-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        text-align: center;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: rgba(102, 126, 234, 0.1);
        border-radius: 10px;
        padding: 0.5rem 1rem;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 헤더
    render_dashboard_header()
    
    # 메인 대시보드 탭
    tab1, tab2, tab3 = st.tabs(["📊 피드백 분석", "⚙️ 시스템 상태", "💬 채팅 로그"])
    
    with tab1:
        render_feedback_dashboard()
    
    with tab2:
        render_system_dashboard()
    
    with tab3:
        render_chat_logs()
    
    # 자동 새로고침 (개발 모드)
    if not IS_PRODUCTION:
        st.markdown("---")
        col1, col2, col3 = st.columns([2, 1, 2])
        
        with col2:
            auto_refresh = st.checkbox("🔄 자동 새로고침 (30초)")
            
            if auto_refresh:
                import time
                time.sleep(REFRESH_INTERVAL)
                st.rerun()
    
    # 푸터
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #6b7280; font-size: 0.9rem;">
        🛠️ 벼리톡 관리자 대시보드 v4.1 | 
        개발 모드 전용 | 
        마지막 업데이트: {timestamp}
    </div>
    """.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")), unsafe_allow_html=True)

# =============================================================================
# 진입점
# =============================================================================

if __name__ == "__main__":
    main()
