# config/config.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 시스템 설정 v4.0 (리팩토링)
중앙 집중식 핸들러 설정 아키텍처

설계 원칙:
- [신규] Single Source of Truth: 모든 핸들러의 정의와 설정은 config.py에서 관리
- [신규] 아키텍처 분리: FAISS 핸들러와 Pandas Agent 핸들러를 명확히 구분
- Streamlit Secrets 1순위 → .env 2순위 
- conversation_manager 중심 설정
- 아름답고 유지보수하기 쉬운 구조

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-09-08 (Gemini AI 리팩토링 제안 기반)
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv

# 임베딩 모델을 정의합니다.
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSION = 3072

# =============================================================================
# 프로젝트 루트 디렉터리 설정
# =============================================================================

ROOT_DIR = Path(__file__).parent.parent.absolute()

# .env 파일 로드 (존재하는 경우만)
env_path = ROOT_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)

# =============================================================================
# Streamlit Secrets 안전한 로드 함수 (변경 없음)
# =============================================================================

def get_openai_api_key() -> Optional[str]:
    """Streamlit Secrets 우선순위로 OPENAI_API_KEY 로드"""
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and st.secrets:
            api_key = st.secrets.get("OPENAI_API_KEY")
            if api_key:
                return api_key
    except Exception:
        pass
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    return None

def get_firestore_key() -> Optional[str]:
    """Firestore 서비스 계정 키 로드 (JSON 문자열)"""
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and st.secrets:
            firestore_key = st.secrets.get("FIRESTORE_KEY")
            if firestore_key:
                return firestore_key
    except Exception:
        pass
    firestore_key = os.getenv("FIRESTORE_KEY")
    if firestore_key:
        return firestore_key
    return None

def get_admin_password() -> str:
    """관리자 대시보드 비밀번호 로드"""
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and st.secrets:
            password = st.secrets.get("ADMIN_PASSWORD")
            if password:
                return password
    except Exception:
        pass
    password = os.getenv("ADMIN_PASSWORD")
    if password:
        return password
    return "byeoli2024"

# =============================================================================
# 애플리케이션 설정 클래스 (리팩토링)
# =============================================================================

@dataclass
class AppConfig:
    """
    벼리톡 시스템 설정 (중앙 집중식 핸들러 아키텍처)
    """
    
    # =============================================================================
    # API 설정 (변경 없음)
    # =============================================================================
    
    OPENAI_API_KEY: Optional[str] = field(default_factory=get_openai_api_key)
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TIMEOUT: float = 10.0
    OPENAI_MAX_RETRIES: int = 3
    
    # =============================================================================
    # 대화 관리 설정 (변경 없음)
    # =============================================================================
    
    CONVERSATION_WINDOW_SIZE: int = 5
    CONVERSATION_SUMMARY_MAX_LENGTH: int = 200
    CONVERSATION_SUMMARY_TIMEOUT: float = 10.0
    REFERENCE_RESOLUTION_TIMEOUT: float = 3.0
    REFERENCE_RESOLUTION_MAX_TOKENS: int = 100
    USE_BACKGROUND_SUMMARY: bool = True
    BACKGROUND_SUMMARY_TIMEOUT: float = 10.0
    
    # =============================================================================
    # 피드백 시스템 설정 (변경 없음)
    # =============================================================================
    
    ENABLE_FEEDBACK: bool = True
    FIRESTORE_KEY: Optional[str] = field(default_factory=get_firestore_key)
    FIRESTORE_PROJECT_ID: str = "byeoli-gnhrd-feedback"
    FIRESTORE_COLLECTION_FEEDBACKS: str = "feedbacks"
    FIRESTORE_COLLECTION_ERRORS: str = "error_logs"
    FIRESTORE_TIMEOUT: float = 5.0
    ADMIN_PASSWORD: str = field(default_factory=get_admin_password)
    
    # =============================================================================
    # [리팩토링] 핸들러 정의 (Single Source of Truth)
    # =============================================================================
    
    HANDLERS: Dict[str, Any] = field(default_factory=lambda: {
        # Pandas Agent Handlers
        "course_satisfaction": {
            "type": "pandas", 
            "class": "CourseSatisfactionHandler",
            "description": "교육과정 만족도 및 종합 평가 분석 정보"
        },
        "subject_satisfaction": {
            "type": "pandas", 
            "class": "SubjectSatisfactionHandler",
            "description": "교과목별 강의 만족도 및 평가 분석 정보"
        }, 
        "cyber": {
            "type": "pandas", 
            "class": "CyberHandler",
            "description": "사이버교육, 온라인 과정, 이러닝 관련 정보"
        },
        "schedule": {
            "type": "pandas", 
            "class": "ScheduleHandler",
            "description": "교육 일정, 스케줄, 기간 관련 정보"
        },
        # FAISS Vectorstore Handlers
        "general": {
            "type": "faiss", 
            "class": "GeneralHandler",
            "description": "학칙, 규정, 연락처, 일반 정보, 교육과정별 커리큘럼 정보"
        },
        "publish": {
            "type": "faiss", 
            "class": "PublishHandler",
            "description": "발행물, 계획서, 평가서, 공식 자료"
        },
        "notice": {
            "type": "faiss", 
            "class": "NoticeHandler",
            "description": "공지사항, 알림, 최신 소식, 경남인재개발원 소개 및 현황 정보"
        },
        "menu": {
            "type": "faiss", 
            "class": "MenuHandler",
            "description": "구내식당, 메뉴, 식단표 관련 정보"
        }
    })

    # =============================================================================
    # [신규] 핸들러 상세 설정
    # =============================================================================

    HANDLER_SETTINGS: Dict[str, Any] = field(default_factory=lambda: {
        # 핸들러 타입별 공통 설정
        "pandas_agent": {
            "llm_model": "gpt-4o",
            "llm_temperature": 0.1,
            "cache_ttl_seconds": 3600,
            "confidence_score": 0.9  # 직접 답변이므로 높은 신뢰도 부여
        },
        "faiss": {
            "default_k": 3,
            "confidence_function": lambda dist: 1.0 / (1.0 + dist)
        },
        
        # 핸들러별 개별/오버라이드 설정
        "course_satisfaction": {"csv_path": "data/satisfaction/course_satisfaction.csv"},
        "subject_satisfaction": {"csv_path": "data/satisfaction/subject_satisfaction.csv"},
        "cyber": {"csv_path": "data/cyber/cyber.csv"},
        "schedule": {"csv_path": "data/schedule/schedule.csv"},
        "publish": {"k": 5} # 발행물은 더 많이 검색하도록 기본값(3)을 오버라이드
    })

    # =============================================================================
    # 디렉터리 및 로깅 설정 (기존 구조 유지)
    # =============================================================================
    
    ROOT_DIR: Path = field(default=ROOT_DIR)
    VECTORSTORE_DIR: Path = field(default_factory=lambda: ROOT_DIR / "vectorstores")
    DATA_DIR: Path = field(default_factory=lambda: ROOT_DIR / "data")
    LOGS_DIR: Path = field(default_factory=lambda: ROOT_DIR / "logs")
    CACHE_DIR: Path = field(default_factory=lambda: ROOT_DIR / "cache")
    ASSETS_DIR: Path = field(default_factory=lambda: ROOT_DIR / "assets")
    
    LOG_LEVEL: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    LOG_FORMAT: str = field(default_factory=lambda: os.getenv("LOG_FORMAT", "simple"))
    
    CHUNK_SIZE: int = field(default_factory=lambda: int(os.getenv("CHUNK_SIZE", "1000")))
    CHUNK_OVERLAP: int = field(default_factory=lambda: int(os.getenv("CHUNK_OVERLAP", "100")))
    
    # =============================================================================
    # 초기화 및 검증
    # =============================================================================
    
    def __post_init__(self):
        """설정 초기화 및 간단한 검증"""
        self._create_directories()
        self._setup_logging()
        self._validate_settings()
    
    def _create_directories(self):
        """필요한 디렉터리 생성"""
        directories = [
            self.VECTORSTORE_DIR, self.LOGS_DIR, self.CACHE_DIR, 
            self.ASSETS_DIR, self.DATA_DIR
        ]
        for dir_path in directories:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logging.warning(f"디렉터리 생성 실패: {dir_path} - {e}")
    
    def _setup_logging(self):
        """간단한 로깅 설정"""
        try:
            log_level = getattr(logging, self.LOG_LEVEL.upper(), logging.INFO)
            format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            if self.LOG_FORMAT == "json":
                format_str = '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": "%(message)s"}'
            
            logging.basicConfig(
                level=log_level, format=format_str, handlers=[logging.StreamHandler()]
            )
            
            logging.getLogger("openai").setLevel(logging.WARNING)
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("google").setLevel(logging.WARNING)
        except Exception as e:
            print(f"로깅 설정 실패: {e}")
    
    def _validate_settings(self):
        """[리팩토링] 상세 설정값 검증"""
        if not self.OPENAI_API_KEY:
            logging.warning("⚠️ OPENAI_API_KEY가 설정되지 않았습니다.")
        else:
            logging.info(f"✅ OPENAI_API_KEY 로드 성공: {self.OPENAI_API_KEY[:10]}...")
        
        if self.ENABLE_FEEDBACK:
            if not self.FIRESTORE_KEY:
                logging.warning("⚠️ 피드백 시스템이 활성화되었지만 FIRESTORE_KEY가 설정되지 않았습니다.")
            else:
                logging.info("✅ Firestore 키 로드 성공")
        
        # 핸들러 타입별 개수 검증
        if not self.HANDLERS:
            logging.error("❌ HANDLERS 딕셔너리가 비어있습니다.")
        else:
            faiss_count = sum(1 for h in self.HANDLERS.values() if h['type'] == 'faiss')
            pandas_count = sum(1 for h in self.HANDLERS.values() if h['type'] == 'pandas')
            logging.info(f"✅ 핸들러 목록 검증 완료: {len(self.HANDLERS)}개 (FAISS: {faiss_count}, Pandas: {pandas_count})")
        
        if self.OPENAI_TIMEOUT <= 0:
            logging.warning(f"⚠️ 잘못된 OpenAI 타임아웃 설정: {self.OPENAI_TIMEOUT}")
        
        logging.info(f"✅ 벼리톡 시스템 설정 초기화 완료 (모델: {self.OPENAI_MODEL})")

    # =============================================================================
    # 편의 메서드 (변경 없음)
    # =============================================================================
    
    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def is_firestore_enabled(self) -> bool:
        return self.ENABLE_FEEDBACK and self.FIRESTORE_KEY is not None

    def get_vectorstore_path(self, domain: str) -> Path:
        return self.VECTORSTORE_DIR / f"vectorstore_{domain}"

# =============================================================================
# 전역 설정 인스턴스 (싱글톤 패턴)
# =============================================================================

_config: Optional[AppConfig] = None

def get_config() -> AppConfig:
    """전역 설정 인스턴스 반환 (싱글톤)"""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config

# =============================================================================
# 편의 함수들 (변경 없음)
# =============================================================================

def get_openai_config() -> dict:
    config = get_config()
    return {"api_key": config.OPENAI_API_KEY, "model": config.OPENAI_MODEL, "timeout": config.OPENAI_TIMEOUT, "max_retries": config.OPENAI_MAX_RETRIES}

def get_conversation_config() -> dict:
    config = get_config()
    return {"window_size": config.CONVERSATION_WINDOW_SIZE, "summary_max_length": config.CONVERSATION_SUMMARY_MAX_LENGTH, "summary_timeout": config.CONVERSATION_SUMMARY_TIMEOUT, "reference_resolution_timeout": config.REFERENCE_RESOLUTION_TIMEOUT, "reference_resolution_max_tokens": config.REFERENCE_RESOLUTION_MAX_TOKENS, "use_background_summary": config.USE_BACKGROUND_SUMMARY, "background_summary_timeout": config.BACKGROUND_SUMMARY_TIMEOUT}

def get_feedback_config() -> dict:
    config = get_config()
    return {"enabled": config.ENABLE_FEEDBACK, "firestore_key": config.FIRESTORE_KEY, "project_id": config.FIRESTORE_PROJECT_ID, "collection_feedbacks": config.FIRESTORE_COLLECTION_FEEDBACKS, "collection_errors": config.FIRESTORE_COLLECTION_ERRORS, "timeout": config.FIRESTORE_TIMEOUT, "admin_password": config.ADMIN_PASSWORD}

# =============================================================================
# 디버그 및 검증 (개발용)
# =============================================================================

def print_config_summary():
    """[리팩토링] 설정 요약 출력"""
    config = get_config()
    
    print("\n" + "="*60)
    print("🔧 벼리톡@경상남도인재개발원 시스템 설정 v4.0 (리팩토링)")
    print("="*60)
    
    print(f"📁 프로젝트 루트: {config.ROOT_DIR}")
    print(f"🤖 OpenAI 모델: {config.OPENAI_MODEL} (API 키: {'✅' if config.OPENAI_API_KEY else '❌'})")
    print(f"📝 피드백 시스템: {'✅ 활성화' if config.is_firestore_enabled() else '❌ 비활성화'}")
    
    print("\n" + "-"*25 + " 핸들러 아키텍처 " + "-"*24)
    faiss_handlers = [name for name, conf in config.HANDLERS.items() if conf['type'] == 'faiss']
    pandas_handlers = [name for name, conf in config.HANDLERS.items() if conf['type'] == 'pandas']
    print(f"🎯 총 {len(config.HANDLERS)}개 핸들러")
    print(f"  - FAISS 기반 ({len(faiss_handlers)}개): {', '.join(faiss_handlers)}")
    print(f"  - Pandas Agent 기반 ({len(pandas_handlers)}개): {', '.join(pandas_handlers)}")
    
    print("\n" + "-"*27 + " 주요 디렉터리 " + "-"*26)
    print(f"  • 데이터: {config.DATA_DIR}")
    print(f"  • 벡터스토어: {config.VECTORSTORE_DIR}")
    print(f"  • 로그: {config.LOGS_DIR}")
    
    print("="*60)

if __name__ == "__main__":
    print("🧪 config.py 모듈 테스트 시작")
    config = get_config()
    print_config_summary()
    print("\n🎉 config.py 초기화 및 요약 출력 완료!")
