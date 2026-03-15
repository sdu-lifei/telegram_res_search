import re
from urllib.parse import unquote

# Compiled regex patterns for various cloud disks
ALL_PAN_LINKS_PATTERN = re.compile(
    r'(?i)(?:(?:magnet:\?xt=urn:btih:[a-zA-Z0-9]+)|(?:ed2k://\|file\|[^|]+\|\d+\|[A-Fa-f0-9]+\|/?)|'
    r'(?:https?://(?:(?:[\w.-]+\.)?(?:pan\.(?:baidu|quark)\.cn|(?:www\.)?(?:alipan|aliyundrive)\.com|drive\.uc\.cn|cloud\.189\.cn|caiyun\.139\.com|(?:www\.)?123(?:684|685|912|pan|592)\.(?:com|cn)|115\.com|115cdn\.com|anxia\.com|pan\.xunlei\.com|mypikpak\.com))(?:/[^\s\'"<>\\(\\)]*)?))'
)

# Specific patterns
BAIDU_PAN_PATTERN = re.compile(r'https?://pan\.baidu\.com/s/[a-zA-Z0-9_-]+(?:\?pwd=[a-zA-Z0-9]{4})?')
QUARK_PAN_PATTERN = re.compile(r'https?://pan\.quark\.cn/s/[a-zA-Z0-9]+')
XUNLEI_PAN_PATTERN = re.compile(r'https?://pan\.xunlei\.com/s/[a-zA-Z0-9]+(?:\?pwd=[a-zA-Z0-9]{4})?(?:#)?')
TIANYI_PAN_PATTERN = re.compile(r'https?://cloud\.189\.cn/t/[a-zA-Z0-9]+(?:%[0-9A-Fa-f]{2})*(?:（[^）]*）)?')
UC_PAN_PATTERN = re.compile(r'https?://drive\.uc\.cn/s/[a-zA-Z0-9]+(?:\?public=\d)?')
PAN123_PATTERN = re.compile(r'https?://(?:www\.)?123(?:684|865|685|912|pan|592)\.(?:com|cn)/s/[a-zA-Z0-9_-]+(?:\?(?:%E6%8F%90%E5%8F%96%E7%A0%81|提取码)[:：][a-zA-Z0-9]+)?')
PAN115_PATTERN = re.compile(r'https?://(?:115\.com|115cdn\.com|anxia\.com)/s/[a-zA-Z0-9]+(?:\?password=[a-zA-Z0-9]{4})?(?:#)?')
ALIYUN_PAN_PATTERN = re.compile(r'https?://(?:www\.)?(?:alipan|aliyundrive)\.com/s/[a-zA-Z0-9]+')

# Password extraction
PASSWORD_PATTERN = re.compile(r'(?i)(?:(?:提取|访问|提取密|密)码|pwd)[：:]\s*([a-zA-Z0-9]{4})(?:[^a-zA-Z0-9]|$)')
URL_PASSWORD_PATTERN = re.compile(r'(?i)[?&]pwd=([a-zA-Z0-9]{4})(?:[^a-zA-Z0-9]|$)')
BAIDU_PASSWORD_PATTERN = re.compile(r'(?i)(?:链接：.*?提取码：|密码：|提取码：|pwd=|pwd:|pwd：)([a-zA-Z0-9]{4})(?:[^a-zA-Z0-9]|$)')


# Domains that are NOT cloud disks — skip these immediately
NON_DISK_DOMAINS = [
    "t.me", "telegram.org", "github.com", "github.io",
    "youtube.com", "youtu.be", "twitter.com", "weibo.com",
    "douban.com", "bilibili.com", "ip-ddns.com", "gitee.com",
    "tgsou",
]

def get_link_type(url: str) -> str:
    """Return the type of cloud disk link, or empty string if not a known disk."""
    lower = url.lower()
    
    # Reject anything that is clearly NOT a cloud disk
    for bad_domain in NON_DISK_DOMAINS:
        if bad_domain in lower:
            return ""
    
    # Also reject anything that doesn't start with http/https/magnet/ed2k
    if not (lower.startswith("http") or lower.startswith("magnet:") or lower.startswith("ed2k:")):
        return ""
    
    if "链接：" in url or "链接:" in url:
        parts = url.split("链接", 1)
        if len(parts) > 1:
            url = parts[1]
            if url.startswith("：") or url.startswith(":"):
                url = url[1:]
            url = url.strip()
            lower = url.lower()
            
    if "ed2k:" in lower: return "ed2k"
    if lower.startswith("magnet:"): return "magnet"
    if "pan.baidu.com" in lower: return "baidu"
    if "pan.quark.cn" in lower: return "quark"
    if "alipan.com" in lower or "aliyundrive.com" in lower: return "aliyun"
    if "cloud.189.cn" in lower: return "tianyi"
    if "drive.uc.cn" in lower: return "uc"
    if "caiyun.139.com" in lower: return "mobile"
    if "115.com" in lower or "115cdn.com" in lower or "anxia.com" in lower: return "115"
    if "mypikpak.com" in lower: return "pikpak"
    if "pan.xunlei.com" in lower: return "xunlei"
    
    # 123 domains
    for d in ["123684.com", "123685.com", "123865.com", "123912.com", "123pan.com", "123pan.cn", "123592.com"]:
        if d in lower:
            return "123"
    
    # Return empty string for unknown URLs — do NOT return 'others'
    return ""

def clean_baidu_pan_url(url: str) -> str:
    if "https://pan.baidu.com/s/" in url:
        start_idx = url.find("https://pan.baidu.com/s/")
        url = url[start_idx:]
        end_markers = [" ", "\n", "\t", "，", "。", "；", ";", ",", "?pwd="]
        min_end_idx = len(url)
        for marker in end_markers:
            idx = url.find(marker)
            if 0 < idx < min_end_idx:
                min_end_idx = idx
        if min_end_idx < len(url):
            url = url[:min_end_idx]
            
        if "?pwd=" in url:
            pwd_idx = url.find("?pwd=")
            if len(url) > pwd_idx + 5:
                pwd_end_idx = pwd_idx + 9
                if pwd_end_idx <= len(url):
                    return url[:pwd_end_idx]
                return url
    return url

def extract_netdisk_links(text: str) -> list[str]:
    links = ALL_PAN_LINKS_PATTERN.findall(text)
    return list(set(links))

def normalize_url(raw_url: str) -> str:
    try:
        return unquote(raw_url)
    except Exception:
        return raw_url

def extract_password(text: str, url: str) -> str:
    # Basic pwd param check
    url_match = URL_PASSWORD_PATTERN.search(url)
    if url_match:
        return url_match.group(1)
        
    pwd_match = PASSWORD_PATTERN.search(text)
    if pwd_match:
        return pwd_match.group(1)
        
    baidu_match = BAIDU_PASSWORD_PATTERN.search(text)
    if baidu_match:
        return baidu_match.group(1)
    
    return ""

def clean_url(url: str, link_type: str) -> str:
    if link_type == "baidu":
        return clean_baidu_pan_url(url)
    # Simple cleaner for others removing common Chinese characters or spaces
    end_markers = [" ", "\n", "\t", "，", "。", "；", ";", ",", "提取码", "密码"]
    min_end_idx = len(url)
    for marker in end_markers:
        idx = url.find(marker)
        if 0 < idx < min_end_idx:
            min_end_idx = idx
    if min_end_idx < len(url):
        url = url[:min_end_idx]
    return url
