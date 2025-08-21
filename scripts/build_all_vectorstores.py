#!/usr/bin/env python3
"""
경상남도인재개발원 RAG 챗봇 - 통합 벡터스토어 빌드 스크립트

GitHub Actions 전용 - 직관적이고 아름다운 코딩
"""

import os
import sys
import logging
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

# 프로젝트 루트 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# =============================================================================
# 🔧 파인튜닝 설정 구역
# =============================================================================

# 로더 매핑 (순서: 성공 가능성 높은 순)
LOADERS = {
    'cyber': 'modules.loader_cyber.CyberLoader',
    'menu': 'modules.loader_menu.MenuLoader', 
    'notice': 'modules.loader_notice.NoticeLoader',
    'satisfaction': 'modules.loader_satisfaction.SatisfactionLoader',
    'general': 'modules.loader_general.GeneralLoader',
    'publish': 'modules.loader_publish.PublishLoader'
}

# GitHub Actions 설정
TIMEOUT_MINUTES = 25
MIN_SUCCESS_DOMAINS = 3

# =============================================================================

def setup_logging():
    """GitHub Actions 최적화 로깅"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler()]
    )
    return logging.getLogger(__name__)

def check_environment():
    """환경 검증"""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY 환경변수가 필요합니다")
        return False
    
    print(f"✅ API 키 확인: {api_key[:10]}...")
    
    # 필수 디렉터리 확인
    for dir_name in ['data', 'vectorstores', 'modules']:
        if not Path(dir_name).exists():
            print(f"❌ 필수 디렉터리 없음: {dir_name}")
            return False
    
    return True

def import_loader(module_path: str):
    """동적 로더 import"""
    try:
        module_name, class_name = module_path.rsplit('.', 1)
        module = __import__(module_name, fromlist=[class_name])
        return getattr(module, class_name)
    except Exception as e:
        raise ImportError(f"로더 import 실패: {module_path} - {e}")

def get_domain_stats(domain: str) -> Dict[str, Any]:
    """도메인별 벡터스토어 통계 자체 계산 (아름다운 경로 매핑)"""
    
    # 🗂️ 도메인별 벡터스토어 경로 매핑 (satisfaction, publish는 unified)
    vectorstore_paths = {
        'satisfaction': 'vectorstores/vectorstore_unified_satisfaction',
        'publish': 'vectorstores/vectorstore_unified_publish',
        'cyber': 'vectorstores/vectorstore_cyber',
        'general': 'vectorstores/vectorstore_general',
        'notice': 'vectorstores/vectorstore_notice',
        'menu': 'vectorstores/vectorstore_menu'
    }
    
    try:
        path = Path(vectorstore_paths[domain])
        faiss_file = path / f"{domain}_index.faiss"
        pkl_file = path / f"{domain}_index.pkl"
        
        # 파일 존재 및 크기 확인
        faiss_exists = faiss_file.exists()
        pkl_exists = pkl_file.exists()
        
        return {
            'domain': domain,
            'path': str(path),
            'vectorstore_exists': faiss_exists and pkl_exists,
            'faiss_size_mb': round(faiss_file.stat().st_size / (1024*1024), 2) if faiss_exists else 0,
            'pkl_size_mb': round(pkl_file.stat().st_size / (1024*1024), 2) if pkl_exists else 0,
            'total_size_mb': round((faiss_file.stat().st_size + pkl_file.stat().st_size) / (1024*1024), 2) if faiss_exists and pkl_exists else 0,
            'last_modified': datetime.fromtimestamp(faiss_file.stat().st_mtime).isoformat() if faiss_exists else None
        }
        
    except Exception as e:
        return {
            'domain': domain,
            'error': f"통계 수집 실패: {e}",
            'vectorstore_exists': False
        }

def build_single_domain(domain: str, loader_class) -> Dict[str, Any]:
    """단일 도메인 빌드"""
    print(f"\n::group::{domain.upper()} 도메인 빌드")
    
    try:
        start_time = time.time()
        
        # 로더 실행
        loader = loader_class()
        success = loader.build_vectorstore(force_rebuild=False)
        
        if not success:
            return {'status': 'failed', 'error': 'Build returned False'}
        
        elapsed = time.time() - start_time
        
        # 📊 벡터스토어 통계 자체 계산
        stats = get_domain_stats(domain)
        stats['build_time'] = round(elapsed, 2)
        stats['timestamp'] = datetime.now().isoformat()
        
        print(f"✅ {domain} 빌드 성공 ({elapsed:.1f}초)")
        if stats.get('vectorstore_exists'):
            print(f"📁 벡터스토어 크기: {stats.get('total_size_mb', 0):.1f}MB")
        
        return {
            'status': 'success',
            'elapsed_time': elapsed,
            'stats': stats
        }
        
    except Exception as e:
        print(f"❌ {domain} 빌드 실패: {e}")
        return {
            'status': 'failed', 
            'error': str(e)
        }
    finally:
        print("::endgroup::")

def build_all_vectorstores() -> Dict[str, Any]:
    """모든 벡터스토어 빌드"""
    logger = setup_logging()
    start_time = datetime.now()
    
    print("🚀 벡터스토어 통합 빌드 시작")
    print(f"📅 시작: {start_time.isoformat()}")
    print(f"📊 총 도메인: {len(LOADERS)}")
    
    results = {}
    success_count = 0
    
    # 각 도메인 빌드
    for domain, module_path in LOADERS.items():
        try:
            # 로더 import
            loader_class = import_loader(module_path)
            
            # 빌드 실행
            result = build_single_domain(domain, loader_class)
            results[domain] = result
            
            if result['status'] == 'success':
                success_count += 1
                
        except Exception as e:
            print(f"❌ {domain} 처리 중 예외: {e}")
            results[domain] = {
                'status': 'failed',
                'error': f"Import/Build 실패: {e}"
            }
    
    # 최종 결과
    end_time = datetime.now()
    elapsed = end_time - start_time
    
    final_result = {
        'timestamp': end_time.isoformat(),
        'elapsed_time': str(elapsed),
        'total_domains': len(LOADERS),
        'successful_domains': success_count,
        'failed_domains': len(LOADERS) - success_count,
        'success_rate': f"{(success_count / len(LOADERS) * 100):.1f}%",
        'results': results
    }
    
    return final_result

def save_report(results: Dict[str, Any]):
    """빌드 보고서 저장"""
    try:
        with open('vectorstore_build_report.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("📄 빌드 보고서 저장 완료")
    except Exception as e:
        print(f"⚠️ 보고서 저장 실패: {e}")

def print_summary(results: Dict[str, Any]):
    """결과 요약 출력"""
    print("\n" + "="*60)
    print("📊 벡터스토어 빌드 최종 결과")
    print("="*60)
    
    print(f"🕐 완료 시간: {results['timestamp']}")
    print(f"⏱️ 소요 시간: {results['elapsed_time']}")
    print(f"📈 성공률: {results['success_rate']}")
    print(f"✅ 성공: {results['successful_domains']}개")
    print(f"❌ 실패: {results['failed_domains']}개")
    
    # 도메인별 상세 결과
    print(f"\n📋 도메인별 결과:")
    for domain, result in results['results'].items():
        status_icon = "✅" if result['status'] == 'success' else "❌"
        elapsed = result.get('elapsed_time', 0)
        print(f"  {status_icon} {domain}: {result['status']}")
        if result['status'] == 'success' and elapsed:
            print(f"     소요시간: {elapsed:.1f}초")
        elif result['status'] == 'failed':
            print(f"     오류: {result.get('error', 'Unknown')}")
    
    print("="*60)

def main():
    """메인 실행"""
    # 환경 검증
    if not check_environment():
        sys.exit(1)
    
    try:
        # 빌드 실행
        results = build_all_vectorstores()
        
        # 결과 출력 및 저장
        print_summary(results)
        save_report(results)
        
        # 성공률 체크
        if results['successful_domains'] < MIN_SUCCESS_DOMAINS:
            print(f"\n⚠️ 최소 요구 도메인({MIN_SUCCESS_DOMAINS})보다 적게 성공")
            sys.exit(1)
        else:
            print(f"\n🎉 빌드 성공! ({results['successful_domains']}/{results['total_domains']})")
            sys.exit(0)
            
    except Exception as e:
        print(f"❌ 치명적 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
