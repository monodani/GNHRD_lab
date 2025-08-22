# config/config.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 시스템 설정 v3.1
conversation_manager + 피드백 시스템 중심 아키텍처

설계 원칙:
- Streamlit Secrets 1순위 → .env 2순위 
- thresholds.py와 완전 분리 (상호 import 없음)
- conversation_manager 중심 설정
- 피드백 시스템 연동
- 아름답고 단순한 구조 (복잡한 로직 제거)

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-17
"""

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional
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
# Streamlit Secrets 안전한 로드 함수
# =============================================================================

def get_openai_api_key() -> Optional[str]:
    """
    Streamlit Secrets 우선순위로 OPENAI_API_KEY 로드
    
    우선순위:
    1. Streamlit Secrets
    2. 환경변수
    3. .env 파일
    
    Returns:
        Optional[str]: API 키 또는 None
    """
    # 1. Streamlit Secrets 시도
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and st.secrets:
            api_key = st.secrets.get("OPENAI_API_KEY")
            if api_key:
                return api_key
    except Exception:
        # Streamlit 환경이 아니거나 secrets 접근 실패
        pass
    
    # 2. 환경변수에서 로드
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    
    # 3. API 키를 찾을 수 없음
    return None

def get_firestore_key() -> Optional[str]:
    """
    Firestore 서비스 계정 키 로드 (JSON 문자열)
    
    Returns:
        Optional[str]: Firestore 키 JSON 문자열 또는 None
    """
    # 1. Streamlit Secrets 시도
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and st.secrets:
            firestore_key = st.secrets.get("FIRESTORE_KEY")
            if firestore_key:
                return firestore_key
    except Exception:
        pass
    
    # 2. 환경변수에서 로드
    firestore_key = os.getenv("FIRESTORE_KEY")
    if firestore_key:
        return firestore_key
    
    return None

def get_admin_password() -> str:
    """
    관리자 대시보드 비밀번호 로드
    
    Returns:
        str: 관리자 비밀번호 (기본값: "byeoli2024")
    """
    # 1. Streamlit Secrets 시도
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and st.secrets:
            password = st.secrets.get("ADMIN_PASSWORD")
            if password:
                return password
    except Exception:
        pass
    
    # 2. 환경변수에서 로드
    password = os.getenv("ADMIN_PASSWORD")
    if password:
        return password
    
    # 3. 기본값
    return "byeoli2024"

# =============================================================================
# 애플리케이션 설정 클래스 (간소화 버전)
# =============================================================================

@dataclass
class AppConfig:
    """
    벼리톡 시스템 설정 (conversation_manager + 피드백 시스템 중심)
    
    - Router 방식 완전 제거
    - conversation_manager.py와 연동
    - feedback_manager.py와 연동
    - thresholds.py와 분리
    """
    
    # =============================================================================
    # API 설정
    # =============================================================================
    
    OPENAI_API_KEY: Optional[str] = field(default_factory=get_openai_api_key)
    OPENAI_MODEL: str = "gpt-4o-mini"
    OPENAI_TIMEOUT: float = 10.0
    OPENAI_MAX_RETRIES: int = 3
    
    # =============================================================================
    # 대화 관리 설정 (conversation_manager.py 연동)
    # =============================================================================
    
    # 5턴 슬라이딩 윈도우 설정
    CONVERSATION_WINDOW_SIZE: int = 5
    CONVERSATION_SUMMARY_MAX_LENGTH: int = 200
    CONVERSATION_SUMMARY_TIMEOUT: float = 10.0
    
    # 지시어 해소 설정
    REFERENCE_RESOLUTION_TIMEOUT: float = 3.0
    REFERENCE_RESOLUTION_MAX_TOKENS: int = 100
    
    # Threading 설정 (백그라운드 요약)
    USE_BACKGROUND_SUMMARY: bool = True
    BACKGROUND_SUMMARY_TIMEOUT: float = 10.0
    
    # =============================================================================
    # 피드백 시스템 설정 (feedback_manager.py 연동)
    # =============================================================================
    
    ENABLE_FEEDBACK: bool = True
    FIRESTORE_KEY: Optional[str] = field(default_factory=get_firestore_key)
    FIRESTORE_PROJECT_ID: str = "byeoli-gnhrd-feedback"
    FIRESTORE_COLLECTION_FEEDBACKS: str = "feedbacks"
    FIRESTORE_COLLECTION_ERRORS: str = "error_logs"
    FIRESTORE_TIMEOUT: float = 5.0
    
    # 관리자 대시보드 설정
    ADMIN_PASSWORD: str = field(default_factory=get_admin_password)
    
    # =============================================================================
    # 핸들러 설정 (6개 도메인)
    # =============================================================================
    
    HANDLERS: List[str] = field(default_factory=lambda: [
        "satisfaction",  # 만족도 조사
        "general",       # 일반 정보 (학칙, 규정 등)
        "publish",       # 발행물 (계획서, 평가서)
        "cyber",         # 사이버교육
        "menu",          # 구내식당 메뉴
        "notice"         # 공지사항
    ])
    
    # =============================================================================
    # 디렉터리 경로 설정
    # =============================================================================
    
    ROOT_DIR: Path = field(default=ROOT_DIR)
    VECTORSTORE_DIR: Path = field(default_factory=lambda: ROOT_DIR / "vectorstores")
    LOGS_DIR: Path = field(default_factory=lambda: ROOT_DIR / "logs")
    CACHE_DIR: Path = field(default_factory=lambda: ROOT_DIR / "cache")
    ASSETS_DIR: Path = field(default_factory=lambda: ROOT_DIR / "assets")
    
    # =============================================================================
    # 로깅 설정
    # =============================================================================
    
    LOG_LEVEL: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    LOG_FORMAT: str = field(default_factory=lambda: os.getenv("LOG_FORMAT", "simple"))
    
    # =============================================================================
    # 검색 설정 (기본값)
    # =============================================================================
    
    FAISS_K_DEFAULT: int = field(default_factory=lambda: int(os.getenv("FAISS_K_DEFAULT", "5")))
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
            self.VECTORSTORE_DIR,
            self.LOGS_DIR, 
            self.CACHE_DIR,
            self.ASSETS_DIR
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
            
            # 로그 포맷 설정
            if self.LOG_FORMAT == "json":
                # JSON 형태 (운영환경)
                format_str = '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": "%(message)s"}'
            else:
                # 일반 텍스트 (개발환경)
                format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            
            logging.basicConfig(
                level=log_level,
                format=format_str,
                handlers=[logging.StreamHandler()]
            )
            
            # 서드파티 라이브러리 로그 레벨 조정
            logging.getLogger("openai").setLevel(logging.WARNING)
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("google").setLevel(logging.WARNING)
            
        except Exception as e:
            print(f"로깅 설정 실패: {e}")
    
    def _validate_settings(self):
        """간단한 설정값 검증"""
        # API 키 검증
        if not self.OPENAI_API_KEY:
            logging.warning("⚠️ OPENAI_API_KEY가 설정되지 않았습니다.")
        else:
            logging.info(f"✅ OPENAI_API_KEY 로드 성공: {self.OPENAI_API_KEY[:10]}...")
        
        # Firestore 키 검증 (피드백 시스템용)
        if self.ENABLE_FEEDBACK:
            if not self.FIRESTORE_KEY:
                logging.warning("⚠️ 피드백 시스템이 활성화되었지만 FIRESTORE_KEY가 설정되지 않았습니다.")
            else:
                logging.info("✅ Firestore 키 로드 성공")
        
        # 핸들러 검증
        if not self.HANDLERS:
            logging.warning("⚠️ HANDLERS 리스트가 비어있습니다.")
        else:
            logging.info(f"✅ 핸들러 목록 검증 완료: {len(self.HANDLERS)}개 도메인")
        
        # 타임아웃 검증
        if self.OPENAI_TIMEOUT <= 0:
            logging.warning(f"⚠️ 잘못된 OpenAI 타임아웃 설정: {self.OPENAI_TIMEOUT}")
        
        logging.info(f"✅ 벼리톡 시스템 설정 초기화 완료 (모델: {self.OPENAI_MODEL})")
    
    # =============================================================================
    # 편의 메서드
    # =============================================================================
    
    def get(self, key: str, default=None):
        """속성을 딕셔너리처럼 접근"""
        return getattr(self, key, default)
    
    def is_firestore_enabled(self) -> bool:
        """Firestore 사용 가능 여부 확인"""
        return self.ENABLE_FEEDBACK and self.FIRESTORE_KEY is not None
    
    def get_vectorstore_path(self, domain: str) -> Path:
        """도메인별 벡터스토어 경로 반환"""
        return self.VECTORSTORE_DIR / f"vectorstore_{domain}"

# =============================================================================
# 전역 설정 인스턴스 (싱글톤 패턴)
# =============================================================================

_config: Optional[AppConfig] = None

def get_config() -> AppConfig:
    """
    전역 설정 인스턴스 반환 (싱글톤)
    
    Returns:
        AppConfig: 설정 인스턴스
    """
    global _config
    if _config is None:
        _config = AppConfig()
    return _config

# =============================================================================
# 편의 함수들
# =============================================================================

def get_openai_config() -> dict:
    """
    OpenAI 클라이언트 설정 반환
    
    Returns:
        dict: OpenAI 설정 딕셔너리
    """
    config = get_config()
    return {
        "api_key": config.OPENAI_API_KEY,
        "model": config.OPENAI_MODEL,
        "timeout": config.OPENAI_TIMEOUT,
        "max_retries": config.OPENAI_MAX_RETRIES
    }

def get_conversation_config() -> dict:
    """
    대화 관리자 설정 반환
    
    Returns:
        dict: conversation_manager 설정 딕셔너리
    """
    config = get_config()
    return {
        "window_size": config.CONVERSATION_WINDOW_SIZE,
        "summary_max_length": config.CONVERSATION_SUMMARY_MAX_LENGTH,
        "summary_timeout": config.CONVERSATION_SUMMARY_TIMEOUT,
        "reference_resolution_timeout": config.REFERENCE_RESOLUTION_TIMEOUT,
        "reference_resolution_max_tokens": config.REFERENCE_RESOLUTION_MAX_TOKENS,
        "use_background_summary": config.USE_BACKGROUND_SUMMARY,
        "background_summary_timeout": config.BACKGROUND_SUMMARY_TIMEOUT
    }

def get_feedback_config() -> dict:
    """
    피드백 시스템 설정 반환
    
    Returns:
        dict: feedback_manager 설정 딕셔너리
    """
    config = get_config()
    return {
        "enabled": config.ENABLE_FEEDBACK,
        "firestore_key": config.FIRESTORE_KEY,
        "project_id": config.FIRESTORE_PROJECT_ID,
        "collection_feedbacks": config.FIRESTORE_COLLECTION_FEEDBACKS,
        "collection_errors": config.FIRESTORE_COLLECTION_ERRORS,
        "timeout": config.FIRESTORE_TIMEOUT,
        "admin_password": config.ADMIN_PASSWORD
    }

# =============================================================================
# 디버그 및 검증 (개발용)
# =============================================================================

def print_config_summary():
    """설정 요약 출력 (개발/디버그용)"""
    config = get_config()
    
    print("\n" + "="*60)
    print("🔧 벼리톡@경상남도인재개발원 시스템 설정 v3.1")
    print("="*60)
    
    print(f"📁 프로젝트 루트: {config.ROOT_DIR}")
    print(f"🤖 OpenAI 모델: {config.OPENAI_MODEL}")
    print(f"🔑 API 키 상태: {'✅ 설정됨' if config.OPENAI_API_KEY else '❌ 없음'}")
    print(f"💬 대화 윈도우: {config.CONVERSATION_WINDOW_SIZE}턴")
    print(f"📝 피드백 시스템: {'✅ 활성화' if config.is_firestore_enabled() else '❌ 비활성화'}")
    print(f"🎯 핸들러 개수: {len(config.HANDLERS)}개")
    print(f"📊 핸들러 목록: {', '.join(config.HANDLERS)}")
    
    print(f"\n📂 디렉터리:")
    print(f"  • 벡터스토어: {config.VECTORSTORE_DIR}")
    print(f"  • 로그: {config.LOGS_DIR}")
    print(f"  • 캐시: {config.CACHE_DIR}")
    print(f"  • 에셋: {config.ASSETS_DIR}")
    
    if config.is_firestore_enabled():
        print(f"\n🔥 Firestore 설정:")
        print(f"  • 프로젝트 ID: {config.FIRESTORE_PROJECT_ID}")
        print(f"  • 피드백 컬렉션: {config.FIRESTORE_COLLECTION_FEEDBACKS}")
        print(f"  • 에러 컬렉션: {config.FIRESTORE_COLLECTION_ERRORS}")
    
    print("="*60)

def validate_config() -> bool:
    """
    설정 검증 (테스트용)
    
    Returns:
        bool: 검증 성공 여부
    """
    try:
        config = get_config()
        
        # 필수 설정 확인
        assert config.OPENAI_MODEL == "gpt-4o-mini", f"모델 불일치: {config.OPENAI_MODEL}"
        assert config.CONVERSATION_WINDOW_SIZE == 5, f"윈도우 크기 불일치: {config.CONVERSATION_WINDOW_SIZE}"
        assert len(config.HANDLERS) == 6, f"핸들러 개수 불일치: {len(config.HANDLERS)}"
        
        # 디렉터리 존재 확인
        essential_dirs = [config.VECTORSTORE_DIR, config.LOGS_DIR, config.CACHE_DIR]
        for dir_path in essential_dirs:
            assert dir_path.exists(), f"필수 디렉터리 없음: {dir_path}"
        
        print("✅ 설정 검증 성공!")
        return True
        
    except Exception as e:
        print(f"❌ 설정 검증 실패: {e}")
        return False

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("🧪 config.py 모듈 테스트 시작")
    
    try:
        # 설정 로드 테스트
        config = get_config()
        print("✅ 설정 로드 성공")
        
        # 편의 함수 테스트
        openai_config = get_openai_config()
        conversation_config = get_conversation_config()
        feedback_config = get_feedback_config()
        print("✅ 편의 함수 테스트 성공")
        
        # 검증 테스트
        if validate_config():
            print("✅ 검증 테스트 성공")
        
        # 요약 출력
        print_config_summary()
        
        print("\n🎉 모든 테스트 통과!")
        
    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
