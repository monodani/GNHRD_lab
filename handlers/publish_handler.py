# handlers/publish_handler.py
from .base.faiss_base_handler import BaseFaissHandler

class PublishHandler(BaseFaissHandler):
    """발행물 FAISS 벡터 검색 핸들러."""
    def __init__(self):
        super().__init__(domain_name="publish")
