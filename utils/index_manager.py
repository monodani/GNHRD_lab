# utils/index_manager.py (v5.2 - SyntaxError 수정)
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - 인덱스 관리자 v5.2 (안정화)
Config-Driven 기반 FAISS 벡터스토어 관리 시스템
"""
import logging
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Any, List
from datetime import datetime

# --- 프로젝트 모듈 ---
from config.config import get_config, EMBEDDING_MODEL
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

logger = logging.getLogger(__name__)

class IndexManager:
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
        self.faiss_domains: List[str] = [
            name for name, conf in self.config.HANDLERS.items() if conf.get('type') == 'faiss'
        ]
        
        self.vectorstores: Dict[str, Optional[FAISS]] = {}
        self.load_stats = {"loaded_domains": [], "failed_domains": [], "load_time": 0.0, "last_loaded": None}
        self.embeddings = self._init_embeddings()
        
        logger.info(f"✅ IndexManager v5.2 초기화 완료 ({len(self.faiss_domains)}개 FAISS 도메인 지원)")
        self._initialized = True
    
    def _init_embeddings(self) -> Optional[OpenAIEmbeddings]:
        try:
            if not self.config.OPENAI_API_KEY:
                logger.error("❌ OPENAI_API_KEY가 설정되지 않았습니다.")
                return None
            
            langchain_embeddings = OpenAIEmbeddings(
                api_key=self.config.OPENAI_API_KEY,
                model=EMBEDDING_MODEL
            )
            logger.info(f"✅ Langchain OpenAI 임베딩 초기화 성공: {EMBEDDING_MODEL}")
            return langchain_embeddings
        except Exception as e:
            logger.error(f"❌ OpenAI 임베딩 초기화 실패: {e}")
            return None
    
    def _load_single_domain(self, domain: str) -> bool:
        if not self.embeddings:
            logger.warning(f"⚠️ 임베딩 객체가 없어 {domain} 로드를 건너뜁니다.")
            return False
        
        try:
            vectorstore_path = self.config.get_vectorstore_path(domain)
            index_name = f"{domain}_index"
            if not (vectorstore_path / f"{index_name}.faiss").exists():
                 logger.warning(f"⚠️ {domain} 인덱스 파일이 없습니다: {vectorstore_path}")
                 return False

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
        if domain not in self.faiss_domains:
            logger.warning(f"⚠️ 지원하지 않는 FAISS 도메인: {domain}")
            return None
        return self.vectorstores.get(domain)

    def health_check(self) -> Dict[str, Any]:
        loaded_count = len(self.load_stats.get("loaded_domains", []))
        total_count = len(self.faiss_domains)
        is_healthy = (total_count > 0) and (loaded_count == total_count)
        
        return {
            "is_healthy": is_healthy,
            "loaded_count": loaded_count,
            "total_count": total_count,
            "loaded_domains": self.load_stats.get("loaded_domains", []),
            "failed_domains": self.load_stats.get("failed_domains", []),
            "load_time": self.load_stats.get("load_time", 0)
        } # 🔥 [수정] 빠져있던 '}'를 추가하여 문법 오류 해결

# --- 전역 함수들 ---
_index_manager_instance = None
def get_index_manager() -> IndexManager:
    global _index_manager_instance
    if _index_manager_instance is None:
        _index_manager_instance = IndexManager()
    return _index_manager_instance

def preload_all_indexes() -> Dict[str, Any]:
    return get_index_manager().preload_all_indexes()

def index_health_check() -> Dict[str, Any]:
    # 🔥 [수정] 업그레이드된 클래스 내부의 health_check 메서드를 호출하도록 변경
    return get_index_manager().health_check()
