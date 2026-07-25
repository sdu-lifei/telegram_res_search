from pathlib import Path
import random
import textwrap

from PIL import Image, ImageDraw, ImageFilter, ImageFont


OUT = Path("share_images/cards")
OUT.mkdir(parents=True, exist_ok=True)
FONT_PATH = "/System/Library/Fonts/STHeiti Light.ttc"


def font(size: int):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        return ImageFont.load_default()


ITEMS = [
    ("01_tiequan_card.png", "铁拳教育", "2026 韩剧，校园霸凌与以暴制暴题材，节奏爽、话题度高。", "https://pan.quark.cn/s/e9a806761dc1", ("#111827", "#991b1b", "#f59e0b")),
    ("02_qingyunian_card.png", "庆余年 第二季", "古装权谋爽剧，全36集，范闲继续周旋朝堂与江湖。", "https://pan.quark.cn/s/7dd6b0f673f2", ("#102a43", "#b45309", "#eab308")),
    ("03_shujuan_card.png", "书卷一梦", "2025 国剧，爱情 / 奇幻 / 古装，李一桐、刘宇宁主演。", "https://pan.quark.cn/s/03f714a76b24", ("#2e1065", "#7c3aed", "#f0abfc")),
    ("04_lizhi_card.png", "长安的荔枝", "雷佳音主演，喜剧 / 古装，讲述“荔枝使”千里运送鲜荔枝的艰难任务。", "https://pan.quark.cn/s/30afbbfff1ff", ("#451a03", "#b45309", "#fde68a")),
    ("05_baqianli_card.png", "八千里路云和月", "2026 年代 / 战争剧，全40集，王阳、万茜、黄澄澄、于和伟主演。", "https://pan.quark.cn/s/38a972ca273f", ("#1f2937", "#4b5563", "#d1d5db")),
    ("06_saullawyer_card.png", "风骚律师 全1-6季", "《绝命毒师》前传，高分犯罪美剧，讲述律师 Saul Goodman 的故事。", "https://pan.quark.cn/s/7bbdc1ae5e72", ("#111827", "#0f766e", "#facc15")),
    ("07_breakingbad_card.png", "绝命毒师 五季合集", "经典犯罪美剧，蓝光原盘 REMUX，内封简繁英双语字幕。", "https://pan.quark.cn/s/fe3ff60faf09", ("#052e16", "#15803d", "#bef264")),
    ("08_moli_card.png", "莫离", "2026 爱情 / 古装剧，白鹿主演，4K HDR 版本。", "https://pan.quark.cn/s/b1f5788f1699", ("#4a044e", "#be185d", "#fbcfe8")),
    ("09_busan_card.png", "釜山行 系列两部合集", "韩国丧尸灾难片系列，4K 原盘 REMUX，杜比视界，内封简英双语字幕。", "https://pan.quark.cn/s/6093182d43fd", ("#111827", "#7f1d1d", "#fca5a5")),
    ("10_zheyao_card.png", "折腰", "2025 古装爱情剧，宋祖儿、刘宇宁主演，4K 60fps HDR 高码率版本。", "https://pan.quark.cn/s/00cda470036c", ("#172554", "#2563eb", "#bfdbfe")),
]


def rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def draw_card(index: int, filename: str, title: str, desc: str, link: str, colors):
    width, height = 1080, 1440
    base, mid, accent = colors
    base_rgb = rgb(base)
    mid_rgb = rgb(mid)
    accent_rgb = rgb(accent)

    img = Image.new("RGB", (width, height), base_rgb)
    draw = ImageDraw.Draw(img)

    for y in range(height):
        ratio = y / height
        col = tuple(int(base_rgb[i] * (1 - ratio) + mid_rgb[i] * ratio) for i in range(3))
        draw.line([(0, y), (width, y)], fill=col)

    random.seed(index)
    for _ in range(18):
        x = random.randint(-200, width)
        y = random.randint(0, height)
        radius = random.randint(80, 260)
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*accent_rgb, random.randint(18, 45)))
        overlay = overlay.filter(ImageFilter.GaussianBlur(25))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

    margin = 72
    draw.rounded_rectangle((margin, margin, width - margin, height - margin), radius=36, fill=(255, 255, 255, 24), outline=(255, 255, 255), width=2)
    draw.rounded_rectangle((118, 130, 962, 610), radius=28, fill=(15, 15, 18), outline=(235, 235, 245), width=2)

    for k in range(8):
        x0 = 150 + k * 102
        top = 175 + random.randint(-10, 35)
        bottom = 565 - random.randint(0, 80)
        fill = tuple(max(0, min(255, int(c * random.uniform(0.45, 0.95)))) for c in accent_rgb)
        draw.rounded_rectangle((x0, top, x0 + 70, bottom), radius=16, fill=fill)

    draw.ellipse((430, 250, 650, 470), fill=(255, 255, 255), outline=(255, 255, 255), width=4)
    draw.polygon([(515, 315), (515, 405), (590, 360)], fill=mid_rgb)
    draw.text((150, 520), "影视资源", fill=(255, 255, 255), font=font(42))

    title_font = font(72 if len(title) <= 8 else 58)
    body_font = font(38)
    small_font = font(32)
    link_font = font(36)

    draw.text((120, 690), f"{index}. {title}", fill=(255, 255, 255), font=title_font)
    y = 800
    for line in textwrap.wrap(desc, width=23):
        draw.text((120, y), line, fill=(238, 242, 255), font=body_font)
        y += 56

    draw.text((120, 1060), "链接", fill=accent_rgb, font=small_font)
    draw.rounded_rectangle((120, 1110, 960, 1235), radius=20, fill=(255, 255, 255))
    yy = 1135
    for line in textwrap.wrap(link, width=34):
        draw.text((150, yy), line, fill=(20, 78, 140), font=link_font)
        yy += 45

    draw.text((120, 1300), "夸克资源搜索 · 我的分享链接", fill=(255, 255, 255), font=small_font)
    img.save(OUT / filename, quality=95)


for index, item in enumerate(ITEMS, 1):
    draw_card(index, *item)
    print((OUT / item[0]).resolve())
