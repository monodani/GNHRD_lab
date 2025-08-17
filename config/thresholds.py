# config/thresholds.py
"""
벼리톡@경상남도인재개발원(BYEOLI-TALK@GNHRD) - Confidence 기반 4단계 분기 설정값
경상남도인재개발원 RAG 챗봇 시스템

Confidence 기반 응답 타입 결정:
- 0.0 ~ 0.20: 일상 대화 (벡터스토어 기반 서비스 소개)
- 0.20초과 ~ 0.50: 정보 부족 (담당부서 연락처 제공)
- 0.50초과 ~ 핸들러별기준: 되묻기 ("혹시 이런 의미인가요?")
- 핸들러별기준 초과 ~ 1.0: 정상 RAG 답변

작성자: 이다니엘 from 경상남도인재개발원
최종 수정: 2025-08-17
"""

# =============================================================================
# 공통 임계값 설정 (모든 핸들러 공통 적용)
# =============================================================================

COMMON_THRESHOLDS = {
    "casual_chat": 0.20,        # 일상 대화 임계값 (0.15~0.25 권장)
    "insufficient_info": 0.50   # 정보 부족 임계값 (0.45~0.55 권장)
}

# =============================================================================
# 핸들러별 개별 임계값 설정 (도메인 특성 반영)
# =============================================================================

HANDLER_THRESHOLDS = {
    # 만족도 조사: 정확성이 중요하므로 엄격하게 설정
    "satisfaction": 0.70,  # 0.50초과~0.70: 되묻기, 0.70초과~1.0: 정상답변
    
    # 일반 정보: 폭넓은 질문이 많으므로 관대하게 설정
    "general": 0.65,       # 0.50초과~0.65: 되묻기, 0.65초과~1.0: 정상답변
    
    # 사이버교육: 기술적 내용이므로 엄격하게 설정
    "cyber": 0.75,         # 0.50초과~0.75: 되묻기, 0.75초과~1.0: 정상답변
    
    # 구내식당 메뉴: 일상적 질문이므로 관대하게 설정
    "menu": 0.60,          # 0.50초과~0.60: 되묻기, 0.60초과~1.0: 정상답변
    
    # 공지사항: 정확한 전달이 중요하므로 적당히 설정
    "notice": 0.65,        # 0.50초과~0.65: 되묻기, 0.65초과~1.0: 정상답변
    
    # 발행물: 정확한 정보 제공이 중요하므로 엄격하게 설정
    "publish": 0.70        # 0.50초과~0.70: 되묻기, 0.70초과~1.0: 정상답변
}

# =============================================================================
# 담당부서 연락처 정보
# =============================================================================

DEPARTMENT_CONTACTS = {
    "general": {
        "department": "인재양성과 교육기획담당",
        "phone": "055-254-2051",
        "description": "교육과정 기획, 운영 관련"
    },
    "satisfaction": {
        "department": "인재개발지원과 평가분석담당",
        "phone": "055-254-2021",
        "description": "만족도 조사, 교육 성과 분석 관련"
    },
    "cyber": {
        "department": "인재양성과 사이버담당",
        "phone": "055-254-2081",
        "description": "사이버교육, 온라인 학습 관련"
    },
    "menu": {
        "department": "인재개발지원과 총무담당",
        "phone": "055-254-2096",
        "description": "구내식당 관련"
    },
    "notice": {
        "department": "경상남도인재개발원",
        "phone": "055-254-2051",
        "description": "공지사항, 일반 문의"
    },
    "publish": {
        "department": "경상남도인재개발원",
        "phone": "055-254-2051",
        "description": "발행물, 자료 관련"
    }
}

# =============================================================================
# 전체 담당부서 목록 (정보 부족시 안내용)
# =============================================================================

ALL_DEPARTMENT_CONTACTS = [
    {
        "department": "인재개발지원과 총무담당",
        "phone": "055-254-2011",
        "description": "예산, 회계, 시설 및 구내식당 관리"
    },
    {
        "department": "인재개발지원과 평가분석담당",
        "phone": "055-254-2021",
        "description": "만족도 조사, 교육 성과 분석"
    },
    {
        "department": "인재양성과 교육기획담당",
        "phone": "055-254-2051",
        "description": "교육과정 기획, 운영"
    },
    {
        "department": "인재양성과 교육운영1담당",
        "phone": "055-254-2061",
        "description": "신규 임용(후보)자 과정, 기본역량, 리더십 교육"
    },
    {
        "department": "인재양성과 교육운영2담당",
        "phone": "055-254-2071",
        "description": "중견리더 과정, 직무역량, 전문교육"
    },
    {
        "department": "인재양성과 사이버담당",
        "phone": "055-254-2081",
        "description": "사이버교육, 온라인 학습"
    }
]

# =============================================================================
# 기관 정보
# =============================================================================

ORGANIZATION_INFO = {
    "name": "경상남도인재개발원",
    "website": "https://www.gyeongnam.go.kr/hrd",
    "main_phone": "055-254-2051",
    "address": "(우 52732) 경상남도 진주시 월아산로 2026 경상남도청 서부청사 4~6층"
}

# =============================================================================
# 설정 검증 함수
# =============================================================================

def validate_thresholds():
    """
    설정값 유효성 검증
    - 모든 임계값이 0.0 ~ 1.0 범위인지 확인
    - 핸들러별 임계값이 공통 임계값보다 높은지 확인
    """
    errors = []
    
    # 공통 임계값 범위 검증
    for key, value in COMMON_THRESHOLDS.items():
        if not (0.0 <= value <= 1.0):
            errors.append(f"COMMON_THRESHOLDS['{key}'] = {value}는 0.0~1.0 범위를 벗어남")
    
    # 핸들러별 임계값 범위 검증
    for handler, threshold in HANDLER_THRESHOLDS.items():
        if not (0.0 <= threshold <= 1.0):
            errors.append(f"HANDLER_THRESHOLDS['{handler}'] = {threshold}는 0.0~1.0 범위를 벗어남")
        
        # 핸들러별 임계값이 insufficient_info보다 높은지 확인
        if threshold <= COMMON_THRESHOLDS["insufficient_info"]:
            errors.append(f"HANDLER_THRESHOLDS['{handler}'] = {threshold}는 insufficient_info({COMMON_THRESHOLDS['insufficient_info']})보다 높아야 함")
    
    # 공통 임계값 순서 검증
    if COMMON_THRESHOLDS["casual_chat"] >= COMMON_THRESHOLDS["insufficient_info"]:
        errors.append(f"casual_chat({COMMON_THRESHOLDS['casual_chat']})는 insufficient_info({COMMON_THRESHOLDS['insufficient_info']})보다 낮아야 함")
    
    return errors

def get_response_type_description():
    """
    응답 타입별 설명 반환 (디버깅 및 문서화용)
    """
    return {
        "casual_chat": {
            "range": f"0.0 ~ {COMMON_THRESHOLDS['casual_chat']}",
            "description": "LLM 기반 일상 대화, 벡터스토어 기반 서비스 소개"
        },
        "insufficient_info": {
            "range": f"{COMMON_THRESHOLDS['casual_chat']}초과 ~ {COMMON_THRESHOLDS['insufficient_info']}",
            "description": "정보 부족, 담당부서 연락처 제공"
        },
        "clarification": {
            "range": f"{COMMON_THRESHOLDS['insufficient_info']}초과 ~ 핸들러별기준",
            "description": "되묻기, 의도 추론 후 선택지 제공"
        },
        "confident_answer": {
            "range": "핸들러별기준 초과 ~ 1.0",
            "description": "정상 RAG 답변, 검색 결과 기반 응답"
        }
    }

# =============================================================================
# 모듈 테스트
# =============================================================================

if __name__ == "__main__":
    print("=== 벼리톡 설정값 검증 ===")
    
    # 설정값 유효성 검증
    validation_errors = validate_thresholds()
    
    if validation_errors:
        print("❌ 설정값 오류 발견:")
        for error in validation_errors:
            print(f"  - {error}")
    else:
        print("✅ 모든 설정값이 유효합니다.")
    
    print("\n=== Confidence 기반 응답 타입 ===")
    response_types = get_response_type_description()
    for response_type, info in response_types.items():
        print(f"{response_type}: {info['range']} - {info['description']}")
    
    print("\n=== 핸들러별 임계값 ===")
    for handler, threshold in HANDLER_THRESHOLDS.items():
        print(f"{handler}: {threshold}")
    
    print(f"\n=== 기관 정보 ===")
    print(f"기관명: {ORGANIZATION_INFO['name']}")
    print(f"웹사이트: {ORGANIZATION_INFO['website']}")
    print(f"대표번호: {ORGANIZATION_INFO['main_phone']}")
