# utils/index_manager.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 인덱스 관리자 v5.0 (리팩토링)
Config-Driven 기반 FAISS 벡터스토어 관리 시스템

핵심 기능:
- [개선] config.py를 참조하여 FAISS 타입의 도메인을 동적으로 관리
- 싱글톤 패턴으로 메모리 효율성 극대화
- 실패한 도메인 제외하고 진행 (Graceful degradation)
- 간단하고 직관적인 API

작성자: 이다니엘 from 경상남도인재개발원 (Gemini AI 리팩토링)
최종 수정: 2025-09-08
"""
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Any, List
from datetime import datetime

# --- 프로젝트 모듈 ---
from config.config import get_config
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings # 변경

logger = logging.getLogger(__name__)

# =============================================================================
# 🔧 파인튜닝 설정 구역 -> 모두 config.py로 이전되어 제거됨
# =============================================================================

class IndexManager:
    """
    [리팩토링] 설정 파일(config.py) 기반으로 동작하는 인덱스 관리자.
    FAISS 타입의 핸들러만 자동으로 인식하여 관리합니다.
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
        
        # 1. 중앙 설정 로드
        self.config = get_config()
        
        # 2. 🔥 [핵심 변경] config 파일에서 'faiss' 타입의 핸들러만 필터링하여 관리 대상으로 삼음
        self.faiss_domains: List[str] = [
            name for name, conf in self.config.HANDLERS.items() if conf.get('type') == 'faiss'
        ]
        
        # 3. 내부 변수 초기화
        self.vectorstores: Dict[str, Optional[FAISS]] = {}
        self.load_stats = {"loaded_domains": [], "failed_domains": [], "load_time": 0.0, "last_loaded": None}
        
        # 4. 임베딩 및 벡터스토어 로더 초기화
        self.embeddings = self._init_embeddings()
        
        logger.info(f"✅ IndexManager v5.0 초기화 완료 ({len(self.faiss_domains)}개 FAISS 도메인 지원)")
        self._initialized = True
    
    def _init_embeddings(self) -> Optional[OpenAIEmbeddings]:
        """Langchain 호환 OpenAI 임베딩 객체를 초기화"""
        try:
            if not self.config.OPENAI_API_KEY:
                logger.error("❌ OPENAI_API_KEY가 설정되지 않았습니다.")
                return None
            
            # Langchain 호환 임베딩 객체 생성
            langchain_embeddings = OpenAIEmbeddings(
                api_key=self.config.OPENAI_API_KEY,
                model=EMBEDDING_MODEL # 전역 변수 사용
            )
            logger.info(f"✅ Langchain OpenAI 임베딩 초기화 성공: {EMBEDDING_MODEL}")
            return langchain_embeddings
        except Exception as e:
            logger.error(f"❌ OpenAI 임베딩 초기화 실패: {e}")
            return None
    
    def _load_single_domain(self, domain: str) -> bool:
        """단일 도메인 FAISS 벡터스토어 로드"""
        if not self.embeddings:
            logger.warning(f"⚠️ 임베딩 객체가 없어 {domain} 로드를 건너뜁니다.")
            return False
        
        try:
            # config.py의 경로 생성 함수 사용
            vectorstore_path = self.config.get_vectorstore_path(domain)
            
            # 파일 존재 여부 확인 (config.py 설정 참조)
            index_name = f"{domain}_index" # 파일명 패턴 단순화
            if not (vectorstore_path / f"{index_name}.faiss").exists():
                 logger.warning(f"⚠️ {domain} 인덱스 파일이 없습니다: {vectorstore_path}")
                 return False

            # FAISS 로드 (langchain 방식)
            vectorstore = FAISS.load_local(
                str(vectorstore_path),
                self.embeddings,
                index_name=index_name,
                allow_dangerous_deserialization=True
            )
            
            doc_count = vectorstore.index.ntotal
            logger.info(f"✅ {domain} FAISS 로드 성공: {doc_count}개 벡터")
            self.vectorstores[domain] = vectorstore
            return True
            
        except Exception as e:
            logger.error(f"❌ {domain} FAISS 로드 실패: {e}")
            return False
    
    def preload_all_indexes(self) -> Dict[str, Any]:
        """모든 FAISS 도메인 인덱스 사전 로드"""
        logger.info(f"🚀 FAISS 인덱스 사전 로드 시작: {self.faiss_domains}")
        start_time = time.time()
        
        loaded = [domain for domain in self.faiss_domains if self._load_single_domain(domain)]
        failed = [domain for domain in self.faiss_domains if domain not in loaded]
        
        self.load_stats = {
            "loaded_domains": loaded,
            "failed_domains": failed,
            "load_time": time.time() - start_time,
            "last_loaded": datetime.now()
        }
        
        logger.info(f"🎉 FAISS 인덱스 로드 완료: {len(loaded)}/{len(self.faiss_domains)}개 성공 ({self.load_stats['load_time']:.2f}초)")
        return {"success": True, "loaded_domains": loaded, "failed_domains": failed}
    
    def get_vectorstore(self, domain: str) -> Optional[FAISS]:
        """도메인별 벡터스토어 반환 (핸들러들이 사용하는 메인 API)"""
        if domain not in self.faiss_domains:
            logger.warning(f"⚠️ 지원하지 않는 FAISS 도메인: {domain}")
            return None
        return self.vectorstores.get(domain)

# =============================================================================
# 기존 함수들은 그대로 유지 (내부적으로 새 로직 사용)
# =============================================================================
_index_manager_instance = None
def get_index_manager() -> IndexManager:
    global _index_manager_instance
    if _index_manager_instance is None:
        _index_manager_instance = IndexManager()
    return _index_manager_instance

def preload_all_indexes() -> Dict[str, Any]:
    return get_index_manager().preload_all_indexes()

def index_health_check() -> Dict[str, Any]:
    # (health_check는 필요 시 더 상세하게 수정 가능)
    return get_index_manager().load_stats
