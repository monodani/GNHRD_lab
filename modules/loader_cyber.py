#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 사이버 교육 로더 (BaseLoader 패턴 준수)

notice 로더 패턴을 따라 완전히 수정됨:
- process_domain_data(self) 시그니처로 변경
- 원본 CSV 파일 직접 읽기 로직 추가
- BaseLoader 표준 패턴 완전 준수
- 기존 템플릿 시스템 유지
"""

import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# 프로젝트 모듈 임포트
from modules.base_loader import BaseLoader
from utils.textifier import TextChunk
from config.config import config

# 로깅 설정
logger = logging.getLogger(__name__)


class CyberLoader(BaseLoader):
    """
    사이버 교육 로더 - BaseLoader 표준 패턴 준수
    
    처리 대상:
    - data/cyber/mingan.csv (민간위탁 사이버교육)
    - data/cyber/nara.csv (나라배움터 사이버교육)
    
    특징:
    - notice 로더와 동일한 process_domain_data(self) 시그니처
    - 원본 CSV 파일 직접 읽기
    - 기존 템플릿 시스템 완벽 보존
    - 해시 기반 증분 빌드 지원
    """
    
    # 기존 템플릿 보존 (검증된 코랩 로직)
    MINGAN_TEMPLATE = """'{교육과정}' 과정은, 2025년 경상남도인재개발원에서 운영하고 있는 민간위탁 사이버교육 과정 중 하나로, {개발연도}년 {개발월}월에 만들어진 교육 콘텐츠로 내용 분류상 {구분}>{대분류}>{중분류}>{소분류}>{세분류}에 해당되고, 학습시간은 {학습시간}시간이며, 학습에 대한 교육 인정시간은 {인정시간}시간입니다.
---
"""

    NARA_TEMPLATE = """'{교육과정}' 과정은, 2025년 경상남도인재개발원 나라배움터에서 운영하는 공동활용 나라콘텐츠를 활용한 교육과정으로, 내용 분류상 {분류}에 해당되며, 학습시간은 {학습차시}이고 학습에 대한 교육 인정시간은 {인정시간}입니다. 참고사항으로, 본 과정은 교육 말미에 진행되는 별도의 평가가 {평가유무}.
---
"""
    
    def __init__(self):
        super().__init__(
            domain="cyber",
            source_dir=config.ROOT_DIR / "data" / "cyber",
            vectorstore_dir=config.ROOT_DIR / "vectorstores" / "vectorstore_cyber",
            index_name="cyber_index"
        )
        
        # 처리할 파일 정의
        self.mingan_file = self.source_dir / "mingan.csv"
        self.nara_file = self.source_dir / "nara.csv"
    
    def process_domain_data(self) -> List[TextChunk]:
        """
        BaseLoader 인터페이스 구현: 사이버 교육 데이터 처리
        
        ✅ notice 로더와 동일한 시그니처: process_domain_data(self)
        """
        all_chunks = []
        
        # 1. 민간위탁 사이버교육 처리
        mingan_chunks = self._process_mingan_csv()
        all_chunks.extend(mingan_chunks)
        
        # 2. 나라배움터 사이버교육 처리
        nara_chunks = self._process_nara_csv()
        all_chunks.extend(nara_chunks)
        
        logger.info(f"✅ 사이버 교육 통합 처리 완료: 민간 {len(mingan_chunks)}개 + 나라 {len(nara_chunks)}개 = 총 {len(all_chunks)}개 청크")
        
        return all_chunks
    
    def _process_mingan_csv(self) -> List[TextChunk]:
        """민간위탁 사이버교육 CSV 직접 읽기 및 처리"""
        chunks = []
        
        if not self.mingan_file.exists():
            logger.warning(f"민간위탁 사이버교육 파일이 없습니다: {self.mingan_file}")
            return chunks
        
        try:
            logger.info(f"🏢 민간위탁 사이버교육 처리 시작: {self.mingan_file}")
            
            # CSV 직접 읽기
            df = self._read_csv_with_encoding(self.mingan_file)
            
            if df is None:
                return chunks
            
            logger.info(f"📄 민간위탁 데이터: {len(df)}행 로드됨")
            
            # 각 행을 기존 템플릿으로 변환
            for idx, row in df.iterrows():
                try:
                    # 데이터 검증 및 정제
                    clean_data = self._validate_and_clean_mingan_data(row.to_dict(), f"mingan_row_{idx}")
                    if not clean_data:
                        continue
                    
                    # 기존 템플릿 적용
                    try:
                        formatted_content = self.MINGAN_TEMPLATE.format(**clean_data)
                    except KeyError as e:
                        logger.error(f"민간위탁 템플릿 적용 실패 (행 {idx}): 누락 필드 {e}")
                        continue
                    
                    # 메타데이터 생성
                    metadata = {
                        'source_file': 'mingan.csv',
                        'source_id': f'cyber/mingan.csv#row_{idx}',
                        'cyber_type': 'mingan',
                        'education_course': clean_data.get('교육과정', ''),
                        'development_year': str(clean_data.get('개발연도', '')),
                        'development_month': str(clean_data.get('개발월', '')),
                        'category_path': f"{clean_data.get('구분', '')}>{clean_data.get('대분류', '')}>{clean_data.get('중분류', '')}>{clean_data.get('소분류', '')}>{clean_data.get('세분류', '')}",
                        'learning_hours': self._safe_convert_to_float(clean_data.get('학습시간', '')),
                        'recognition_hours': self._safe_convert_to_float(clean_data.get('인정시간', '')),
                        'cache_ttl': 2592000,  # 30일 TTL
                        'processing_date': datetime.now().isoformat(),
                        'chunk_type': 'cyber_mingan'
                    }
                    
                    chunk = TextChunk(
                        text=formatted_content,
                        source_id=metadata['source_id'],
                        metadata=metadata
                    )
                    
                    chunks.append(chunk)
                    
                except Exception as e:
                    logger.error(f"민간위탁 행 {idx} 처리 실패: {e}")
                    continue
            
            logger.info(f"✅ 민간위탁 사이버교육 처리 완료: {len(chunks)}개 청크 생성")
            
        except Exception as e:
            logger.error(f"❌ 민간위탁 사이버교육 파일 처리 실패: {e}")
        
        return chunks
    
    def _process_nara_csv(self) -> List[TextChunk]:
        """나라배움터 사이버교육 CSV 직접 읽기 및 처리"""
        chunks = []
        
        if not self.nara_file.exists():
            logger.warning(f"나라배움터 사이버교육 파일이 없습니다: {self.nara_file}")
            return chunks
        
        try:
            logger.info(f"🏛️ 나라배움터 사이버교육 처리 시작: {self.nara_file}")
            
            # CSV 직접 읽기
            df = self._read_csv_with_encoding(self.nara_file)
            
            if df is None:
                return chunks
            
            logger.info(f"📄 나라배움터 데이터: {len(df)}행 로드됨")
            
            # 각 행을 기존 템플릿으로 변환
            for idx, row in df.iterrows():
                try:
                    # 데이터 검증 및 정제
                    clean_data = self._validate_and_clean_nara_data(row.to_dict(), f"nara_row_{idx}")
                    if not clean_data:
                        continue
                    
                    # 기존 템플릿 적용
                    try:
                        formatted_content = self.NARA_TEMPLATE.format(**clean_data)
                    except KeyError as e:
                        logger.error(f"나라배움터 템플릿 적용 실패 (행 {idx}): 누락 필드 {e}")
                        continue
                    
                    # 메타데이터 생성
                    metadata = {
                        'source_file': 'nara.csv',
                        'source_id': f'cyber/nara.csv#row_{idx}',
                        'cyber_type': 'nara',
                        'education_course': clean_data.get('교육과정', ''),
                        'classification': clean_data.get('분류', ''),
                        'learning_sessions': str(clean_data.get('학습차시', '')),
                        'recognition_hours': self._safe_convert_to_float(clean_data.get('인정시간', '')),
                        'evaluation_required': clean_data.get('평가유무', ''),
                        'cache_ttl': 2592000,  # 30일 TTL
                        'processing_date': datetime.now().isoformat(),
                        'chunk_type': 'cyber_nara'
                    }
                    
                    chunk = TextChunk(
                        text=formatted_content,
                        source_id=metadata['source_id'],
                        metadata=metadata
                    )
                    
                    chunks.append(chunk)
                    
                except Exception as e:
                    logger.error(f"나라배움터 행 {idx} 처리 실패: {e}")
                    continue
            
            logger.info(f"✅ 나라배움터 사이버교육 처리 완료: {len(chunks)}개 청크 생성")
            
        except Exception as e:
            logger.error(f"❌ 나라배움터 사이버교육 파일 처리 실패: {e}")
        
        return chunks
    
    def _read_csv_with_encoding(self, csv_file: Path) -> Optional[pd.DataFrame]:
        """인코딩 자동 감지로 CSV 읽기"""
        encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig']
        
        for encoding in encodings:
            try:
                df = pd.read_csv(csv_file, encoding=encoding)
                logger.info(f"CSV 파일 로드 성공 (인코딩: {encoding})")
                return df
                
            except UnicodeDecodeError:
                logger.debug(f"인코딩 {encoding} 실패, 다음 시도...")
                continue
            except Exception as e:
                logger.error(f"CSV 파일 읽기 실패 (인코딩: {encoding}): {e}")
                continue
        
        logger.error(f"모든 인코딩 시도 실패: {csv_file}")
        return None
    
    def _validate_and_clean_mingan_data(self, row_data: Dict[str, Any], source_id: str) -> Optional[Dict[str, str]]:
        """민간위탁 데이터 검증 및 정제"""
        try:
            # 필수 필드 확인
            required_fields = ['교육과정', '개발연도', '학습시간', '인정시간']
            for field in required_fields:
                if field not in row_data or pd.isna(row_data[field]):
                    logger.warning(f"민간위탁 필수 필드 누락 ({source_id}): {field}")
                    return None
            
            # 데이터 정제
            clean_data = {}
            for key, value in row_data.items():
                if pd.isna(value):
                    clean_data[key] = ''
                else:
                    clean_data[key] = str(value).strip()
            
            return clean_data
            
        except Exception as e:
            logger.error(f"민간위탁 데이터 검증 실패 ({source_id}): {e}")
            return None
    
    def _validate_and_clean_nara_data(self, row_data: Dict[str, Any], source_id: str) -> Optional[Dict[str, str]]:
        """나라배움터 데이터 검증 및 정제"""
        try:
            # 필수 필드 확인
            required_fields = ['교육과정', '분류', '학습차시', '인정시간']
            for field in required_fields:
                if field not in row_data or pd.isna(row_data[field]):
                    logger.warning(f"나라배움터 필수 필드 누락 ({source_id}): {field}")
                    return None
            
            # 데이터 정제
            clean_data = {}
            for key, value in row_data.items():
                if pd.isna(value):
                    clean_data[key] = ''
                else:
                    clean_data[key] = str(value).strip()
            
            return clean_data
            
        except Exception as e:
            logger.error(f"나라배움터 데이터 검증 실패 ({source_id}): {e}")
            return None
    
    def _safe_convert_to_float(self, value: Any) -> float:
        """안전한 float 변환"""
        try:
            if pd.isna(value) or value == '':
                return 0.0
            return float(str(value).strip())
        except (ValueError, TypeError):
            return 0.0


# ================================================================
# 개발/테스트용 진입점
# ================================================================

def main():
    """개발/테스트용 진입점"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    loader = CyberLoader()
    
    try:
        # BaseLoader의 표준 인터페이스 사용
        success = loader.build_vectorstore()
        
        if success:
            logger.info("✅ 사이버 교육 벡터스토어 구축 완료")
        else:
            logger.error("❌ 사이버 교육 벡터스토어 구축 실패")
            
    except Exception as e:
        logger.error(f"❌ 로더 실행 실패: {e}")
        raise


if __name__ == '__main__':
    main()
