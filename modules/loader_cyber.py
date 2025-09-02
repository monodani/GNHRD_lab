# #!/usr/bin/env python3
# """
# 경상남도인재개발원 RAG 챗봇 - 사이버 교육 벡터스토어 로더

# 민간위탁/나라배움터 사이버교육 CSV → FAISS 벡터스토어 생성
# """

# import os
# import logging
# import pandas as pd
# import hashlib
# import time
# from pathlib import Path
# from typing import List, Dict, Any
# from datetime import datetime

# from config.config import EMBEDDING_MODEL
# from langchain_community.vectorstores import FAISS
# from langchain_openai import OpenAIEmbeddings

# # =============================================================================
# # 🔧 파인튜닝 설정
# # =============================================================================

# # 경로 설정
# SOURCE_DIR = "data/cyber"
# VECTORSTORE_DIR = "vectorstores/vectorstore_cyber"
# INDEX_NAME = "cyber_index"

# # 파일 설정
# MINGAN_FILE = "mingan.csv"
# NARA_FILE = "nara.csv"
# CSV_ENCODINGS = ['utf-8', 'cp949', 'euc-kr']

# # 필수 필드
# MINGAN_FIELDS = ['교육과정', '개발연도', '학습시간', '인정시간']
# NARA_FIELDS = ['교육과정', '분류', '학습차시', '인정시간']

# # 템플릿
# MINGAN_TEMPLATE = """'{교육과정}' 과정은, 2025년 경상남도인재개발원에서 운영하고 있는 민간위탁 사이버교육 과정 중 하나로, {개발연도}년 {개발월}월에 만들어진 교육 콘텐츠로 내용 분류상 {구분}>{대분류}>{중분류}>{소분류}>{세분류}에 해당되고, 학습시간은 {학습시간}시간이며, 학습에 대한 교육 인정시간은 {인정시간}시간입니다.
# ---
# """

# NARA_TEMPLATE = """'{교육과정}' 과정은, 2025년 경상남도인재개발원 나라배움터에서 운영하는 공동활용 나라콘텐츠를 활용한 교육과정으로, 내용 분류상 {분류}에 해당되며, 학습시간은 {학습차시}이고 학습에 대한 교육 인정시간은 {인정시간}입니다. 참고사항으로, 본 과정은 교육 말미에 진행되는 별도의 평가가 {평가유무}.
# ---
# """

# # =============================================================================

# logger = logging.getLogger(__name__)


# class TextChunk:
#     def __init__(self, text: str, source_id: str, metadata: Dict[str, Any] = None):
#         self.text = text
#         self.source_id = source_id
#         self.metadata = metadata or {}


# class CyberLoader:
#     def __init__(self):
#         # API 키 및 임베딩
#         self.api_key = os.getenv("OPENAI_API_KEY")
#         if not self.api_key:
#             raise ValueError("OPENAI_API_KEY 환경변수가 필요합니다")
        
#         self.embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=self.api_key)
        
#         # 경로 설정
#         root = Path(__file__).parent.parent
#         self.source_dir = root / SOURCE_DIR
#         self.vectorstore_dir = root / VECTORSTORE_DIR
#         self.vectorstore_dir.mkdir(parents=True, exist_ok=True)
        
#         logger.info(f"CyberLoader 초기화: {EMBEDDING_MODEL}")
    
#     def build_vectorstore(self, force_rebuild: bool = False) -> bool:
#         """벡터스토어 빌드"""
#         try:
#             if not force_rebuild and not self._needs_rebuild():
#                 logger.info("벡터스토어가 최신상태입니다")
#                 return True
            
#             logger.info("벡터스토어 빌드 시작...")
#             start_time = time.time()
            
#             # 데이터 처리
#             chunks = self._process_data()
            
#             # FAISS 생성
#             texts = [chunk.text for chunk in chunks]
#             metadatas = [chunk.metadata for chunk in chunks]
            
#             vectorstore = FAISS.from_texts(texts, self.embeddings, metadatas)
#             vectorstore.save_local(str(self.vectorstore_dir), INDEX_NAME)
            
#             # 해시 저장
#             self._save_hash()
            
#             elapsed = time.time() - start_time
#             logger.info(f"빌드 완료: {len(chunks)}개 청크, {elapsed:.1f}초")
#             return True
            
#         except Exception as e:
#             logger.error(f"빌드 실패: {e}")
#             raise
    
#     def _process_data(self) -> List[TextChunk]:
#         """CSV 파일들 처리"""
#         chunks = []
        
#         # 민간위탁 처리
#         mingan_file = self.source_dir / MINGAN_FILE
#         if mingan_file.exists():
#             df = self._read_csv(mingan_file)
#             for idx, row in df.iterrows():
#                 chunk = self._create_mingan_chunk(row, idx)
#                 if chunk:
#                     chunks.append(chunk)
        
#         # 나라배움터 처리
#         nara_file = self.source_dir / NARA_FILE
#         if nara_file.exists():
#             df = self._read_csv(nara_file)
#             for idx, row in df.iterrows():
#                 chunk = self._create_nara_chunk(row, idx)
#                 if chunk:
#                     chunks.append(chunk)
        
#         if not chunks:
#             raise ValueError("처리할 데이터가 없습니다")
        
#         logger.info(f"데이터 처리 완료: {len(chunks)}개 청크")
#         return chunks
    
#     def _read_csv(self, file_path: Path) -> pd.DataFrame:
#         """CSV 파일 읽기"""
#         for encoding in CSV_ENCODINGS:
#             try:
#                 return pd.read_csv(file_path, encoding=encoding)
#             except UnicodeDecodeError:
#                 continue
#         raise ValueError(f"CSV 읽기 실패: {file_path}")
    
#     def _create_mingan_chunk(self, row: pd.Series, idx: int) -> TextChunk:
#         """민간위탁 청크 생성"""
#         data = row.to_dict()
        
#         # 필수 필드 확인
#         for field in MINGAN_FIELDS:
#             if pd.isna(data.get(field)):
#                 logger.warning(f"민간위탁 행 {idx}: {field} 누락")
#                 return None
        
#         # 데이터 정제
#         clean_data = {k: str(v).strip() if not pd.isna(v) else '' for k, v in data.items()}
        
#         # 템플릿 적용
#         try:
#             content = MINGAN_TEMPLATE.format(**clean_data)
#         except KeyError as e:
#             logger.error(f"민간위탁 템플릿 오류 (행 {idx}): {e}")
#             return None
        
#         # 메타데이터
#         metadata = {
#             'source_file': MINGAN_FILE,
#             'source_id': f'cyber/{MINGAN_FILE}#row_{idx}',
#             'cyber_type': 'mingan',
#             'education_course': clean_data.get('교육과정', ''),
#             'learning_hours': self._to_float(clean_data.get('학습시간')),
#             'recognition_hours': self._to_float(clean_data.get('인정시간')),
#             'processing_date': datetime.now().isoformat()
#         }
        
#         return TextChunk(content, metadata['source_id'], metadata)
    
#     def _create_nara_chunk(self, row: pd.Series, idx: int) -> TextChunk:
#         """나라배움터 청크 생성"""
#         data = row.to_dict()
        
#         # 필수 필드 확인
#         for field in NARA_FIELDS:
#             if pd.isna(data.get(field)):
#                 logger.warning(f"나라배움터 행 {idx}: {field} 누락")
#                 return None
        
#         # 데이터 정제
#         clean_data = {k: str(v).strip() if not pd.isna(v) else '' for k, v in data.items()}
        
#         # 템플릿 적용
#         try:
#             content = NARA_TEMPLATE.format(**clean_data)
#         except KeyError as e:
#             logger.error(f"나라배움터 템플릿 오류 (행 {idx}): {e}")
#             return None
        
#         # 메타데이터
#         metadata = {
#             'source_file': NARA_FILE,
#             'source_id': f'cyber/{NARA_FILE}#row_{idx}',
#             'cyber_type': 'nara',
#             'education_course': clean_data.get('교육과정', ''),
#             'classification': clean_data.get('분류', ''),
#             'recognition_hours': self._to_float(clean_data.get('인정시간')),
#             'processing_date': datetime.now().isoformat()
#         }
        
#         return TextChunk(content, metadata['source_id'], metadata)
    
#     def _to_float(self, value) -> float:
#         """안전한 float 변환"""
#         try:
#             return float(str(value).strip()) if not pd.isna(value) else 0.0
#         except:
#             return 0.0
    
#     def _needs_rebuild(self) -> bool:
#         """재빌드 필요 여부"""
#         # FAISS 파일 확인
#         faiss_file = self.vectorstore_dir / f"{INDEX_NAME}.faiss"
#         pkl_file = self.vectorstore_dir / f"{INDEX_NAME}.pkl"
        
#         if not (faiss_file.exists() and pkl_file.exists()):
#             return True
        
#         # 해시 비교
#         hash_file = self.vectorstore_dir / ".source_hash"
#         if not hash_file.exists():
#             return True
        
#         current_hash = self._calculate_hash()
#         with open(hash_file, 'r') as f:
#             stored_hash = f.read().strip()
        
#         return current_hash != stored_hash
    
#     def _calculate_hash(self) -> str:
#         """소스 해시 계산"""
#         hasher = hashlib.md5()
#         hasher.update(EMBEDDING_MODEL.encode())
        
#         for filename in [MINGAN_FILE, NARA_FILE]:
#             file_path = self.source_dir / filename
#             if file_path.exists():
#                 hasher.update(str(file_path.stat().st_mtime).encode())
        
#         return hasher.hexdigest()[:16]
    
#     def _save_hash(self):
#         """현재 해시 저장"""
#         hash_file = self.vectorstore_dir / ".source_hash"
#         with open(hash_file, 'w') as f:
#             f.write(self._calculate_hash())


# def main():
#     logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
#     try:
#         loader = CyberLoader()
#         loader.build_vectorstore()
#         print("✅ 사이버 교육 벡터스토어 구축 완료")
#     except Exception as e:
#         print(f"❌ 실패: {e}")
#         exit(1)


# if __name__ == '__main__':
#     main()
