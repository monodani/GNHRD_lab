#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 발행물 PDF 로더 (BaseLoader 패턴 준수)

notice 로더 패턴을 따라 완전히 수정됨:
- process_domain_data(self) 시그니처로 변경
- DocumentProcessor 의존성 완전 제거
- PyPDF2 직접 사용으로 PDF 읽기
- BaseLoader 표준 패턴 완전 준수
- 기존 템플릿 시스템 유지
- Citation 모델 유효성 검사 오류 수정 (context 길이 제한)
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# PyPDF2 직접 임포트 (DocumentProcessor 의존성 제거)
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


class PublishLoader(BaseLoader):
    """
    발행물 PDF 로더 - BaseLoader 표준 패턴 준수
    
    처리 대상:
    - data/publish/2025plan.pdf (2025 교육훈련계획서)
    - data/publish/2024pyeongga.pdf (2024 종합평가서)
    
    특징:
    - notice 로더와 동일한 process_domain_data(self) 시그니처
    - DocumentProcessor 의존성 완전 제거
    - PyPDF2 직접 사용으로 PDF 읽기
    - 발행물별 템플릿 적용
    - 해시 기반 증분 빌드 지원
    """
    
    def __init__(self):
        super().__init__(
            domain="publish",
            source_dir=config.ROOT_DIR / "data" / "publish",
            vectorstore_dir=config.ROOT_DIR / "vectorstores" / "vectorstore_unified_publish",
            index_name="publish_index"
        )
        
        # 처리할 파일 정의
        self.plan_file = self.source_dir / "2025plan.pdf"
        self.evaluation_file = self.source_dir / "2024pyeongga.pdf"
        
        # 발행물별 템플릿
        self.templates = {
            "2025plan": self._get_plan_template(),
            "2024pyeongga": self._get_evaluation_template(),
            "default": self._get_default_template()
        }
    
    def process_domain_data(self) -> List[TextChunk]:
        """
        BaseLoader 인터페이스 구현: 발행물 PDF 데이터 처리
        
        ✅ notice 로더와 동일한 시그니처: process_domain_data(self)
        """
        if not PDF_AVAILABLE:
            logger.error("❌ PyPDF2 라이브러리가 설치되지 않았습니다")
            return []
        
        all_chunks = []
        
        # 1. 2025 교육훈련계획서 처리
        plan_chunks = self._process_pdf_file(self.plan_file, "2025plan", "2025 교육훈련계획서")
        all_chunks.extend(plan_chunks)
        
        # 2. 2024 종합평가서 처리
        evaluation_chunks = self._process_pdf_file(self.evaluation_file, "2024pyeongga", "2024 종합평가서")
        all_chunks.extend(evaluation_chunks)
        
        logger.info(f"✅ 발행물 통합 처리 완료: 계획서 {len(plan_chunks)}개 + 평가서 {len(evaluation_chunks)}개 = 총 {len(all_chunks)}개 청크")
        
        return all_chunks
    
    def _process_pdf_file(self, pdf_file: Path, template_key: str, doc_type: str) -> List[TextChunk]:
        """PDF 파일 직접 읽기 및 처리"""
        chunks = []
        
        if not pdf_file.exists():
            logger.warning(f"PDF 파일이 없습니다: {pdf_file}")
            return chunks
        
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
                        
                        # Pydantic Citation 모델의 context 필드 유효성 검사 오류를 방지하기 위해 
                        # context의 길이를 200자로 제한합니다.
                        truncated_content = page_text[:200] + '...' if len(page_text) > 200 else page_text
                        
                        # 템플릿 적용
                        formatted_content = self._apply_template(
                            content=page_text.strip(),
                            template_key=template_key,
                            doc_type=doc_type,
                            page_number=page_num,
                            source_file=pdf_file.name
                        )
                        
                        # 메타데이터 생성
                        metadata = {
                            'source_file': pdf_file.name,
                            'source_id': f'publish/{pdf_file.name}#page_{page_num}',
                            'document_type': doc_type,
                            'page_number': page_num,
                            'total_pages': total_pages,
                            'char_count': len(page_text),
                            'word_count': len(page_text.split()),
                            'domain': 'publish',
                            'template_applied': template_key,
                            'cache_ttl': 2592000,  # 30일 TTL
                            'processing_date': datetime.now().isoformat(),
                            'chunk_type': 'document_page',
                            # ✅ context 길이 제한 로직을 적용한 content 필드
                            'content': truncated_content
                        }
                        
                        chunk = TextChunk(
                            text=formatted_content,
                            source_id=metadata['source_id'],
                            metadata=metadata
                        )
                        
                        chunks.append(chunk)
                        
                    except Exception as e:
                        logger.error(f"페이지 {page_num} 처리 실패: {e}")
                        continue
            
            logger.info(f"✅ {pdf_file.name} 처리 완료: {len(chunks)}개 청크 생성")
            
        except Exception as e:
            logger.error(f"❌ PDF 파일 처리 실패 ({pdf_file}): {e}")
        
        return chunks
    
    def _apply_template(self, content: str, template_key: str, doc_type: str, page_number: int, source_file: str) -> str:
        """발행물별 템플릿 적용"""
        try:
            template = self.templates.get(template_key, self.templates["default"])
            
            # 템플릿 변수 매핑
            template_vars = {
                'document_type': doc_type,
                'document_name': source_file,
                'page_number': page_number,
                'content': content,
                'source_file': source_file,
                'generation_date': datetime.now().strftime('%Y-%m-%d')
            }
            
            return template.format(**template_vars)
            
        except Exception as e:
            logger.error(f"템플릿 적용 실패 (page {page_number}): {e}")
            # 폴백: 기본 형식으로 반환
            return f"[{doc_type}] 페이지 {page_number}\n\n{content}\n\n[출처: {source_file}]"
    
    def _get_plan_template(self) -> str:
        """2025 교육훈련계획서 전용 템플릿"""
        return """
[2025 교육훈련계획서] 페이지 {page_number}

{content}

[문서 정보]
- 문서유형: {document_type}
- 페이지: {page_number}
- 생성일: {generation_date}

[검색 최적화]
이 내용은 경상남도인재개발원의 2025년 교육훈련계획서에서 발췌된 공식 문서로,
교육과정 운영계획, 교육목표, 추진전략, 예산계획 등 교육훈련 전반에 관한 정보를 담고 있습니다.

[출처]
파일: {source_file} (페이지 {page_number})
""".strip()
    
    def _get_evaluation_template(self) -> str:
        """2024 종합평가서 전용 템플릿"""
        return """
[2024 종합평가서] 페이지 {page_number}

{content}

[문서 정보]
- 문서유형: {document_type}
- 페이지: {page_number}
- 생성일: {generation_date}

[검색 최적화]
이 내용은 경상남도인재개발원의 2024년 종합평가서에서 발췌된 공식 문서로,
교육과정 운영성과, 만족도 분석, 교육효과 평가, 개선방안 등 교육성과에 관한 정보를 담고 있습니다.

[출처]
파일: {source_file} (페이지 {page_number})
""".strip()
    
    def _get_default_template(self) -> str:
        """기본 발행물 템플릿"""
        return """
[발행물 문서] 페이지 {page_number}

{content}

[문서 정보]
- 문서유형: {document_type}
- 문서명: {document_name}
- 페이지: {page_number}
- 생성일: {generation_date}

[검색 최적화]
이 내용은 경상남도인재개발원의 공식 발행물에서 발췌된 것으로,
교육훈련 관련 정책, 계획, 성과, 운영방안 등과 관련된 정보를 담고 있습니다.

[출처]
파일: {source_file} (페이지 {page_number})
""".strip()


# ================================================================
# 개발/테스트용 진입점
# ================================================================

def main():
    """개발/테스트용 진입점"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    loader = PublishLoader()
    
    try:
        # BaseLoader의 표준 인터페이스 사용
        success = loader.build_vectorstore()
        
        if success:
            logger.info("✅ 발행물 벡터스토어 구축 완료")
        else:
            logger.error("❌ 발행물 벡터스토어 구축 실패")
            
    except Exception as e:
        logger.error(f"❌ 로더 실행 실패: {e}")
        raise


if __name__ == '__main__':
    main()
