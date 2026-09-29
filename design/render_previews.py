from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math


OUT = Path(__file__).resolve().parent
S = 2
W, H = 1800, 1080
FONT = r"C:\Windows\Fonts\Noto Sans SC (TrueType).otf"
FONT_BOLD = r"C:\Windows\Fonts\Noto Sans SC Bold (TrueType).otf"
FONT_LATIN = r"C:\Windows\Fonts\bahnschrift.ttf"


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def ft(size, bold=False, latin=False):
    return ImageFont.truetype(FONT_LATIN if latin else FONT_BOLD if bold else FONT, size * S)


class Canvas:
    def __init__(self, background):
        self.im = Image.new("RGB", (W * S, H * S), rgb(background))
        self.d = ImageDraw.Draw(self.im)

    def box(self, xy, fill, radius=0, outline=None, width=1):
        xy = tuple(int(v * S) for v in xy)
        self.d.rounded_rectangle(xy, radius=radius * S, fill=rgb(fill),
                                 outline=rgb(outline) if outline else None, width=width * S)

    def line(self, xy, fill, width=1):
        self.d.line(tuple(int(v * S) for v in xy), fill=rgb(fill), width=width * S, joint="curve")

    def circle(self, xy, fill, outline=None, width=1):
        self.d.ellipse(tuple(int(v * S) for v in xy), fill=rgb(fill),
                       outline=rgb(outline) if outline else None, width=width * S)

    def text(self, x, y, value, size, color, bold=False, latin=False, anchor=None):
        self.d.text((int(x * S), int(y * S)), value, font=ft(size, bold, latin),
                    fill=rgb(color), anchor=anchor)

    def save(self, name):
        self.im.resize((W, H), Image.Resampling.LANCZOS).save(OUT / name, optimize=True)


def wave(c, x, y, w, h, color, seed=0):
    cy = y + h / 2
    for i in range(int(w / 4)):
        xx = x + i * 4
        envelope = 0.26 + 0.65 * abs(math.sin((i + seed) * .071) * math.sin((i + seed) * .019))
        amplitude = h * .43 * envelope * (0.4 + 0.6 * abs(math.sin((i + seed) * .47)))
        c.line((xx, cy - amplitude, xx, cy + amplitude), color, 2)


def chrome(c, x, y, w, title, p):
    c.box((x, y, x + w, y + 55), p["chrome"], 18)
    c.box((x, y + 32, x + w, y + 62), p["chrome"])
    for j, color in enumerate((p["warm"], p["accent"], p["muted"])):
        c.circle((x + 20 + j * 17, y + 22, x + 30 + j * 17, y + 32), color)
    c.text(x + 95, y + 15, title, 20, p["text"], bold=True)
    c.text(x + w - 113, y + 17, "—   □   ×", 18, p["muted"])


def chip(c, x, y, label, p, active=False, w=None):
    w = w or (len(label) * 15 + 26)
    c.box((x, y, x + w, y + 34), p["accent"] if active else p["sub"], 9,
          None if active else p["line"])
    c.text(x + 12, y + 6, label, 14, p["on"] if active else p["text"])
    return w


def button(c, x, y, w, label, p, active=True, h=43):
    c.box((x, y, x + w, y + h), p["accent"] if active else p["sub"], 10,
          None if active else p["line"])
    c.text(x + w / 2, y + h / 2, label, 16,
           p["on"] if active else p["text"], bold=True, anchor="mm")


def score(c, x, y, w, h, p):
    c.box((x, y, x + w, y + h), p["score"], 14, p["line"])
    for j in range(5):
        ly = y + 47 + j * 27
        c.line((x + 25, ly, x + w - 25, ly), p["line"], 1)
    seq = [(0, 3, 42), (1, 5, 56), (2, 6, 40), (3, 7, 74), (4, 5, 42),
           (5, 3, 60), (6, 2, 36), (7, 1, 72), (8, 3, 48)]
    step = (w - 80) / len(seq)
    for n, degree, dur in seq:
        xx = x + 41 + n * step
        yy = y + 138 - (degree - 1) * 13.4
        c.circle((xx - 8, yy - 6, xx + 8, yy + 6), p["accent"] if n == 3 else p["text"])
        c.line((xx + 8, yy, xx + 8, yy - 30), p["accent"] if n == 3 else p["text"], 2)
        c.text(xx - 6, y + h - 30, str(degree), 14, p["muted"], latin=True)
    c.text(x + 25, y + 10, "主旋律  ·  原调 C 大调  ·  估计 96 BPM", 14, p["muted"])


def converter(c, x, y, w, h, p, variant):
    c.box((x + 9, y + 14, x + w + 9, y + h + 14), p["shadow"], 20)
    c.box((x, y, x + w, y + h), p["panel"], 20)
    chrome(c, x, y, w, "听谱 · 曲谱转换器", p)
    body_y = y + 72
    if variant == "paper":
        c.box((x + 20, body_y, x + 84, y + h - 22), p["rail"], 14)
        for i, glyph in enumerate(("音", "波", "谱", "设")):
            yy = body_y + 26 + i * 70
            if i == 1:
                c.box((x + 31, yy - 7, x + 73, yy + 36), p["accent"], 10)
            c.text(x + 52, yy + 12, glyph, 25, p["on"] if i == 1 else p["muted"], anchor="mm")
        bx = x + 111
        bw = w - 138
    else:
        bx = x + 29
        bw = w - 58
    c.text(bx, body_y + 5, "把声音，写成可演奏的谱", 27, p["text"], bold=True)
    c.text(bx, body_y + 48, "保留原始音高与演奏时间；不支持的音会单独标出。", 15, p["muted"])
    c.box((bx, body_y + 88, bx + bw, body_y + 208), p["sub"], 15, p["line"])
    c.box((bx + 22, body_y + 110, bx + 73, body_y + 161), p["accent"], 12)
    c.text(bx + 47, body_y + 135, "♪", 29, p["on"], anchor="mm")
    c.text(bx + 91, body_y + 106, "星河之夜.mp3", 19, p["text"], bold=True)
    c.text(bx + 91, body_y + 141, "03:42  ·  44.1 kHz  ·  立体声", 14, p["muted"])
    c.line((bx + 22, body_y + 184, bx + bw - 22, body_y + 184), p["line"], 1)
    c.text(bx + 23, body_y + 184, "更换音频", 13, p["accent"], bold=True)
    c.text(bx + bw - 129, body_y + 184, "WAV / FLAC / M4A", 13, p["muted"])
    c.text(bx, body_y + 229, "识别范围", 17, p["text"], bold=True)
    xx = bx
    for label, active, ww in (("提取主旋律", True, 119), ("完整音符", False, 102), ("仅人声", False, 86)):
        chip(c, xx, body_y + 263, label, p, active, ww)
        xx += ww + 11
    c.box((bx, body_y + 317, bx + bw, body_y + 429), p["wave"], 14)
    wave(c, bx + 17, body_y + 329, bw - 34, 82, p["accent"], 14)
    c.line((bx + bw * .42, body_y + 325, bx + bw * .42, body_y + 420), p["warm"], 2)
    c.text(bx + 15, body_y + 403, "00:58", 12, p["wave_text"], latin=True)
    c.text(bx + bw - 59, body_y + 403, "03:42", 12, p["wave_text"], latin=True)
    c.text(bx, body_y + 452, "识别结果", 18, p["text"], bold=True)
    c.text(bx + bw - 138, body_y + 456, "低置信度  3 处", 14, p["warm"])
    score(c, bx, body_y + 491, bw, 210, p)
    c.text(bx + 2, body_y + 720, "音域外  2 音    ｜    重叠音  5 处    ｜    已保留原调", 14, p["muted"])
    button(c, bx + bw - 154, body_y + 749, 154, "导出曲谱", p)
    button(c, bx + bw - 306, body_y + 749, 139, "试听并校对", p, False)


def keybed(c, x, y, w, p):
    keys = [("1", "Z"), ("2", "X"), ("3", "C"), ("4", "V"),
            ("5", "B"), ("6", "N"), ("7", "M"), ("i", ",")]
    gap = 8
    kw = (w - gap * 7) / 8
    for i, (note, key) in enumerate(keys):
        xx = x + i * (kw + gap)
        highlighted = i == 4
        c.box((xx, y, xx + kw, y + 107), p["accent"] if highlighted else p["key"], 12,
              None if highlighted else p["line"])
        c.text(xx + kw / 2, y + 29, note, 28, p["on"] if highlighted else p["text"],
               bold=True, latin=True, anchor="mm")
        c.box((xx + kw / 2 - 19, y + 68, xx + kw / 2 + 19, y + 92),
              p["on"] if highlighted else p["sub"], 5)
        c.text(xx + kw / 2, y + 80, key, 15, p["accent"] if highlighted else p["text"],
               bold=True, latin=True, anchor="mm")


def playlist_row(c, x, y, w, n, title, duration, p, active=False):
    if active:
        c.box((x, y, x + w, y + 56), p["sub"], 10)
    c.text(x + 15, y + 15, f"{n:02}", 16, p["accent"] if active else p["muted"], latin=True)
    c.text(x + 56, y + 12, title, 17, p["text"], bold=active)
    c.text(x + w - 68, y + 16, duration, 15, p["muted"], latin=True)


def player(c, x, y, w, h, p, variant):
    c.box((x + 9, y + 14, x + w + 9, y + h + 14), p["shadow"], 20)
    c.box((x, y, x + w, y + h), p["panel"], 20)
    chrome(c, x, y, w, "风箱 · 自动演奏器", p)
    bx, bw, by = x + 30, w - 60, y + 73
    c.box((bx, by, bx + bw, by + 173), p["hero"], 16)
    c.text(bx + 28, by + 20, "待机 · 游戏窗口激活后可启动", 15, p["hero_muted"])
    c.text(bx + 28, by + 53, "星河之夜", 32, p["hero_text"], bold=True)
    c.text(bx + 29, by + 104, "原调  ·  96 BPM  ·  第 1 / 8 首", 16, p["hero_muted"])
    button(c, bx + bw - 169, by + 61, 138, "开始演奏", p, True, 51)
    c.line((bx + 28, by + 148, bx + bw - 28, by + 148), p["hero_line"], 4)
    c.line((bx + 28, by + 148, bx + bw * .37, by + 148), p["warm"], 4)
    c.circle((bx + bw * .37 - 5, by + 143, bx + bw * .37 + 5, by + 153), p["warm"])
    c.text(bx, by + 202, "游戏按键预览", 18, p["text"], bold=True)
    c.text(bx + bw - 171, by + 204, "当前配置：默认口琴", 13, p["muted"])
    keybed(c, bx, by + 240, bw, p)
    c.text(bx, by + 370, "鼠标修饰（按住生效，松开恢复）", 16, p["text"], bold=True)
    mouse = [("左键", "降调"), ("中键", "半音"), ("右键", "升调")]
    mw = (bw - 20) / 3
    for i, (key, mode) in enumerate(mouse):
        xx = bx + i * (mw + 10)
        c.box((xx, by + 407, xx + mw, by + 478), p["sub"], 11, p["line"])
        c.text(xx + 15, by + 417, key, 14, p["muted"])
        c.text(xx + 15, by + 439, mode, 20, p["text"], bold=True)
    c.box((bx, by + 503, bx + bw, by + 569), p["sub"], 11)
    c.text(bx + 17, by + 512, "全局热键", 14, p["muted"])
    c.text(bx + 17, by + 536, "启停  F8       上一首  F6       下一首  F7", 16, p["text"], bold=True)
    c.text(bx + bw - 88, by + 524, "修改 ›", 15, p["accent"], bold=True)
    c.text(bx, by + 584, "播放列表", 18, p["text"], bold=True)
    playlist_row(c, bx, by + 621, bw, 1, "星河之夜", "03:42", p, True)
    playlist_row(c, bx, by + 677, bw, 2, "山海慢板", "02:57", p)
    playlist_row(c, bx, by + 733, bw, 3, "纸飞机", "04:10", p)


PALETTES = {
    "paper": dict(bg="#E1EAE6", panel="#FBFCF9", chrome="#F4F7F4", rail="#EBF0EC",
                  sub="#F1F5F1", score="#FFFFFF", wave="#EAF1EF", wave_text="#59767D",
                  text="#17343B", muted="#668187", accent="#2362BA", on="#FFFFFF",
                  warm="#D07450", line="#D5E1DC", key="#FFFFFF", shadow="#C6D5D0",
                  hero="#173C48", hero_text="#F8FBF5", hero_muted="#B7D4D3", hero_line="#547982"),
    "console": dict(bg="#071D25", panel="#102B33", chrome="#183841", rail="#163A43",
                    sub="#183A43", score="#15343C", wave="#0A2028", wave_text="#91B7B8",
                    text="#EFF8F5", muted="#92B3B5", accent="#74D7C4", on="#102B33",
                    warm="#F5B85C", line="#315660", key="#21414A", shadow="#04151B",
                    hero="#213E48", hero_text="#F1FBF6", hero_muted="#A9C8CA", hero_line="#44636C"),
    "cassette": dict(bg="#E8E1D0", panel="#FFF8E8", chrome="#F4E9CE", rail="#F4E1B5",
                     sub="#FFF0D1", score="#FFFEF6", wave="#182E4A", wave_text="#C6D5E3",
                     text="#1D3150", muted="#687689", accent="#EE6047", on="#FFFFFF",
                     warm="#D79B31", line="#DCCCA9", key="#FFFCF3", shadow="#CEC3AB",
                     hero="#1D3150", hero_text="#FFF7E7", hero_muted="#CED8E0", hero_line="#68778E"),
}


def make(variant, label, tagline, index):
    p = PALETTES[variant]
    c = Canvas(p["bg"])
    # The board is intentionally a comparison of two independent executables.
    c.text(48, 30, f"{index}  {label}", 38, p["text"], bold=True)
    c.text(48, 83, tagline, 16, p["muted"])
    c.text(48, 126, "曲谱转换器", 17, p["text"], bold=True)
    c.text(918, 126, "自动演奏器", 17, p["text"], bold=True)
    converter(c, 48, 159, 830, 865, p, variant)
    player(c, 918, 159, 830, 865, p, variant)
    c.save(f"preview-{variant}.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    make("paper", "谱台", "冷纸色与蓝墨。重点放在听写、校对与长期阅读。", "A")
    make("console", "夜航控制台", "深海绿与暖黄。适合边看游戏边使用的演奏控制台。", "B")
    make("cassette", "磁带录音室", "复古奶油黄、海军蓝与珊瑚红。更轻快，更有游戏感。", "C")
