#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 공지사항 벡터스토어 로더 (단순화 버전)

TextLoader + RecursiveCharacterTextSplitter → FAISS 벡터스토어 생성
"""

import os
import logging
import streamlit as st
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

# =============================================================================
# 🔧 파인튜닝 설정 구역
# =============================================================================

# 경로 설정
SOURCE_FILE = "data/notice/notice.txt"
VECTORSTORE_DIR = "vectorstores/vectorstore_notice"
INDEX_NAME = "notice_index"

# 청킹 설정
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# 임베딩 모델
EMBEDDING_MODEL = "text-embedding-3-large"

# =============================================================================

logger = logging.getLogger(__name__)


def get_api_key() -> str:
    """Streamlit Secrets에서 API 키 가져오기"""
    try:
        # Streamlit Secrets 우선
        if hasattr(st, 'secrets') and st.secrets:
            api_key = st.secrets.get("OPENAI_API_KEY")
            if api_key:
                return api_key
    except Exception:
        pass
    
    # 환경변수 대안
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY를 Streamlit Secrets 또는 환경변수에 설정해주세요")
    
    return api_key


class NoticeLoader:
    """단순화된 공지사항 로더"""
    
    def __init__(self):
        """로더 초기화"""
        self.api_key = get_api_key()
        self.embeddings = OpenAIEmbeddings(
            model=EMBEDDING_MODEL,
            api_key=self.api_key
        )
        
        # 경로 설정
        self.project_root = Path(__file__).parent.parent
        self.source_file = self.project_root / SOURCE_FILE
        self.vectorstore_dir = self.project_root / VECTORSTORE_DIR
        
        # 디렉터리 생성
        self.vectorstore_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"NoticeLoader 초기화 완료: {EMBEDDING_MODEL}")
    
    def build_vectorstore(self, force_rebuild: bool = False) -> bool:
        """벡터스토어 빌드"""
        try:
            # 파일 존재 확인
            if not self.source_file.exists():
                raise FileNotFoundError(f"소스 파일이 없습니다: {self.source_file}")
            
            # 기존 벡터스토어 확인
            faiss_file = self.vectorstore_dir / f"{INDEX_NAME}.faiss"
            pkl_file = self.vectorstore_dir / f"{INDEX_NAME}.pkl"
            
            if not force_rebuild and faiss_file.exists() and pkl_file.exists():
                logger.info("기존 벡터스토어를 사용합니다")
                return True
            
            logger.info("🚀 벡터스토어 빌드 시작...")
            
            # 1. 텍스트 로드
            loader = TextLoader(
                str(self.source_file),
                encoding='utf-8'
            )
            documents = loader.load()
            logger.info(f"✅ 문서 로드 완료: {len(documents)}개 문서")
            
            # 2. 텍스트 분할
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=CHUNK_SIZE,
                chunk_overlap=CHUNK_OVERLAP,
                separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""]
            )
            chunks = text_splitter.split_documents(documents)
            logger.info(f"✅ 텍스트 분할 완료: {len(chunks)}개 청크")
            
            # 3. 메타데이터 추가 (기존 시스템 호환성)
            for i, chunk in enumerate(chunks):
                chunk.metadata.update({
                    'source_file': 'notice.txt',
                    'chunk_id': i,
                    'domain': 'notice',
                    'chunk_type': 'notice'
                })
            
            # 4. FAISS 벡터스토어 생성
            vectorstore = FAISS.from_documents(
                chunks,
                self.embeddings
            )
            logger.info(f"✅ 임베딩 완료: {len(chunks)}개 청크")
            
            # 5. 벡터스토어 저장
            vectorstore.save_local(
                str(self.vectorstore_dir),
                INDEX_NAME
            )
            logger.info(f"✅ 벡터스토어 저장 완료: {self.vectorstore_dir}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 벡터스토어 빌드 실패: {e}")
            raise
    
    def get_stats(self) -> dict:
        """벡터스토어 통계 정보"""
        try:
            faiss_file = self.vectorstore_dir / f"{INDEX_NAME}.faiss"
            pkl_file = self.vectorstore_dir / f"{INDEX_NAME}.pkl"
            
            if not (faiss_file.exists() and pkl_file.exists()):
                return {"exists": False}
            
            # 파일 크기 정보
            faiss_size = faiss_file.stat().st_size / (1024 * 1024)  # MB
            pkl_size = pkl_file.stat().st_size / (1024 * 1024)      # MB
            
            return {
                "exists": True,
                "faiss_size_mb": round(faiss_size, 2),
                "pkl_size_mb": round(pkl_size, 2),
                "total_size_mb": round(faiss_size + pkl_size, 2),
                "source_file": str(self.source_file),
                "vectorstore_dir": str(self.vectorstore_dir),
                "chunk_settings": {
                    "chunk_size": CHUNK_SIZE,
                    "chunk_overlap": CHUNK_OVERLAP,
                    "embedding_model": EMBEDDING_MODEL
                }
            }
            
        except Exception as e:
            logger.error(f"통계 조회 실패: {e}")
            return {"exists": False, "error": str(e)}


def main():
    """스크립트 실행 진입점"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        print("🌟 경상남도인재개발원 공지사항 벡터스토어 로더")
        print("=" * 50)
        
        # 로더 초기화
        loader = NoticeLoader()
        
        # 현재 상태 확인
        stats = loader.get_stats()
        if stats.get("exists"):
            print(f"📁 기존 벡터스토어: {stats['total_size_mb']}MB")
            
            rebuild = input("기존 벡터스토어를 재빌드하시겠습니까? (y/N): ").lower() == 'y'
            if not rebuild:
                print("✅ 기존 벡터스토어를 유지합니다")
                return
        
        # 빌드 실행
        success = loader.build_vectorstore(force_rebuild=True)
        
        if success:
            # 최종 통계
            final_stats = loader.get_stats()
            print("\n🎉 빌드 완료!")
            print(f"📊 벡터스토어 크기: {final_stats['total_size_mb']}MB")
            print(f"📁 저장 위치: {final_stats['vectorstore_dir']}")
        else:
            print("❌ 빌드 실패")
            
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        exit(1)


if __name__ == '__main__':
    main()
