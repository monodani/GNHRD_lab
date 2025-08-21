#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 만족도 벡터스토어 로더

교육과정/교과목 만족도 CSV → FAISS 벡터스토어 생성
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

# =============================================================================
# 🔧 파인튜닝 설정
# =============================================================================

# 경로 설정
SOURCE_DIR = "data/satisfaction"
VECTORSTORE_DIR = "vectorstores/vectorstore_unified_satisfaction"
INDEX_NAME = "satisfaction_index"

# 파일 설정
COURSE_CSV = "course_satisfaction.csv"
SUBJECT_CSV = "subject_satisfaction.csv"
CSV_ENCODINGS = ['utf-8', 'cp949', 'euc-kr']

# 필수 필드
COURSE_FIELDS = ['교육과정', '교육과정_기수', '전반만족도']
SUBJECT_FIELDS = ['교육과정', '교과목(강의)', '강의만족도']

# 템플릿 (기존 검증된 로직 보존)
COURSE_TEMPLATE = (
    "{교육주차}에 개설된 '제{교육과정_기수}기 {교육과정}'은(는) '{교육과정_유형}'으로 분류되는 교육과정으로 "
    "{교육일자} {교육장소}에서 진행되었으며, 교육인원은 총 {교육인원}명이었습니다. "
    "'제{교육과정_기수}기 {교육과정}' 교육생의 교육에 대한 '전반적인 만족도'는 {전반만족도}점, "
    "교육효과 체감도 지표인 '역량향상도' 점수는 {역량향상도}점, '현업적용도'는 {현업적용도}점이었습니다. "
    "또한, '교과편성 만족도' {교과편성_만족도}점, '제{교육과정_기수}기 {교육과정}' 전체 강의에 대한 '강의만족도' 평균은 {교육과정별_강의만족도_평균}점이었으며, "
    "'제{교육과정_기수}기 {교육과정}'에 대한 모든 만족도 지표 평균인 '제{교육과정_기수}기 {교육과정}'의 '종합만족도'는 {종합만족도}점으로 "
    "'{교육연도}년' 전체 교육과정 중 '{교육과정_순위}위'를 기록했습니다."
)

SUBJECT_TEMPLATE = (
    "{교육주차}에 개설된 '제{교육과정_기수}기 {교육과정}'의 '{교과목(강의)}' 교과목(강의)에 대한 "
    "'강의만족도'는 {강의만족도}점으로 '{교육연도}년' 운영된 전체 교과목(강의) 중 '{교과목(강의)_순위}위'를 기록했습니다."
)

# =============================================================================

logger = logging.getLogger(__name__)


class TextChunk:
    def __init__(self, text: str, source_id: str, metadata: Dict[str, Any] = None):
        self.text = text
        self.source_id = source_id
        self.metadata = metadata or {}


class SatisfactionLoader:
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
        
        logger.info(f"SatisfactionLoader 초기화: {EMBEDDING_MODEL}")
    
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
        """CSV 파일들 처리"""
        chunks = []
        
        # 교육과정 만족도 처리
        course_file = self.source_dir / COURSE_CSV
        if course_file.exists():
            df = self._read_csv(course_file)
            for idx, row in df.iterrows():
                chunk = self._create_course_chunk(row, idx)
                if chunk:
                    chunks.append(chunk)
        
        # 교과목 만족도 처리
        subject_file = self.source_dir / SUBJECT_CSV
        if subject_file.exists():
            df = self._read_csv(subject_file)
            for idx, row in df.iterrows():
                chunk = self._create_subject_chunk(row, idx)
                if chunk:
                    chunks.append(chunk)
        
        if not chunks:
            raise ValueError("처리할 데이터가 없습니다")
        
        logger.info(f"데이터 처리 완료: {len(chunks)}개 청크")
        return chunks
    
    def _read_csv(self, file_path: Path) -> pd.DataFrame:
        """CSV 파일 읽기"""
        for encoding in CSV_ENCODINGS:
            try:
                return pd.read_csv(file_path, encoding=encoding)
            except UnicodeDecodeError:
                continue
        raise ValueError(f"CSV 읽기 실패: {file_path}")
    
    def _create_course_chunk(self, row: pd.Series, idx: int) -> TextChunk:
        """교육과정 만족도 청크 생성"""
        data = row.to_dict()
        
        # 필수 필드 확인
        for field in COURSE_FIELDS:
            if pd.isna(data.get(field)):
                logger.warning(f"교육과정 행 {idx}: {field} 누락")
                return None
        
        # 데이터 정제
        clean_data = {k: str(v).strip() if not pd.isna(v) else '' for k, v in data.items()}
        
        # 템플릿 적용
        try:
            content = COURSE_TEMPLATE.format(**clean_data)
        except KeyError as e:
            logger.error(f"교육과정 템플릿 오류 (행 {idx}): {e}")
            return None
        
        # 메타데이터
        metadata = {
            'source_file': COURSE_CSV,
            'source_id': f'satisfaction/{COURSE_CSV}#row_{idx}',
            'satisfaction_type': 'course',
            'education_course': clean_data.get('교육과정', ''),
            'course_session': clean_data.get('교육과정_기수', ''),
            'education_year': clean_data.get('교육연도', ''),
            'overall_satisfaction': self._to_float(clean_data.get('전반만족도')),
            'comprehensive_satisfaction': self._to_float(clean_data.get('종합만족도')),
            'course_ranking': self._to_int(clean_data.get('교육과정_순위')),
            'processing_date': datetime.now().isoformat()
        }
        
        return TextChunk(content, metadata['source_id'], metadata)
    
    def _create_subject_chunk(self, row: pd.Series, idx: int) -> TextChunk:
        """교과목 만족도 청크 생성"""
        data = row.to_dict()
        
        # 필수 필드 확인
        for field in SUBJECT_FIELDS:
            if pd.isna(data.get(field)):
                logger.warning(f"교과목 행 {idx}: {field} 누락")
                return None
        
        # 데이터 정제
        clean_data = {k: str(v).strip() if not pd.isna(v) else '' for k, v in data.items()}
        
        # 템플릿 적용
        try:
            content = SUBJECT_TEMPLATE.format(**clean_data)
        except KeyError as e:
            logger.error(f"교과목 템플릿 오류 (행 {idx}): {e}")
            return None
        
        # 메타데이터
        metadata = {
            'source_file': SUBJECT_CSV,
            'source_id': f'satisfaction/{SUBJECT_CSV}#row_{idx}',
            'satisfaction_type': 'subject',
            'education_course': clean_data.get('교육과정', ''),
            'course_session': clean_data.get('교육과정_기수', ''),
            'subject_name': clean_data.get('교과목(강의)', ''),
            'education_year': clean_data.get('교육연도', ''),
            'lecture_satisfaction': self._to_float(clean_data.get('강의만족도')),
            'subject_ranking': self._to_int(clean_data.get('교과목(강의)_순위')),
            'processing_date': datetime.now().isoformat()
        }
        
        return TextChunk(content, metadata['source_id'], metadata)
    
    def _to_float(self, value) -> float:
        """안전한 float 변환"""
        try:
            return float(str(value).strip()) if not pd.isna(value) else 0.0
        except:
            return 0.0
    
    def _to_int(self, value) -> int:
        """안전한 int 변환"""
        try:
            return int(float(str(value).strip())) if not pd.isna(value) else 0
        except:
            return 0
    
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
        
        for filename in [COURSE_CSV, SUBJECT_CSV]:
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
        loader = SatisfactionLoader()
        loader.build_vectorstore()
        print("✅ 만족도 벡터스토어 구축 완료")
    except Exception as e:
        print(f"❌ 실패: {e}")
        exit(1)


if __name__ == '__main__':
    main()
