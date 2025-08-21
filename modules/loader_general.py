#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 일반 정보 벡터스토어 로더

학칙/규정/연락처 PDF+CSV → FAISS 벡터스토어 생성
"""

import os
import logging
import pandas as pd
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
SOURCE_DIR = "data/general"
VECTORSTORE_DIR = "vectorstores/vectorstore_general"
INDEX_NAME = "general_index"

# 파일 설정
HAKCHIK_PDF = "hakchik.pdf"
OPERATION_PDF = "operation_test.pdf"
TELEPHONE_CSV = "task_telephone.csv"
CSV_ENCODINGS = ['utf-8', 'cp949', 'euc-kr']

# 필수 컬럼
TELEPHONE_COLUMNS = ['부서', '직책', '전화번호', '담당업무']

# 텍스트 처리
MIN_PAGE_TEXT_LENGTH = 50
CHUNK_PREFIX_REGULATIONS = "[통합규정문서]"
CHUNK_PREFIX_OPERATIONS = "[운영평가계획]"

# 템플릿
TELEPHONE_TEMPLATE = """담당업무: {담당업무}
  - 담당자: {부서} {직책}
  - 연락처: {전화번호}
"""

# =============================================================================

logger = logging.getLogger(__name__)


class TextChunk:
    def __init__(self, text: str, source_id: str, metadata: Dict[str, Any] = None):
        self.text = text
        self.source_id = source_id
        self.metadata = metadata or {}


class GeneralLoader:
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
        
        logger.info(f"GeneralLoader 초기화: {EMBEDDING_MODEL}")
    
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
        """PDF와 CSV 파일들 처리"""
        chunks = []
        
        # PDF 파일들 처리
        pdf_files = [
            (HAKCHIK_PDF, "regulations", CHUNK_PREFIX_REGULATIONS),
            (OPERATION_PDF, "operations", CHUNK_PREFIX_OPERATIONS)
        ]
        
        for filename, category, prefix in pdf_files:
            pdf_chunks = self._process_pdf(filename, category, prefix)
            chunks.extend(pdf_chunks)
        
        # CSV 파일 처리
        csv_chunks = self._process_telephone_csv()
        chunks.extend(csv_chunks)
        
        if not chunks:
            raise ValueError("처리할 데이터가 없습니다")
        
        logger.info(f"데이터 처리 완료: {len(chunks)}개 청크")
        return chunks
    
    def _process_pdf(self, filename: str, category: str, prefix: str) -> List[TextChunk]:
        """PDF 파일 처리"""
        chunks = []
        pdf_file = self.source_dir / filename
        
        if not pdf_file.exists():
            logger.warning(f"PDF 파일 없음: {filename}")
            return chunks
        
        if not PDF_AVAILABLE:
            logger.error(f"PyPDF2 라이브러리가 필요합니다")
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
                        page_text, filename, category, prefix, 
                        page_num, total_pages
                    )
                    chunks.append(chunk)
            
            logger.info(f"{filename} 처리 완료: {len(chunks)}개 청크")
            
        except Exception as e:
            logger.error(f"PDF 처리 실패 ({filename}): {e}")
        
        return chunks
    
    def _create_pdf_chunk(self, page_text: str, filename: str, category: str, 
                         prefix: str, page_num: int, total_pages: int) -> TextChunk:
        """PDF 청크 생성"""
        content = f"{prefix} 페이지 {page_num}\n\n{page_text.strip()}"
        
        metadata = {
            'source_file': filename,
            'file_type': 'pdf',
            'category': category,
            'page_number': page_num,
            'total_pages': total_pages,
            'char_count': len(page_text),
            'processing_date': datetime.now().isoformat()
        }
        
        source_id = f'general/{filename}#page_{page_num}'
        return TextChunk(content, source_id, metadata)
    
    def _process_telephone_csv(self) -> List[TextChunk]:
        """연락처 CSV 처리"""
        chunks = []
        csv_file = self.source_dir / TELEPHONE_CSV
        
        if not csv_file.exists():
            logger.warning(f"CSV 파일 없음: {TELEPHONE_CSV}")
            return chunks
        
        try:
            df = self._read_csv(csv_file)
            
            # 필수 컬럼 확인
            missing_cols = [col for col in TELEPHONE_COLUMNS if col not in df.columns]
            if missing_cols:
                logger.error(f"필수 컬럼 누락: {missing_cols}")
                return chunks
            
            for idx, row in df.iterrows():
                chunk = self._create_telephone_chunk(row, idx)
                if chunk:
                    chunks.append(chunk)
            
            logger.info(f"연락처 처리 완료: {len(chunks)}개 청크")
            
        except Exception as e:
            logger.error(f"CSV 처리 실패: {e}")
        
        return chunks
    
    def _create_telephone_chunk(self, row: pd.Series, idx: int) -> TextChunk:
        """연락처 청크 생성"""
        data = row.to_dict()
        
        # 필수 데이터 확인
        for col in TELEPHONE_COLUMNS:
            if pd.isna(data.get(col)):
                logger.warning(f"연락처 행 {idx}: {col} 누락")
                return None
        
        # 데이터 정제
        clean_data = {k: str(v).strip() if not pd.isna(v) else '' for k, v in data.items()}
        
        # 템플릿 적용
        try:
            content = TELEPHONE_TEMPLATE.format(**clean_data)
        except KeyError as e:
            logger.error(f"연락처 템플릿 오류 (행 {idx}): {e}")
            return None
        
        # 메타데이터
        metadata = {
            'source_file': TELEPHONE_CSV,
            'file_type': 'csv',
            'category': 'contact',
            'row_index': idx,
            'department': clean_data.get('부서', ''),
            'position': clean_data.get('직책', ''),
            'phone': clean_data.get('전화번호', ''),
            'task_area': clean_data.get('담당업무', ''),
            'processing_date': datetime.now().isoformat()
        }
        
        source_id = f'general/{TELEPHONE_CSV}#row_{idx}'
        return TextChunk(content, source_id, metadata)
    
    def _read_csv(self, file_path: Path) -> pd.DataFrame:
        """CSV 파일 읽기"""
        for encoding in CSV_ENCODINGS:
            try:
                return pd.read_csv(file_path, encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"CSV 읽기 실패: {file_path}")
    
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
        
        for filename in [HAKCHIK_PDF, OPERATION_PDF, TELEPHONE_CSV]:
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
        loader = GeneralLoader()
        loader.build_vectorstore()
        print("✅ 일반 정보 벡터스토어 구축 완료")
    except Exception as e:
        print(f"❌ 실패: {e}")
        exit(1)


if __name__ == '__main__':
    main()
