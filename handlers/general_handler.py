# handlers/general_handler.py
from .base.faiss_base_handler import BaseFaissHandler

class GeneralHandler(BaseFaissHandler):
    """일반 정보(학칙, 규정 등) FAISS 벡터 검색 핸들러."""
    def __init__(self):
        super().__init__(domain_name="general")
