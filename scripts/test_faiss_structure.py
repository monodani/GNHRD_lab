# test_faiss_structure.py (검증용 스크립트)
"""LangChain FAISS 내부 구조 탐색 테스트"""

import numpy as np
from utils.index_manager import get_index_manager

def test_faiss_internal_access():
    """FAISS 내부 구조 접근 가능성 검증"""
    
    print("🔍 LangChain FAISS 내부 구조 검증 시작")
    
    try:
        # 1. 벡터스토어 로드
        index_manager = get_index_manager()
        vectorstore = index_manager.get_vectorstore("general")
        
        print(f"✅ 벡터스토어 로드 성공: {type(vectorstore)}")
        
        # 2. 내부 속성 탐색
        print("\n🔍 내부 속성 탐색:")
        for attr in ['index', 'docstore', 'index_to_docstore_id']:
            if hasattr(vectorstore, attr):
                obj = getattr(vectorstore, attr)
                print(f"✅ {attr}: {type(obj)} - {obj}")
            else:
                print(f"❌ {attr}: 속성 없음")
        
        # 3. FAISS 인덱스 직접 접근 테스트
        if hasattr(vectorstore, 'index'):
            faiss_index = vectorstore.index
            print(f"\n🔍 FAISS 인덱스 정보:")
            print(f"  • 타입: {type(faiss_index)}")
            print(f"  • 벡터 개수: {faiss_index.ntotal if hasattr(faiss_index, 'ntotal') else '알 수 없음'}")
            print(f"  • 차원: {faiss_index.d if hasattr(faiss_index, 'd') else '알 수 없음'}")
        
        # 4. 임베딩 접근 테스트
        if hasattr(vectorstore, 'embeddings'):
            embeddings = vectorstore.embeddings
            print(f"\n🔍 임베딩 객체: {type(embeddings)}")
            
            # 테스트 쿼리 임베딩
            test_query = "근태관리 규정"
            query_vector = embeddings.embed_query(test_query)
            print(f"  • 쿼리 벡터 생성: {len(query_vector)}차원")
        
        return True
        
    except Exception as e:
        print(f"❌ 검증 실패: {e}")
        return False

def test_direct_search():
    """직접 검색 방식 실행 가능성 테스트"""
    
    print("\n🧪 직접 검색 방식 테스트")
    
    try:
        index_manager = get_index_manager()
        vectorstore = index_manager.get_vectorstore("general")
        
        # 테스트 쿼리
        query = "근태관리 규정"
        
        # 방법 1: 기존 LangChain 방식
        print("📋 방법 1: LangChain 표준 방식")
        docs_standard = vectorstore.similarity_search_with_score(query, k=3)
        print(f"  • 결과: {len(docs_standard)}개")
        if docs_standard:
            print(f"  • 첫 번째 점수: {docs_standard[0][1]:.4f}")
        
        # 방법 2: 직접 FAISS 접근 (시도)
        print("\n📋 방법 2: 직접 FAISS 접근")
        
        # 쿼리 벡터 생성
        query_vector = vectorstore.embeddings.embed_query(query)
        query_array = np.array([query_vector]).astype('float32')
        
        # FAISS 직접 검색 시도
        if hasattr(vectorstore, 'index'):
            distances, indices = vectorstore.index.search(query_array, k=3)
            print(f"  • FAISS 직접 검색 성공!")
            print(f"  • 거리: {distances[0]}")
            print(f"  • 인덱스: {indices[0]}")
            
            # 문서 매핑 시도
            if hasattr(vectorstore, 'index_to_docstore_id'):
                print(f"  • 매핑 정보 존재: {type(vectorstore.index_to_docstore_id)}")
                
                for i, faiss_id in enumerate(indices[0]):
                    if faiss_id in vectorstore.index_to_docstore_id:
                        doc_id = vectorstore.index_to_docstore_id[faiss_id]
                        print(f"    - FAISS {faiss_id} → Doc {doc_id}")
                        
                        if hasattr(vectorstore, 'docstore'):
                            doc = vectorstore.docstore.search(doc_id)
                            if doc:
                                content_preview = doc.page_content[:100] + "..."
                                print(f"      내용: {content_preview}")
        
        return True
        
    except Exception as e:
        print(f"❌ 직접 검색 테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 LangChain FAISS 호환성 검증 테스트")
    print("=" * 60)
    
    # 기본 구조 탐색
    structure_ok = test_faiss_internal_access()
    
    if structure_ok:
        # 직접 검색 테스트
        search_ok = test_direct_search()
        
        if search_ok:
            print("\n🎉 결론: 코랩 방식 적용 가능!")
        else:
            print("\n⚠️ 결론: 직접 검색 방식에 제약 있음")
    else:
        print("\n❌ 결론: 내부 구조 접근 불가")
    
    print("=" * 60)
