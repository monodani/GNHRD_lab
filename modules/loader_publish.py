#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 발행물 벡터스토어 로더 (간소화)

publish.pdf → FAISS 벡터스토어 생성 (PDFPlumber 방식)
"""

import os
import logging
import streamlit as st
from pathlib import Path

try:
    from langchain_community.document_loaders import PDFPlumberLoader
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS
    from langchain_openai import OpenAIEmbeddings
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# =============================================================================
# 🔧 파인튜닝 설정 구역
# =============================================================================

# 경로 설정
SOURCE_FILE = "data/publish/publish.pdf"
VECTORSTORE_DIR = "vectorstores/vectorstore_publish"
INDEX_NAME = "publish_index"

# 임베딩 모델
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072

# 텍스트 분할 설정
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

# =============================================================================

logger = logging.getLogger(__name__)

class PublishLoader:
    """간소화된 발행물 로더 (PDFPlumber 방식)"""
    
    def __init__(self):
        # API 키 확인
        self.api_key = st.secrets.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 필요합니다")
        
        # 경로 설정
        self.root = Path(__file__).parent.parent
        self.source_file = self.root / SOURCE_FILE
        self.vectorstore_dir = self.root / VECTORSTORE_DIR
        self.vectorstore_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("PublishLoader 간소화 버전 초기화")
    
    def build_vectorstore(self, force_rebuild: bool = False) -> bool:
        """벡터스토어 빌드 (코랩 방식)"""
        if not PDF_AVAILABLE:
            raise ValueError("필요한 라이브러리 설치: pip install langchain_community pdfplumber faiss-cpu langchain_openai")
        
        if not self.source_file.exists():
            raise ValueError(f"파일 없음: {self.source_file}")
        
        try:
            logger.info("PDF 로드 및 분할 시작...")
            
            # PDF 로드 (PDFPlumber 방식)
            loader = PDFPlumberLoader(str(self.source_file))
            docs = loader.load()
            
            # 텍스트 분할
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=CHUNK_SIZE, 
                chunk_overlap=CHUNK_OVERLAP
            )
            split_docs = text_splitter.split_documents(docs)
            
            logger.info(f"문서 분할 완료: {len(split_docs)}개 청크")
            
            # 임베딩 생성
            embedding = OpenAIEmbeddings(
                api_key=self.api_key,
                model=EMBEDDING_MODEL,
                dimensions=EMBEDDING_DIMENSIONS
            )
            
            # FAISS 벡터스토어 생성
            vectorstore = FAISS.from_documents(documents=split_docs, embedding=embedding)
            
            # 저장 (publish_index.faiss, publish_index.pkl)
            vectorstore.save_local(str(self.vectorstore_dir), INDEX_NAME)
            
            logger.info(f"벡터스토어 저장 완료: {self.vectorstore_dir}/{INDEX_NAME}")
            return True
            
        except Exception as e:
            logger.error(f"빌드 실패: {e}")
            raise

def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    try:
        loader = PublishLoader()
        loader.build_vectorstore()
        print("✅ 발행물 벡터스토어 구축 완료")
    except Exception as e:
        print(f"❌ 실패: {e}")
        exit(1)

if __name__ == '__main__':
    main()
