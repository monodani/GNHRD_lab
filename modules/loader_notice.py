#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 공지사항 벡터스토어 로더 v4.1

notice.txt 파일 파싱 → 공지사항별 스마트 청크 생성 → FAISS 벡터스토어
"""

import os
import re
import logging
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from config.config import EMBEDDING_MODEL
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

# =============================================================================
# 🔧 파인튜닝 설정 구역 - 모든 설정값을 여기서 조정
# =============================================================================

# 경로 설정
SOURCE_DIR = "data/notice"
VECTORSTORE_DIR = "vectorstores/vectorstore_notice"
INDEX_NAME = "notice_index"

# 파일 설정
NOTICE_FILE = "notice.txt"
SECTION_DELIMITER = "---"

# 파싱 설정
MAX_TITLE_LENGTH = 50
MAX_CONTENT_LENGTH = 200  # Citation 모델 호환성
CACHE_TTL_HOURS = 6

# 공지사항 타입 분류 키워드 (우선순위 순)
NOTICE_TYPE_KEYWORDS = {
    "evaluation": ["평가", "과제", "제출기한", "마감일", "점수", "채점"],
    "enrollment": ["입교", "교육생", "준비물", "체크리스트", "지참", "입소"],
    "recruitment": ["모집", "신청", "접수", "선발", "모집공고"],
    "schedule": ["일정", "시간표", "변경", "연기", "취소"],
    "urgent": ["긴급", "즉시", "반드시", "중요", "주의", "필수"],
    "general": ["공지", "안내", "알림", "공고"]
}

# 중요도 추출 키워드
IMPORTANCE_KEYWORDS = {
    "urgent": ["긴급", "즉시", "반드시", "중요"],
    "deadline": ["마감", "기한", "제출", "감점"],
    "normal": ["안내", "공지", "알림"]
}

# 청크 생성 템플릿 (기존 로직 보존)
NOTICE_TEMPLATE = """[{title}] {notice_type} 공지사항

{content}

유형: {notice_type}
중요도: {importance}
처리일: {date}

#공지사항 #경남인재개발원 #{notice_type}"""

# =============================================================================

logger = logging.getLogger(__name__)


class TextChunk:
    def __init__(self, text: str, source_id: str, metadata: Dict[str, Any] = None):
        self.text = text
        self.source_id = source_id
        self.metadata = metadata or {}


class NoticeLoader:
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
        
        logger.info(f"NoticeLoader 초기화: {EMBEDDING_MODEL}")
    
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
        """notice.txt 파일 처리"""
        notice_file = self.source_dir / NOTICE_FILE
        
        if not notice_file.exists():
            raise ValueError(f"공지사항 파일 없음: {notice_file}")
        
        chunks = []
        
        try:
            # 파일 읽기
            with open(notice_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 섹션별 분할
            sections = [s.strip() for s in content.split(SECTION_DELIMITER) if s.strip()]
            
            for idx, section in enumerate(sections, 1):
                chunk = self._create_notice_chunk(section, idx)
                if chunk:
                    chunks.append(chunk)
            
            if not chunks:
                raise ValueError("처리할 공지사항이 없습니다")
            
            logger.info(f"공지사항 처리 완료: {len(chunks)}개 청크")
            
        except Exception as e:
            logger.error(f"공지사항 파일 처리 실패: {e}")
            raise
        
        return chunks
    
    def _create_notice_chunk(self, section: str, notice_number: int) -> TextChunk:
        """개별 공지사항 청크 생성"""
        # 제목 추출
        title = self._extract_title(section)
        
        # 타입 분류
        notice_type = self._classify_notice_type(title, section)
        
        # 중요도 추출
        importance = self._extract_importance(title, section)
        
        # 내용 정제 (Citation 모델 호환성)
        content = section[:MAX_CONTENT_LENGTH] + "..." if len(section) > MAX_CONTENT_LENGTH else section
        
        # 템플릿 적용
        text = NOTICE_TEMPLATE.format(
            title=title,
            notice_type=notice_type,
            content=content.strip(),
            importance=importance,
            date=datetime.now().strftime("%Y-%m-%d")
        )
        
        # 메타데이터
        metadata = {
            'source_file': NOTICE_FILE,
            'notice_number': notice_number,
            'notice_title': title,
            'notice_type': notice_type,
            'importance': importance,
            'cache_ttl': CACHE_TTL_HOURS * 3600,
            'processing_date': datetime.now().isoformat(),
            'content': content,  # Citation 모델용
            'chunk_type': 'notice'
        }
        
        source_id = f'notice/{NOTICE_FILE}#section_{notice_number}'
        return TextChunk(text, source_id, metadata)
    
    def _extract_title(self, text: str) -> str:
        """제목 추출 (다양한 패턴 지원)"""
        lines = text.strip().split('\n')
        if not lines:
            return "제목 없음"
        
        first_line = lines[0].strip()
        
        # 대괄호 패턴 우선 추출
        bracket_match = re.search(r'\[(.*?)\]', first_line)
        if bracket_match:
            title = bracket_match.group(1).strip()
            return title[:MAX_TITLE_LENGTH] if len(title) > MAX_TITLE_LENGTH else title
        
        # 첫 번째 줄을 제목으로 사용
        title = first_line[:MAX_TITLE_LENGTH] if len(first_line) > MAX_TITLE_LENGTH else first_line
        return title if title else "제목 없음"
    
    def _classify_notice_type(self, title: str, content: str) -> str:
        """공지사항 타입 분류 (키워드 기반)"""
        combined_text = (title + " " + content).lower()
        
        # 우선순위 순으로 검사
        for notice_type, keywords in NOTICE_TYPE_KEYWORDS.items():
            if any(keyword.lower() in combined_text for keyword in keywords):
                return notice_type
        
        return "general"  # 기본값
    
    def _extract_importance(self, title: str, content: str) -> str:
        """중요도 추출"""
        combined_text = (title + " " + content).lower()
        
        # 긴급도 순으로 검사
        for importance, keywords in IMPORTANCE_KEYWORDS.items():
            if any(keyword.lower() in combined_text for keyword in keywords):
                return importance
        
        return "normal"  # 기본값
    
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
        
        notice_file = self.source_dir / NOTICE_FILE
        if notice_file.exists():
            hasher.update(str(notice_file.stat().st_mtime).encode())
            hasher.update(str(notice_file.stat().st_size).encode())
        
        return hasher.hexdigest()[:16]
    
    def _save_hash(self):
        """현재 해시 저장"""
        hash_file = self.vectorstore_dir / ".source_hash"
        with open(hash_file, 'w') as f:
            f.write(self._calculate_hash())


def main():
    """개발/테스트용 진입점"""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    try:
        loader = NoticeLoader()
        loader.build_vectorstore()
        print("✅ 공지사항 벡터스토어 구축 완료")
    except Exception as e:
        print(f"❌ 실패: {e}")
        exit(1)


if __name__ == '__main__':
    main()
