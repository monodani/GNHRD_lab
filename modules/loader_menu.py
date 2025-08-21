#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 식단표 벡터스토어 로더

ChatGPT API로 이미지 → 텍스트 변환 후 FAISS 벡터스토어 생성
"""

import os
import logging
import json
import base64
import hashlib
import time
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from config.config import EMBEDDING_MODEL
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
import requests

# =============================================================================
# 🔧 파인튜닝 설정
# =============================================================================

# 경로 설정
SOURCE_DIR = "data/menu"
VECTORSTORE_DIR = "vectorstores/vectorstore_menu"
INDEX_NAME = "menu_index"

# 파일 설정
MENU_IMAGE = "menu.png"
CACHE_FILE = "menu_cache.json"

# ChatGPT API 설정
CHATGPT_MODEL = "gpt-4o-mini"
CHATGPT_URL = "https://api.openai.com/v1/chat/completions"
MAX_TOKENS = 2000
TEMPERATURE = 0.1

# 캐시 설정
CACHE_TTL_HOURS = 6

# 프롬프트
MENU_EXTRACTION_PROMPT = """
다음은 경상남도인재개발원의 주간 식단표 이미지입니다.
이 이미지를 분석하여 요일별, 식사별로 메뉴를 정확히 추출해주세요.

출력 형식은 반드시 다음 JSON 구조를 따라주세요:
{
    "월요일": {
        "조식": ["메뉴1", "메뉴2"],
        "중식": ["메뉴1", "메뉴2"], 
        "석식": ["메뉴1", "메뉴2"]
    },
    "화요일": { ... },
    "수요일": { ... },
    "목요일": { ... },
    "금요일": { ... }
}

주의사항:
1. 메뉴명은 정확히 추출(애매/모호한 데이터가 추출될 시 해당 데이터 기준 가장 확률 높은 메뉴명 추정하여 출력)
2. 빈 항목은 빈 배열 []로 표시
3. JSON 형식만 응답하고 다른 설명 없이
4. 금요일 석식은 "경제 활성화의 날"로 무조건 출력
"""

# 템플릿
MENU_TEMPLATE = """{day} {meal_type}

메뉴: {menu_items}

#식단 #경남인재개발원 #{day} #{meal_type}"""

# =============================================================================

logger = logging.getLogger(__name__)


class TextChunk:
    def __init__(self, text: str, source_id: str, metadata: Dict[str, Any] = None):
        self.text = text
        self.source_id = source_id
        self.metadata = metadata or {}


class MenuLoader:
    def __init__(self):
        # API 키 및 임베딩
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 필요합니다")
        
        self.embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL, api_key=self.api_key)
        
        # 경로 설정
        root = Path(__file__).parent.parent
        self.source_dir = root / SOURCE_DIR
        self.vectorstore_dir = root / VECTORSTORE_DIR
        self.vectorstore_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"MenuLoader 초기화: {EMBEDDING_MODEL}")
    
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
        """이미지 처리 및 청크 생성"""
        image_file = self.source_dir / MENU_IMAGE
        
        if not image_file.exists():
            raise ValueError(f"식단표 이미지 없음: {image_file}")
        
        # 캐시 확인 또는 새로 추출
        menu_data = self._get_menu_data(image_file)
        
        # 청크 생성
        chunks = self._create_chunks(menu_data)
        
        if not chunks:
            raise ValueError("처리할 데이터가 없습니다")
        
        logger.info(f"데이터 처리 완료: {len(chunks)}개 청크")
        return chunks
    
    def _get_menu_data(self, image_file: Path) -> Dict[str, Any]:
        """캐시 확인 후 필요시 ChatGPT API 호출"""
        cache_file = self.source_dir / CACHE_FILE
        
        # 캐시 유효성 확인
        if self._is_cache_valid(cache_file, image_file):
            logger.info("캐시된 식단 데이터 사용")
            return self._load_cache(cache_file)
        
        # 새로 추출
        logger.info("ChatGPT API로 식단 추출")
        menu_data = self._extract_menu_from_image(image_file)
        
        # 캐시 저장
        self._save_cache(cache_file, menu_data)
        
        return menu_data
    
    def _is_cache_valid(self, cache_file: Path, image_file: Path) -> bool:
        """캐시 유효성 확인"""
        if not cache_file.exists():
            return False
        
        try:
            cache_time = cache_file.stat().st_mtime
            image_time = image_file.stat().st_mtime
            current_time = time.time()
            
            # 이미지가 더 최신이면 무효
            if image_time > cache_time:
                return False
            
            # TTL 확인
            ttl_seconds = CACHE_TTL_HOURS * 3600
            if current_time - cache_time > ttl_seconds:
                return False
            
            return True
        except:
            return False
    
    def _load_cache(self, cache_file: Path) -> Dict[str, Any]:
        """캐시 로드"""
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def _save_cache(self, cache_file: Path, data: Dict[str, Any]):
        """캐시 저장"""
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"캐시 저장 실패: {e}")
    
    def _extract_menu_from_image(self, image_file: Path) -> Dict[str, Any]:
        """ChatGPT API로 이미지에서 메뉴 추출"""
        try:
            # 이미지 base64 인코딩
            with open(image_file, 'rb') as f:
                base64_image = base64.b64encode(f.read()).decode('utf-8')
            
            # API 호출
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            payload = {
                "model": CHATGPT_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": MENU_EXTRACTION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": MAX_TOKENS,
                "temperature": TEMPERATURE
            }
            
            response = requests.post(CHATGPT_URL, headers=headers, json=payload)
            response.raise_for_status()
            
            # JSON 추출
            content = response.json()['choices'][0]['message']['content']
            json_start = content.find('{')
            json_end = content.rfind('}') + 1
            
            if json_start != -1 and json_end != -1:
                json_str = content[json_start:json_end]
                return json.loads(json_str)
            else:
                raise ValueError("JSON 형식을 찾을 수 없음")
                
        except Exception as e:
            logger.error(f"이미지 추출 실패: {e}")
            return self._create_fallback_menu()
    
    def _create_fallback_menu(self) -> Dict[str, Any]:
        """API 실패시 기본 메뉴"""
        return {
            "월요일": {"조식": ["식단 정보 로드 실패"], "중식": ["관리자에게 문의"], "석식": ["055-254-2096"]},
            "화요일": {"조식": [], "중식": [], "석식": []},
            "수요일": {"조식": [], "중식": [], "석식": []},
            "목요일": {"조식": [], "중식": [], "석식": []},
            "금요일": {"조식": [], "중식": [], "석식": []}
        }
    
    def _create_chunks(self, menu_data: Dict[str, Any]) -> List[TextChunk]:
        """메뉴 데이터를 청크로 변환"""
        chunks = []
        
        for day, meals in menu_data.items():
            for meal_type, menu_items in meals.items():
                if menu_items:  # 빈 메뉴 제외
                    chunk = self._create_meal_chunk(day, meal_type, menu_items)
                    if chunk:
                        chunks.append(chunk)
        
        return chunks
    
    def _create_meal_chunk(self, day: str, meal_type: str, menu_items: List[str]) -> TextChunk:
        """개별 식사 청크 생성"""
        menu_text = ", ".join(menu_items)
        
        content = MENU_TEMPLATE.format(
            day=day,
            meal_type=meal_type,
            menu_items=menu_text
        )
        
        metadata = {
            'source_file': MENU_IMAGE,
            'day': day,
            'meal_type': meal_type,
            'menu_count': len(menu_items),
            'processing_date': datetime.now().isoformat()
        }
        
        source_id = f'menu/{MENU_IMAGE}#{day}_{meal_type}'
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
        
        image_file = self.source_dir / MENU_IMAGE
        if image_file.exists():
            hasher.update(str(image_file.stat().st_mtime).encode())
        
        return hasher.hexdigest()[:16]
    
    def _save_hash(self):
        """현재 해시 저장"""
        hash_file = self.vectorstore_dir / ".source_hash"
        with open(hash_file, 'w') as f:
            f.write(self._calculate_hash())


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    
    try:
        loader = MenuLoader()
        loader.build_vectorstore()
        print("✅ 식단표 벡터스토어 구축 완료")
    except Exception as e:
        print(f"❌ 실패: {e}")
        exit(1)


if __name__ == '__main__':
    main()
