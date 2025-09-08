# handlers/notice_handler.py
from .base.faiss_base_handler import BaseFaissHandler

class NoticeHandler(BaseFaissHandler):
    """공지사항 FAISS 벡터 검색 핸들러."""
    def __init__(self):
        super().__init__(domain_name="notice")
