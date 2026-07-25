from pansou_py.plugins.core.web_fallback import WebFallbackPlugin


def test_web_fallback_keeps_only_keyword_context_links():
    plugin = WebFallbackPlugin()
    body = """
    <html>
      <head><title>资源合集</title></head>
      <body>
        <p>庆余年 第二季 夸克网盘 https://pan.quark.cn/s/relevant123</p>
        <p>其他电视剧 夸克网盘 https://pan.quark.cn/s/unrelated456</p>
      </body>
    </html>
    """

    links = plugin._extract_relevant_links("庆余年", body, "资源合集", "资源合集")

    assert [link.url for link in links] == ["https://pan.quark.cn/s/relevant123"]


def test_web_fallback_allows_single_link_when_page_matches_keyword():
    plugin = WebFallbackPlugin()
    body = """
    <html>
      <head><title>庆余年 第二季 在线观看</title></head>
      <body>
        <p>夸克网盘 https://pan.quark.cn/s/single123</p>
      </body>
    </html>
    """

    links = plugin._extract_relevant_links("庆余年", body, "庆余年 第二季 在线观看", "庆余年 第二季 在线观看")

    assert [link.url for link in links] == ["https://pan.quark.cn/s/single123"]
