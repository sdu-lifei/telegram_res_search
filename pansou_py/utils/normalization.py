import re

def normalize_keyword(kw: str) -> str:
    """Normalize search keyword by stripping common prefixes and whitespace."""
    if not kw:
        return ""
    kw = kw.strip()
    # Strip patterns like '名称:', '名字：', '名称: ' etc.
    kw = re.sub(r'^[\u540d\u79f0\u5c0f\u8d44\u6e90\u6807\u9898][\uff1a:\s]+', '', kw).strip()
    # Remove common file extensions if present at the end
    kw = re.sub(r'\.(mp4|mkv|avi|mov|wmv|ts|flv)$', '', kw, flags=re.IGNORECASE).strip()
    return kw
