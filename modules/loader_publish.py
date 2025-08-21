#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 발행물 벡터스토어 로더

교육훈련계획서/종합평가서 PDF → FAISS 벡터스토어 생성
"""

import os
import logging
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from config.config import EMBEDDING_MODEL
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

# PDF 처리
try:
    from PyPDF2 import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# =============================================================================
# 🔧 파인튜닝 설정
# =============================================================================

# 경로 설정
SOURCE_DIR = "data/publish"
VECTORSTORE_DIR = "vectorstores/vectorstore_unified_publish"
INDEX_NAME = "publish_index"

# 파일 설정
PLAN_PDF = "2025plan.pdf"
EVALUATION_PDF = "2024pyeongga.pdf"

# 텍스트 처리
MIN_PAGE_TEXT_LENGTH = 50

# 문서 타입 매핑
DOC_TYPES = {
    PLAN_PDF: "2025 교육훈련계획서",
    EVALUATION_PDF: "2024 종합평가서"
}

# 통합 템플릿 (단순화)
PDF_TEMPLATE = """[{doc_type}] 페이지 {page_number}

{content}

[출처: {filename} 페이지 {page_number}]"""

# =============================================================================

logger = logging.getLogger(__name__)


class TextChunk:
    def __init__(self, text: str, source_id: str, metadata: Dict[str, Any] = None):
        self.text = text
        self.source_id = source_id
        self.metadata = metadata or {}


class PublishLoader:
    def __init__(self):
        # API 키 및 임베딩
        self.api_key = os.getenv("OPENAI_API_KEY_DEV")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY_DEV 환경변수가 필요합니다")
        
        self.embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=self.api_key)
        
        # 경로 설정
        root = Path(__file__).parent.parent
        self.source_dir = root / SOURCE_DIR
        self.vectorstore_dir = root / VECTORSTORE_DIR
        self.vectorstore_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"PublishLoader 초기화: {EMBEDDING_MODEL}")
    
    def build_vectorstore(self, force_rebuild: bool = False) -> bool:
        """벡터스토어 빌드"""
        try:
            if not force_rebuild and not self._needs_rebuild():
                logger.info("벡터스토어가 최신상태입니다")
                return True
            
            logger.info("벡터스토어 빌드 시작...")
            start_time = time.time()
            
            # 데이터 처리
            chunks = self._process_data()
            
            # FAISS 생성
            texts = [chunk.text for chunk in chunks]
            metadatas = [chunk.metadata for chunk in chunks]
            
            vectorstore = FAISS.from_texts(texts, self.embeddings, metadatas)
            vectorstore.save_local(str(self.vectorstore_dir), INDEX_NAME)
            
            # 해시 저장
            self._save_hash()
            
            elapsed = time.time() - start_time
            logger.info(f"빌드 완료: {len(chunks)}개 청크, {elapsed:.1f}초")
            return True
            
        except Exception as e:
            logger.error(f"빌드 실패: {e}")
            raise
    
    def _process_data(self) -> List[TextChunk]:
        """PDF 파일들 처리"""
        if not PDF_AVAILABLE:
            raise ValueError("PyPDF2 라이브러리가 필요합니다")
        
        chunks = []
        
        # 발행물 PDF들 처리
        for filename, doc_type in DOC_TYPES.items():
            pdf_chunks = self._process_pdf(filename, doc_type)
            chunks.extend(pdf_chunks)
        
        if not chunks:
            raise ValueError("처리할 데이터가 없습니다")
        
        logger.info(f"데이터 처리 완료: {len(chunks)}개 청크")
        return chunks
    
    def _process_pdf(self, filename: str, doc_type: str) -> List[TextChunk]:
        """PDF 파일 처리"""
        chunks = []
        pdf_file = self.source_dir / filename
        
        if not pdf_file.exists():
            logger.warning(f"PDF 파일 없음: {filename}")
            return chunks
        
        try:
            with open(pdf_file, 'rb') as file:
                pdf_reader = PdfReader(file)
                total_pages = len(pdf_reader.pages)
                
                for page_num, page in enumerate(pdf_reader.pages, 1):
                    page_text = page.extract_text()
                    
                    if len(page_text.strip()) < MIN_PAGE_TEXT_LENGTH:
                        continue
                    
                    chunk = self._create_pdf_chunk(
                        page_text, filename, doc_type, page_num, total_pages
                    )
                    chunks.append(chunk)
            
            logger.info(f"{filename} 처리 완료: {len(chunks)}개 청크")
            
        except Exception as e:
            logger.error(f"PDF 처리 실패 ({filename}): {e}")
        
        return chunks
    
    def _create_pdf_chunk(self, page_text: str, filename: str, doc_type: str, 
                         page_num: int, total_pages: int) -> TextChunk:
        """PDF 청크 생성"""
        # 템플릿 적용
        content = PDF_TEMPLATE.format(
            doc_type=doc_type,
            page_number=page_num,
            content=page_text.strip(),
            filename=filename
        )
        
        # 메타데이터
        metadata = {
            'source_file': filename,
            'file_type': 'pdf',
            'document_type': doc_type,
            'page_number': page_num,
            'total_pages': total_pages,
            'char_count': len(page_text),
            'processing_date': datetime.now().isoformat()
        }
        
        source_id = f'publish/{filename}#page_{page_num}'
        return TextChunk(content, source_id, metadata)
    
    def _needs_rebuild(self) -> bool:
        """재빌드 필요 여부"""
        # FAISS 파일 확인
        faiss_file = self.vectorstore_dir / f"{INDEX_NAME}.faiss"
        pkl_file = self.vectorstore_dir / f"{INDEX_NAME}.pkl"
        
        if not (faiss_file.exists() and pkl_file.exists()):
            return True
        
        # 해시 비교
        hash_file = self.vectorstore_dir / ".source_hash"
        if not hash_file.exists():
            return True
        
        current_hash = self._calculate_hash()
        with open(hash_file, 'r') as f:
            stored_hash = f.read().strip()
        
        return current_hash != stored_hash
    
    def _calculate_hash(self) -> str:
        """소스 해시 계산"""
        hasher = hashlib.md5()
        hasher.update(EMBEDDING_MODEL.encode())
        
        for filename in DOC_TYPES.keys():
            file_path = self.source_dir / filename
            if file_path.exists():
                hasher.update(str(file_path.stat().st_mtime).encode())
        
        return hasher.hexdigest()[:16]
    
    def _save_hash(self):
        """현재 해시 저장"""
        hash_file = self.vectorstore_dir / ".source_hash"
        with open(hash_file, 'w') as f:
            f.write(self._calculate_hash())


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
