# handlers/menu_handler.py
from .base.faiss_base_handler import BaseFaissHandler

class MenuHandler(BaseFaissHandler):
    """구내식당 메뉴 FAISS 벡터 검색 핸들러."""
    def __init__(self):
        super().__init__(domain_name="menu")
