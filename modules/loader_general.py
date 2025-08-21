#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 일반 도메인 로더 (BaseLoader 패턴 준수)

notice 로더 패턴을 따라 완전히 수정됨:
- process_domain_data(self) 시그니처로 변경
- 원본 파일 직접 읽기 로직 추가
- BaseLoader 표준 패턴 완전 준수
- 기존 템플릿 시스템 유지
"""

import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# PyPDF2 직접 임포트 (PDFProcessor 의존성 제거)
try:
    from PyPDF2 import PdfReader
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

# 프로젝트 모듈 임포트
from modules.base_loader import BaseLoader
from utils.textifier import TextChunk
from config.config import config

# 로깅 설정
logger = logging.getLogger(__name__)


class GeneralLoader(BaseLoader):
    """
    일반 도메인 로더 - BaseLoader 표준 패턴 준수
    
    처리 대상:
    - data/general/hakchik.pdf (학칙+감점기준+전결규정 통합문서)
    - data/general/operation_test.pdf (운영/평가 계획)
    - data/general/task_telephone.csv (업무담당자 연락처)
    
    특징:
    - notice 로더와 동일한 process_domain_data(self) 시그니처
    - 원본 파일 직접 읽기
    - PyPDF2 직접 사용 (PDFProcessor 의존성 제거)
    - 기존 코랩 템플릿 완벽 보존
    - 해시 기반 증분 빌드 지원
    """
    
    def __init__(self):
        super().__init__(
            domain="general",
            source_dir=config.ROOT_DIR / "data" / "general",
            vectorstore_dir=config.ROOT_DIR / "vectorstores" / "vectorstore_general",
            index_name="general_index"
        )

        
        # 처리할 파일 정의
        self.hakchik_file = self.source_dir / "hakchik.pdf"
        self.operation_file = self.source_dir / "operation_test.pdf"
        self.telephone_file = self.source_dir / "task_telephone.csv"
    
    def process_domain_data(self) -> List[TextChunk]:
        """
        BaseLoader 인터페이스 구현: 일반 도메인 데이터 처리
        
        ✅ notice 로더와 동일한 시그니처: process_domain_data(self)
        """
        all_chunks = []
        
        # 1. PDF 파일들 처리
        pdf_chunks = self._process_pdf_files()
        all_chunks.extend(pdf_chunks)
        
        # 2. CSV 파일 처리 (업무담당자 연락처)
        csv_chunks = self._process_telephone_csv()
        all_chunks.extend(csv_chunks)
        
        logger.info(f"✅ 일반 도메인 통합 처리 완료: PDF {len(pdf_chunks)}개 + CSV {len(csv_chunks)}개 = 총 {len(all_chunks)}개 청크")
        
        return all_chunks
    
    def _process_pdf_files(self) -> List[TextChunk]:
        """PDF 파일들 직접 읽기 및 처리 (PyPDF2 직접 사용)"""
        chunks = []
        
        if not PDF_AVAILABLE:
            logger.error("❌ PyPDF2 라이브러리가 설치되지 않았습니다")
            return chunks
        
        pdf_files = [
            (self.hakchik_file, "regulations", "통합규정문서"),
            (self.operation_file, "operations", "운영평가계획")
        ]
        
        for pdf_file, category, doc_type in pdf_files:
            if not pdf_file.exists():
                logger.warning(f"PDF 파일이 없습니다: {pdf_file}")
                continue
            
            try:
                logger.info(f"📄 PDF 처리 시작: {pdf_file}")
                
                # PyPDF2로 직접 PDF 읽기
                with open(pdf_file, 'rb') as file:
                    pdf_reader = PdfReader(file)
                    total_pages = len(pdf_reader.pages)
                    
                    logger.info(f"PDF 총 페이지 수: {total_pages}")
                    
                    for page_num, page in enumerate(pdf_reader.pages, 1):
                        try:
                            # 페이지 텍스트 추출
                            page_text = page.extract_text()
                            
                            if not page_text or len(page_text.strip()) < 50:
                                logger.debug(f"페이지 {page_num}: 텍스트가 너무 짧거나 없음 (건너뜀)")
                                continue
                            
                            # 텍스트 청크 생성
                            chunk_text = f"[{doc_type}] 페이지 {page_num}\n\n{page_text.strip()}"
                            
                            # 메타데이터 생성
                            metadata = {
                                'source_file': pdf_file.name,
                                'file_type': 'pdf',
                                'category': category,
                                'doc_type': doc_type,
                                'domain': 'general',
                                'page_number': page_num,
                                'total_pages': total_pages,
                                'char_count': len(page_text),
                                'cache_ttl': 2592000,  # 30일 TTL
                                'processing_date': datetime.now().isoformat(),
                                'chunk_type': 'document'
                            }
                            
                            chunk = TextChunk(
                                text=chunk_text,
                                source_id=f'general/{pdf_file.name}#page_{page_num}',
                                metadata=metadata
                            )
                            
                            chunks.append(chunk)
                            
                        except Exception as e:
                            logger.error(f"페이지 {page_num} 처리 실패: {e}")
                            continue
                
                logger.info(f"✅ {pdf_file.name} 처리 완료: {len([c for c in chunks if c.metadata.get('source_file') == pdf_file.name])}개 청크")
                
            except Exception as e:
                logger.error(f"❌ PDF 파일 처리 실패 ({pdf_file}): {e}")
                continue
        
        return chunks
    
    def _process_telephone_csv(self) -> List[TextChunk]:
        """업무담당자 연락처 CSV 직접 읽기 및 처리 (기존 코랩 템플릿 보존)"""
        chunks = []
        
        if not self.telephone_file.exists():
            logger.warning(f"연락처 파일이 없습니다: {self.telephone_file}")
            return chunks
        
        try:
            logger.info(f"📞 연락처 CSV 처리 시작: {self.telephone_file}")
            
            # CSV 인코딩 자동 감지 및 읽기
            df = self._read_csv_with_encoding(self.telephone_file)
            
            if df is None:
                return chunks
            
            logger.info(f"📄 연락처 데이터: {len(df)}행 로드됨")
            
            # 각 행을 기존 코랩 템플릿으로 변환
            for idx, row in df.iterrows():
                try:
                    # 기존 코랩 템플릿 완벽 보존
                    chunk_text = (
                        f"담당업무: {row['담당업무']}\n"
                        f"  - 담당자: {row['부서']} {row['직책']}\n"
                        f"  - 연락처: {row['전화번호']}\n"
                    )
                    
                    # 메타데이터 생성
                    metadata = {
                        'source_file': 'task_telephone.csv',
                        'file_type': 'csv',
                        'category': 'contact',
                        'doc_type': '업무담당자연락처',
                        'domain': 'general',
                        'row_index': idx,
                        'department': str(row['부서']),
                        'position': str(row['직책']),
                        'phone': str(row['전화번호']),
                        'task_area': str(row['담당업무']),
                        'cache_ttl': 2592000,  # 30일 TTL
                        'processing_date': datetime.now().isoformat(),
                        'chunk_type': 'contact'
                    }
                    
                    chunk = TextChunk(
                        text=chunk_text,
                        source_id=f'general/task_telephone.csv#row_{idx}',
                        metadata=metadata
                    )
                    
                    chunks.append(chunk)
                    
                except Exception as e:
                    logger.error(f"연락처 행 {idx} 처리 실패: {e}")
                    continue
            
            logger.info(f"✅ 연락처 CSV 처리 완료: {len(chunks)}개 청크 생성 (기존 템플릿 보존)")
            
        except Exception as e:
            logger.error(f"❌ 연락처 CSV 파일 처리 실패: {e}")
        
        return chunks
    
    def _read_csv_with_encoding(self, csv_file: Path) -> Optional[pd.DataFrame]:
        """인코딩 자동 감지로 CSV 읽기"""
        encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig']
        
        for encoding in encodings:
            try:
                df = pd.read_csv(csv_file, encoding=encoding)
                logger.info(f"CSV 파일 로드 성공 (인코딩: {encoding})")
                
                # 필수 컬럼 확인
                required_columns = ['부서', '직책', '전화번호', '담당업무']
                missing_columns = [col for col in required_columns if col not in df.columns]
                
                if missing_columns:
                    logger.error(f"필수 컬럼 누락: {missing_columns}")
                    logger.error(f"실제 컬럼: {list(df.columns)}")
                    return None
                
                return df
                
            except UnicodeDecodeError:
                logger.debug(f"인코딩 {encoding} 실패, 다음 시도...")
                continue
            except Exception as e:
                logger.error(f"CSV 파일 읽기 실패 (인코딩: {encoding}): {e}")
                continue
        
        logger.error(f"모든 인코딩 시도 실패: {csv_file}")
        return None


# ================================================================
# 개발/테스트용 진입점
# ================================================================

def main():
    """개발/테스트용 진입점"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    loader = GeneralLoader()
    
    try:
        # BaseLoader의 표준 인터페이스 사용
        success = loader.build_vectorstore()
        
        if success:
            logger.info("✅ 일반 도메인 벡터스토어 구축 완료")
        else:
            logger.error("❌ 일반 도메인 벡터스토어 구축 실패")
            
    except Exception as e:
        logger.error(f"❌ 로더 실행 실패: {e}")
        raise


if __name__ == '__main__':
    main()
