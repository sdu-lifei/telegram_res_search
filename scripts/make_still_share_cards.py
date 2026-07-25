from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "share_images" / "final"
OUT.mkdir(parents=True, exist_ok=True)

FONT_PATHS = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def font(size: int):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


ITEMS = [
    {
        "file": "01_tiequan.png",
        "still": "01_tiequan.jpg",
        "title": "铁拳教育",
        "desc": "韩剧，校园霸凌与以暴制暴题材，节奏爽、话题度高。",
        "link": "https://pan.quark.cn/s/e9a806761dc1",
    },
    {
        "file": "02_qingyunian2.png",
        "still": "02_qingyunian.jpg",
        "title": "庆余年 第二季",
        "desc": "古装权谋爽剧，范闲继续周旋朝堂与江湖。",
        "link": "https://pan.quark.cn/s/7dd6b0f673f2",
    },
    {
        "file": "03_shujuanyimeng.png",
        "still": "03_shujuan.jpg",
        "title": "书卷一梦",
        "desc": "爱情 / 奇幻 / 古装，李一桐、刘宇宁主演。",
        "link": "https://pan.quark.cn/s/03f714a76b24",
    },
    {
        "file": "04_changanlizhi.png",
        "still": "04_lizhi.jpg",
        "title": "长安的荔枝",
        "desc": "雷佳音主演，喜剧 / 古装，讲述千里运送鲜荔枝的艰难任务。",
        "link": "https://pan.quark.cn/s/30afbbfff1ff",
    },
    {
        "file": "05_baqianli.png",
        "still": "05_baqianli.jpg",
        "title": "八千里路云和月",
        "desc": "年代 / 战争剧，王阳、万茜、黄澄澄、于和伟主演。",
        "link": "https://pan.quark.cn/s/38a972ca273f",
    },
    {
        "file": "06_yanxigonglue.png",
        "still": "07_yanxi.jpg",
        "title": "延禧攻略",
        "desc": "高热度清宫剧，魏璎珞一路进阶，宫斗线密集好追。",
        "link": "https://pan.quark.cn/s/5877f8984f2d",
    },
    {
        "file": "07_jintewu.png",
        "still": "10_jintewu.jpg",
        "title": "金特务",
        "desc": "韩影动作喜剧，轻松下饭，适合喜欢特工题材的朋友。",
        "link": "https://pan.quark.cn/s/4f5aee55684a",
    },
    {
        "file": "08_saullawyer.png",
        "still": "08_saullawyer.jpg",
        "title": "风骚律师 全1-6季",
        "desc": "《绝命毒师》前传，高分犯罪美剧，讲述 Saul Goodman 的故事。",
        "link": "https://pan.quark.cn/s/7bbdc1ae5e72",
    },
    {
        "file": "09_busan.png",
        "still": "09_busan.jpg",
        "title": "釜山行 系列两部合集",
        "desc": "韩国丧尸灾难片系列，4K 原盘 REMUX，紧张刺激。",
        "link": "https://pan.quark.cn/s/6093182d43fd",
    },
    {
        "file": "10_zheyao.png",
        "still": "09_zheyao.jpg",
        "title": "折腰",
        "desc": "古装爱情剧，宋祖儿、刘宇宁主演，4K 60fps HDR 版本。",
        "link": "https://pan.quark.cn/s/00cda470036c",
    },
]


def wrap_text(draw, text, font_obj, max_width):
    lines = []
    for paragraph in text.splitlines():
        line = ""
        for char in paragraph:
            candidate = line + char
            if draw.textbbox((0, 0), candidate, font=font_obj)[2] <= max_width:
                line = candidate
            else:
                if line:
                    lines.append(line)
                line = char
        if line:
            lines.append(line)
    return lines


def draw_card(index, item):
    width, height = 1080, 1500
    bg = Image.new("RGB", (width, height), "#f7f8fb")
    draw = ImageDraw.Draw(bg)

    still_path = ROOT / "share_images" / "stills" / item["still"]
    still = Image.open(still_path).convert("RGB")
    still = ImageOps.fit(still, (1080, 760), method=Image.Resampling.LANCZOS, centering=(0.5, 0.36))
    bg.paste(still, (0, 0))

    shade = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(350, 760):
        alpha = int((y - 350) / 410 * 180)
        sd.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
    bg = Image.alpha_composite(bg.convert("RGBA"), shade).convert("RGB")
    draw = ImageDraw.Draw(bg)

    draw.rounded_rectangle((56, 54, 208, 112), radius=29, fill=(0, 0, 0, 150))
    draw.text((86, 66), f"TOP {index}", font=font(30), fill="white")

    title_font = font(66 if len(item["title"]) <= 8 else 54)
    body_font = font(39)
    label_font = font(32)
    link_font = font(37)
    small_font = font(26)

    draw.text((64, 610), item["title"], font=title_font, fill="white")
    draw.text((64, 690), "我的分享资源", font=small_font, fill="#e5e7eb")

    panel_top = 760
    draw.rectangle((0, panel_top, width, height), fill="#ffffff")
    draw.rounded_rectangle((64, 820, 1016, 1422), radius=34, fill="#ffffff", outline="#d9e2ec", width=2)

    y = 870
    draw.text((110, y), f"{index}. 资源名：{item['title']}", font=body_font, fill="#121826")
    y += 74
    draw.text((110, y), "简介：", font=body_font, fill="#121826")
    x_desc = 226
    desc_lines = wrap_text(draw, item["desc"], body_font, 740)
    for n, line in enumerate(desc_lines[:3]):
        draw.text((x_desc if n == 0 else 110, y), line, font=body_font, fill="#1f2937")
        y += 56
    y += 22

    draw.text((110, y), "链接：", font=body_font, fill="#121826")
    y += 56
    draw.rounded_rectangle((110, y, 970, y + 118), radius=22, fill="#eef6ff", outline="#bfdbfe", width=2)
    link_lines = textwrap.wrap(item["link"], width=38)
    yy = y + 25
    for line in link_lines[:2]:
        draw.text((142, yy), line, font=link_font, fill="#0b63ce")
        yy += 44

    draw.text((110, 1362), "可直接转发到微信群", font=label_font, fill="#64748b")
    bg.save(OUT / item["file"], quality=95)
    return OUT / item["file"]


for idx, item in enumerate(ITEMS, 1):
    print(draw_card(idx, item))
