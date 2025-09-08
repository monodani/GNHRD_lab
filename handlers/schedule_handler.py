# handlers/schedule_handler.py
"""
벼리톡@경상남도인재개발원 - 교육 일정 핸들러 v1.0 (리팩토링)
BasePandasAgentHandler를 상속받아 동작하며, 모든 로직과 설정은 중앙에서 관리됩니다.

작성자: 이다니엘 from 경상남도인재개발원 (Gemini AI 리팩토링)
최종 수정: 2025-09-08
"""
from .base.pandas_base_handler import BasePandasAgentHandler

class ScheduleHandler(BasePandasAgentHandler):
    """
    교육 일정 CSV 데이터를 분석하는 핸들러.
    모든 기능은 부모 클래스인 BasePandasAgentHandler에 위임합니다.
    """
    def __init__(self):
        # 🎯 'schedule' 이라는 이름으로 부모 클래스를 초기화합니다.
        # 이 이름은 config.py에 정의된 설정 키와 일치해야 합니다.
        super().__init__(domain_name="schedule")
