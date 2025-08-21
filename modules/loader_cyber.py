#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 사이버 교육 벡터스토어 로더 (독립형)

완전히 독립적인 벡터스토어 생성기:
- BaseLoader 의존성 완전 제거
- config.py에서 임베딩 모델만 가져오기
- API 키는 환경변수에서 직접 로드
- 기존 템플릿 시스템 완벽 보존
- 실패시 전면 중단 (안전한 에러 처리)
"""

import os
import logging
import pandas as pd
import hashlib
import time
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

# 설정 가져오기
from config.config import EMBEDDING_MODEL, EMBEDDING_DIMENSION

# 필수 라이브러리
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

# 로깅 설정
logger = logging.getLogger(__name__)


class TextChunk:
    """간단한 텍스트 청크 클래스"""
    def __init__(self, text: str, source_id: str, metadata: Dict[str, Any] = None):
        self.text = text
        self.source_id = source_id
        self.metadata = metadata or {}


class CyberLoader:
    """
    사이버 교육 벡터스토어 독립 로더
    
    처리 대상:
    - data/cyber/mingan.csv (민간위탁 사이버교육)
    - data/cyber/nara.csv (나라배움터 사이버교육)
    
    특징:
    - 완전 독립적 동작
    - 기존 템플릿 시스템 보존
    - 해시 기반 증분 빌드
    - 실패시 전면 중단
    """
    
    # 검증된 기존 템플릿 보존
    MINGAN_TEMPLATE = """'{교육과정}' 과정은, 2025년 경상남도인재개발원에서 운영하고 있는 민간위탁 사이버교육 과정 중 하나로, {개발연도}년 {개발월}월에 만들어진 교육 콘텐츠로 내용 분류상 {구분}>{대분류}>{중분류}>{소분류}>{세분류}에 해당되고, 학습시간은 {학습시간}시간이며, 학습에 대한 교육 인정시간은 {인정시간}시간입니다.
---
"""

    NARA_TEMPLATE = """'{교육과정}' 과정은, 2025년 경상남도인재개발원 나라배움터에서 운영하는 공동활용 나라콘텐츠를 활용한 교육과정으로, 내용 분류상 {분류}에 해당되며, 학습시간은 {학습차시}이고 학습에 대한 교육 인정시간은 {인정시간}입니다. 참고사항으로, 본 과정은 교육 말미에 진행되는 별도의 평가가 {평가유무}.
---
"""
    
    def __init__(self):
        """로더 초기화"""
        # API 키 직접 로드
        self.api_key = os.getenv("OPENAI_API_KEY_DEV")
        if not self.api_key:
            raise ValueError("❌ OPENAI_API_KEY_DEV 환경변수가 설정되지 않았습니다.")
        
        # 설정값
        self.embedding_model = EMBEDDING_MODEL
        self.embedding_dimension = EMBEDDING_DIMENSION
        
        # 경로 설정
        self.root_dir = Path(__file__).parent.parent
        self.source_dir = self.root_dir / "data" / "cyber"
        self.vectorstore_dir = self.root_dir / "vectorstores" / "vectorstore_cyber"
        self.index_name = "cyber_index"
        
        # 디렉터리 생성
        self.vectorstore_dir.mkdir(parents=True, exist_ok=True)
        
        # 처리할 파일
        self.mingan_file = self.source_dir / "mingan.csv"
        self.nara_file = self.source_dir / "nara.csv"
        
        # 임베딩 모델 초기화
        self.embeddings = OpenAIEmbeddings(
            model=self.embedding_model,
            api_key=self.api_key
        )
        
        logger.info(f"✅ CyberLoader 초기화 완료")
        logger.info(f"   - 임베딩 모델: {self.embedding_model} ({self.embedding_dimension}차원)")
        logger.info(f"   - 소스 디렉터리: {self.source_dir}")
        logger.info(f"   - 출력 디렉터리: {self.vectorstore_dir}")
    
    def process_data(self) -> List[TextChunk]:
        """사이버 교육 데이터 처리"""
        all_chunks = []
        
        # 1. 민간위탁 사이버교육 처리
        logger.info("🏢 민간위탁 사이버교육 처리 시작")
        mingan_chunks = self._process_mingan_csv()
        all_chunks.extend(mingan_chunks)
        
        # 2. 나라배움터 사이버교육 처리  
        logger.info("🏛️ 나라배움터 사이버교육 처리 시작")
        nara_chunks = self._process_nara_csv()
        all_chunks.extend(nara_chunks)
        
        logger.info(f"✅ 사이버 교육 데이터 처리 완료: 민간 {len(mingan_chunks)}개 + 나라 {len(nara_chunks)}개 = 총 {len(all_chunks)}개 청크")
        
        if not all_chunks:
            raise ValueError("❌ 처리된 데이터가 없습니다. 소스 파일을 확인해주세요.")
        
        return all_chunks
    
    def _process_mingan_csv(self) -> List[TextChunk]:
        """민간위탁 사이버교육 CSV 처리"""
        chunks = []
        
        if not self.mingan_file.exists():
            logger.warning(f"⚠️ 민간위탁 파일이 없습니다: {self.mingan_file}")
            return chunks
        
        try:
            # CSV 읽기
            df = self._read_csv_with_encoding(self.mingan_file)
            logger.info(f"📄 민간위탁 데이터: {len(df)}행 로드됨")
            
            # 각 행 처리
            for idx, row in df.iterrows():
                try:
                    # 데이터 검증 및 정제
                    clean_data = self._validate_and_clean_mingan_data(row.to_dict(), f"mingan_row_{idx}")
                    if not clean_data:
                        continue
                    
                    # 템플릿 적용
                    try:
                        formatted_content = self.MINGAN_TEMPLATE.format(**clean_data)
                    except KeyError as e:
                        logger.error(f"❌ 민간위탁 템플릿 적용 실패 (행 {idx}): 누락 필드 {e}")
                        raise
                    
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
                    logger.error(f"❌ 민간위탁 행 {idx} 처리 실패: {e}")
                    raise
            
            logger.info(f"✅ 민간위탁 사이버교육 처리 완료: {len(chunks)}개 청크 생성")
            
        except Exception as e:
            logger.error(f"❌ 민간위탁 사이버교육 파일 처리 실패: {e}")
            raise
        
        return chunks
    
    def _process_nara_csv(self) -> List[TextChunk]:
        """나라배움터 사이버교육 CSV 처리"""
        chunks = []
        
        if not self.nara_file.exists():
            logger.warning(f"⚠️ 나라배움터 파일이 없습니다: {self.nara_file}")
            return chunks
        
        try:
            # CSV 읽기
            df = self._read_csv_with_encoding(self.nara_file)
            logger.info(f"📄 나라배움터 데이터: {len(df)}행 로드됨")
            
            # 각 행 처리
            for idx, row in df.iterrows():
                try:
                    # 데이터 검증 및 정제
                    clean_data = self._validate_and_clean_nara_data(row.to_dict(), f"nara_row_{idx}")
                    if not clean_data:
                        continue
                    
                    # 템플릿 적용
                    try:
                        formatted_content = self.NARA_TEMPLATE.format(**clean_data)
                    except KeyError as e:
                        logger.error(f"❌ 나라배움터 템플릿 적용 실패 (행 {idx}): 누락 필드 {e}")
                        raise
                    
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
                    logger.error(f"❌ 나라배움터 행 {idx} 처리 실패: {e}")
                    raise
            
            logger.info(f"✅ 나라배움터 사이버교육 처리 완료: {len(chunks)}개 청크 생성")
            
        except Exception as e:
            logger.error(f"❌ 나라배움터 사이버교육 파일 처리 실패: {e}")
            raise
        
        return chunks
    
    def _read_csv_with_encoding(self, csv_file: Path) -> pd.DataFrame:
        """인코딩 자동 감지로 CSV 읽기"""
        encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig']
        
        for encoding in encodings:
            try:
                df = pd.read_csv(csv_file, encoding=encoding)
                logger.info(f"✅ CSV 파일 로드 성공 (인코딩: {encoding})")
                return df
                
            except UnicodeDecodeError:
                continue
            except Exception as e:
                logger.error(f"❌ CSV 파일 읽기 실패 (인코딩: {encoding}): {e}")
                continue
        
        raise ValueError(f"❌ 모든 인코딩 시도 실패: {csv_file}")
    
    def _validate_and_clean_mingan_data(self, row_data: Dict[str, Any], source_id: str) -> Optional[Dict[str, str]]:
        """민간위탁 데이터 검증 및 정제"""
        try:
            # 필수 필드 확인
            required_fields = ['교육과정', '개발연도', '학습시간', '인정시간']
            for field in required_fields:
                if field not in row_data or pd.isna(row_data[field]):
                    logger.error(f"❌ 민간위탁 필수 필드 누락 ({source_id}): {field}")
                    raise ValueError(f"필수 필드 누락: {field}")
            
            # 데이터 정제
            clean_data = {}
            for key, value in row_data.items():
                if pd.isna(value):
                    clean_data[key] = ''
                else:
                    clean_data[key] = str(value).strip()
            
            return clean_data
            
        except Exception as e:
            logger.error(f"❌ 민간위탁 데이터 검증 실패 ({source_id}): {e}")
            raise
    
    def _validate_and_clean_nara_data(self, row_data: Dict[str, Any], source_id: str) -> Optional[Dict[str, str]]:
        """나라배움터 데이터 검증 및 정제"""
        try:
            # 필수 필드 확인
            required_fields = ['교육과정', '분류', '학습차시', '인정시간']
            for field in required_fields:
                if field not in row_data or pd.isna(row_data[field]):
                    logger.error(f"❌ 나라배움터 필수 필드 누락 ({source_id}): {field}")
                    raise ValueError(f"필수 필드 누락: {field}")
            
            # 데이터 정제
            clean_data = {}
            for key, value in row_data.items():
                if pd.isna(value):
                    clean_data[key] = ''
                else:
                    clean_data[key] = str(value).strip()
            
            return clean_data
            
        except Exception as e:
            logger.error(f"❌ 나라배움터 데이터 검증 실패 ({source_id}): {e}")
            raise
    
    def _safe_convert_to_float(self, value: Any) -> float:
        """안전한 float 변환"""
        try:
            if pd.isna(value) or value == '':
                return 0.0
            return float(str(value).strip())
        except (ValueError, TypeError):
            return 0.0
    
    def calculate_source_hash(self) -> str:
        """소스 데이터 해시 계산 (증분 빌드용)"""
        try:
            hash_md5 = hashlib.md5()
            
            # 임베딩 모델도 해시에 포함
            hash_md5.update(self.embedding_model.encode())
            
            # 소스 파일들의 수정 시간 및 크기
            for file_path in [self.mingan_file, self.nara_file]:
                if file_path.exists():
                    hash_md5.update(str(file_path.stat().st_mtime).encode())
                    hash_md5.update(str(file_path.stat().st_size).encode())
            
            return hash_md5.hexdigest()[:16]
        except Exception as e:
            logger.warning(f"⚠️ 해시 계산 실패: {e}")
            return str(int(time.time()))
    
    def needs_rebuild(self) -> bool:
        """재빌드 필요 여부 확인"""
        try:
            # FAISS 파일 확인
            faiss_file = self.vectorstore_dir / f"{self.index_name}.faiss"
            pkl_file = self.vectorstore_dir / f"{self.index_name}.pkl"
            
            if not (faiss_file.exists() and pkl_file.exists()):
                logger.info("🔨 FAISS 파일이 없어서 새로 빌드")
                return True
            
            # 해시 파일 확인
            hash_file = self.vectorstore_dir / ".source_hash"
            if not hash_file.exists():
                logger.info("🔨 해시 파일이 없어서 새로 빌드")
                return True
            
            # 해시 비교
            current_hash = self.calculate_source_hash()
            with open(hash_file, 'r') as f:
                stored_hash = f.read().strip()
            
            if current_hash != stored_hash:
                logger.info("🔨 소스 데이터 변경으로 재빌드")
                return True
            
            logger.info("✅ 벡터스토어가 최신 상태")
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ 재빌드 확인 실패: {e}")
            return True
    
    def build_vectorstore(self, force_rebuild: bool = False) -> bool:
        """벡터스토어 빌드"""
        try:
            # 재빌드 필요성 확인
            if not force_rebuild and not self.needs_rebuild():
                logger.info("⏭️ 이미 최신 벡터스토어 존재")
                return True
            
            logger.info("🔨 사이버 교육 벡터스토어 빌드 시작...")
            start_time = time.time()
            
            # 1. 데이터 처리
            chunks = self.process_data()
            
            # 2. FAISS 벡터스토어 생성
            logger.info("🔄 FAISS 벡터스토어 생성 중...")
            
            texts = [chunk.text for chunk in chunks]
            metadatas = [chunk.metadata for chunk in chunks]
            
            vectorstore = FAISS.from_texts(
                texts=texts,
                embedding=self.embeddings,
                metadatas=metadatas
            )
            
            # 3. 저장
            vectorstore.save_local(
                folder_path=str(self.vectorstore_dir),
                index_name=self.index_name
            )
            
            # 4. 해시 저장
            current_hash = self.calculate_source_hash()
            hash_file = self.vectorstore_dir / ".source_hash"
            with open(hash_file, 'w') as f:
                f.write(current_hash)
            
            # 5. 생성 확인
            faiss_file = self.vectorstore_dir / f"{self.index_name}.faiss"
            pkl_file = self.vectorstore_dir / f"{self.index_name}.pkl"
            
            if faiss_file.exists() and pkl_file.exists():
                faiss_size = faiss_file.stat().st_size / (1024*1024)
                elapsed_time = time.time() - start_time
                
                logger.info(f"✅ 사이버 교육 벡터스토어 빌드 완료!")
                logger.info(f"   - 처리된 청크: {len(chunks)}개")
                logger.info(f"   - 파일 크기: {faiss_size:.1f}MB")
                logger.info(f"   - 소요 시간: {elapsed_time:.2f}초")
                
                return True
            else:
                raise ValueError("❌ 벡터스토어 파일 생성 실패")
                
        except Exception as e:
            logger.error(f"❌ 벡터스토어 빌드 실패: {e}")
            raise


def main():
    """메인 실행 함수"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        loader = CyberLoader()
        success = loader.build_vectorstore()
        
        if success:
            print("✅ 사이버 교육 벡터스토어 구축 성공!")
        else:
            print("❌ 사이버 교육 벡터스토어 구축 실패!")
            exit(1)
            
    except Exception as e:
        print(f"❌ 로더 실행 실패: {e}")
        exit(1)


if __name__ == '__main__':
    main()
