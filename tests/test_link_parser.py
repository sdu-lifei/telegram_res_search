from pansou_py.core.tg_searcher import _keyword_variants
from pansou_py.utils.link_parser import extract_netdisk_links, extract_password, get_link_type


def test_extract_quark_link_and_password():
    text = "资源 https://pan.quark.cn/s/a500126895e7 提取码: ab12"

    links = extract_netdisk_links(text)

    assert "https://pan.quark.cn/s/a500126895e7" in links
    assert get_link_type(links[0]) == "quark"
    assert extract_password(text, links[0]) == "ab12"


def test_keyword_variants_cover_common_title_aliases():
    assert "沙丘 2" in _keyword_variants("沙丘2")
    assert "Dune Part Two" in _keyword_variants("沙丘2")
    assert "酱园弄 悬案" in _keyword_variants("酱园弄")
