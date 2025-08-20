# utils/index_manager.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 인덱스 관리자 v4.1
Architecture.md 기준 최적화 버전

핵심 기능:
- 6개 도메인 벡터스토어 중앙 관리 (FAISS 기반)
- 싱글톤 패턴으로 메모리 효율성 극대화
- 실패한 도메인 제외하고 진행 (Graceful degradation)
- 간단하고 직관적인 API
- 파인튜닝 편의성 극대화

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-21
"""

import logging
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime

from config.config import get_config
from langchain_community.vectorstores import FAISS

# =============================================================================
# 🔧 파인튜닝 설정 구역 - 여기서 모든 값 조정 가능
# =============================================================================

# 임베딩 모델 설정
EMBEDDING_MODEL = "text-embedding-3-large"

# 도메인 설정 (6개 핸들러)
SUPPORTED_DOMAINS = [
    "satisfaction", "cyber", "publish", 
    "general", "notice", "menu"
]

# 벡터스토어 경로 매핑 (satisfaction만 예외)
VECTORSTORE_PATH_MAPPING = {
    "satisfaction": "vectorstore_unified_satisfaction",
    "cyber": "vectorstore_cyber",
    "publish": "vectorstore_publish",
    "general": "vectorstore_general",
    "notice": "vectorstore_notice",
    "menu": "vectorstore_menu"
}

# 파일명 패턴
INDEX_FILE_PATTERN = "{domain}_index"  # {domain}_index.faiss, {domain}_index.pkl

# 에러 처리 임계값
MIN_REQUIRED_DOMAINS = 3  # 최소 3개 도메인 성공해야 서비스 가능
LOAD_TIMEOUT_SECONDS = 30  # 도메인당 최대 로드 시간

# =============================================================================
# 🔧 파인튜닝 설정 구역 끝
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# IndexManager 싱글톤 클래스
# =============================================================================

class IndexManager:
    """
    6개 도메인 벡터스토어 중앙 관리자 (Architecture v4.1)
    
    핵심 API:
    - get_vectorstore(domain): 핸들러들이 사용하는 메인 API
    - preload_all_indexes(): 앱 시작시 모든 인덱스 로드
    - health_check(): 시스템 상태 체크
    """
    
    _instance = None
    _instance_lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super(IndexManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self.config = get_config()
        self.vectorstores: Dict[str, Optional[FAISS]] = {}
        self.load_stats = {
            "loaded_domains": [],
            "failed_domains": [],
            "load_time": 0.0,
            "last_loaded": None
        }
        
        # OpenAI 임베딩 초기화
        self.embeddings = self._init_embeddings()
        
        logger.info(f"✅ IndexManager 싱글톤 초기화 완료: {len(SUPPORTED_DOMAINS)}개 도메인 지원")
        self._initialized = True
    
    def _init_embeddings(self):
        """OpenAI 임베딩 초기화"""
        try:
            import openai
            
            api_key = self.config.OPENAI_API_KEY
            if not api_key:
                logger.error("❌ OPENAI_API_KEY가 설정되지 않았습니다.")
                return None
            
            # OpenAI 클라이언트로 임베딩 생성
            client = openai.OpenAI(api_key=api_key)
            
            # 테스트 임베딩으로 연결 확인
            try:
                test_response = client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input="테스트"
                )
                logger.info(f"✅ OpenAI 임베딩 초기화 성공: {EMBEDDING_MODEL}")
                return client
            except Exception as test_error:
                logger.error(f"❌ OpenAI 임베딩 테스트 실패: {test_error}")
                return None
                
        except ImportError:
            logger.error("❌ openai 라이브러리를 설치해주세요: pip install openai")
            return None
        except Exception as e:
            logger.error(f"❌ OpenAI 임베딩 초기화 실패: {e}")
            return None
    
    def _get_vectorstore_path(self, domain: str) -> Path:
        """도메인별 벡터스토어 경로 반환"""
        vectorstore_dir_name = VECTORSTORE_PATH_MAPPING.get(domain, f"vectorstore_{domain}")
        return Path(self.config.VECTORSTORE_DIR) / vectorstore_dir_name
    
    def _load_single_domain(self, domain: str) -> bool:
        """단일 도메인 벡터스토어 로드"""
        try:
            start_time = time.time()
            
            # 경로 확인
            vectorstore_path = self._get_vectorstore_path(domain)
            faiss_path = vectorstore_path / f"{INDEX_FILE_PATTERN.format(domain=domain)}.faiss"
            pkl_path = vectorstore_path / f"{INDEX_FILE_PATTERN.format(domain=domain)}.pkl"
            
            if not faiss_path.exists() or not pkl_path.exists():
                logger.warning(f"⚠️ {domain} 인덱스 파일이 없습니다: {vectorstore_path}")
                return False
            
            if not self.embeddings:
                logger.warning(f"⚠️ {domain} 임베딩이 없어 로드를 건너뜁니다.")
                return False
            
            # FAISS 로드 (langchain 방식)
            try:
                # OpenAI 임베딩을 langchain 호환 방식으로 래핑
                from langchain_openai import OpenAIEmbeddings
                
                langchain_embeddings = OpenAIEmbeddings(
                    api_key=self.config.OPENAI_API_KEY,
                    model=EMBEDDING_MODEL
                )
                
                vectorstore = FAISS.load_local(
                    str(vectorstore_path),
                    langchain_embeddings,
                    index_name=INDEX_FILE_PATTERN.format(domain=domain),
                    allow_dangerous_deserialization=True
                )
                
                # 인덱스 유효성 검증
                if hasattr(vectorstore, 'index') and hasattr(vectorstore.index, 'ntotal'):
                    doc_count = vectorstore.index.ntotal
                    if doc_count == 0:
                        logger.warning(f"⚠️ {domain} 인덱스에 문서가 없습니다.")
                        return False
                    else:
                        logger.info(f"✅ {domain} FAISS 로드 성공: {doc_count}개 벡터")
                
                self.vectorstores[domain] = vectorstore
                
                elapsed = time.time() - start_time
                logger.info(f"✅ {domain} 로드 완료 ({elapsed:.2f}초)")
                return True
                
            except Exception as faiss_error:
                logger.error(f"❌ {domain} FAISS 로드 실패: {faiss_error}")
                return False
            
        except Exception as e:
            logger.error(f"❌ {domain} 로드 중 예외 발생: {e}")
            return False
    
    def preload_all_indexes(self) -> Dict[str, Any]:
        """
        모든 도메인 인덱스 사전 로드
        
        Returns:
            Dict: 로드 결과 정보
        """
        logger.info(f"🚀 인덱스 사전 로드 시작: {SUPPORTED_DOMAINS}")
        start_time = time.time()
        
        loaded_domains = []
        failed_domains = []
        
        for domain in SUPPORTED_DOMAINS:
            try:
                if self._load_single_domain(domain):
                    loaded_domains.append(domain)
                else:
                    failed_domains.append(domain)
            except Exception as e:
                logger.error(f"❌ {domain} 로드 중 예외: {e}")
                failed_domains.append(domain)
        
        # 결과 저장
        elapsed_time = time.time() - start_time
        self.load_stats = {
            "loaded_domains": loaded_domains,
            "failed_domains": failed_domains,
            "load_time": elapsed_time,
            "last_loaded": datetime.now()
        }
        
        # 서비스 가능 여부 체크
        success_count = len(loaded_domains)
        total_count = len(SUPPORTED_DOMAINS)
        
        if success_count < MIN_REQUIRED_DOMAINS:
            error_msg = f"서비스 불가: {success_count}/{total_count}개 도메인만 로드됨 (최소 {MIN_REQUIRED_DOMAINS}개 필요)"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "loaded_domains": loaded_domains,
                "failed_domains": failed_domains,
                "performance": {"load_time": elapsed_time}
            }
        
        logger.info(f"🎉 인덱스 로드 완료: {success_count}/{total_count}개 성공 ({elapsed_time:.2f}초)")
        return {
            "success": True,
            "loaded_domains": loaded_domains,
            "failed_domains": failed_domains,
            "performance": {
                "load_time": elapsed_time,
                "loaded_count": success_count,
                "total_count": total_count
            }
        }
    
    def get_vectorstore(self, domain: str) -> Optional[FAISS]:
        """
        도메인별 벡터스토어 반환 (핸들러들이 사용하는 메인 API)
        
        Args:
            domain: 도메인명 (satisfaction, cyber, publish, general, notice, menu)
            
        Returns:
            Optional[FAISS]: 벡터스토어 또는 None
        """
        if domain not in SUPPORTED_DOMAINS:
            logger.warning(f"⚠️ 지원하지 않는 도메인: {domain}")
            return None
        
        return self.vectorstores.get(domain)
    
    def health_check(self) -> Dict[str, Any]:
        """
        시스템 상태 체크
        
        Returns:
            Dict: 상태 정보
        """
        loaded_count = len(self.load_stats["loaded_domains"])
        total_count = len(SUPPORTED_DOMAINS)
        
        # 각 도메인별 상세 상태
        domain_status = {}
        for domain in SUPPORTED_DOMAINS:
            domain_status[domain] = {
                "loaded": domain in self.load_stats["loaded_domains"],
                "available": self.vectorstores.get(domain) is not None
            }
        
        return {
            "service_available": loaded_count >= MIN_REQUIRED_DOMAINS,
            "loaded_domains": loaded_count,
            "total_domains": total_count,
            "success_rate": round(loaded_count / total_count * 100, 1),
            "embeddings_available": self.embeddings is not None,
            "last_loaded": self.load_stats["last_loaded"].isoformat() if self.load_stats["last_loaded"] else None,
            "load_time": self.load_stats["load_time"],
            "domain_status": domain_status
        }
    
    def reload_all_domains(self) -> Dict[str, Any]:
        """
        모든 도메인 재로드 (관리자 수동 버튼용)
        
        Returns:
            Dict: 재로드 결과
        """
        logger.info("🔄 수동 인덱스 재로드 시작")
        
        # 기존 벡터스토어 정리
        self.vectorstores.clear()
        
        # 재로드 실행
        return self.preload_all_indexes()

# =============================================================================
# 전역 인스턴스 및 편의 함수
# =============================================================================

_index_manager_instance = None

def get_index_manager() -> IndexManager:
    """
    IndexManager 싱글톤 인스턴스 반환
    
    Returns:
        IndexManager: 인덱스 관리자 인스턴스
    """
    global _index_manager_instance
    if _index_manager_instance is None:
        _index_manager_instance = IndexManager()
    return _index_manager_instance

# app.py 호환성 함수들
def preload_all_indexes() -> Dict[str, Any]:
    """앱 시작시 인덱스 사전 로드"""
    manager = get_index_manager()
    return manager.preload_all_indexes()

def index_health_check() -> Dict[str, Any]:
    """시스템 상태 체크"""
    manager = get_index_manager()
    return manager.health_check()

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("🧪 IndexManager 테스트 시작")
    
    try:
        # 싱글톤 테스트
        manager1 = get_index_manager()
        manager2 = get_index_manager()
        assert manager1 is manager2, "싱글톤 패턴 실패"
        print("✅ 싱글톤 패턴 테스트 통과")
        
        # 프리로드 테스트
        result = preload_all_indexes()
        print(f"📊 프리로드 결과: {result}")
        
        # 상태 체크 테스트
        health = index_health_check()
        print(f"📊 시스템 상태: {health}")
        
        # 개별 도메인 테스트
        for domain in SUPPORTED_DOMAINS:
            vectorstore = manager1.get_vectorstore(domain)
            status = "✅ 로드됨" if vectorstore else "❌ 실패"
            print(f"  {domain}: {status}")
        
        print("🎉 모든 테스트 완료!")
        
    except Exception as e:
        print(f"❌ 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
