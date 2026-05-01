import io
import textwrap
from PIL import Image, ImageDraw, ImageFont
from config import VISUAL_TEMPLATES


# ─────────────────────────────────────────
# НАЛАШТУВАННЯ
# ─────────────────────────────────────────

IMG_WIDTH  = 1280
IMG_HEIGHT = 720
FONT_PATH  = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PATH_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


# ─────────────────────────────────────────
# БАЗОВА ГЕНЕРАЦІЯ КАРТИНКИ
# ─────────────────────────────────────────

def generate_post_image(
    title: str,
    body: str,
    rubric: str,
    persona_name: str,
    template: dict,
) -> bytes:
    """
    Генерує картинку для поста через Pillow.
    Повертає PNG у вигляді bytes.
    """
    bg_color     = _hex_to_rgb(template["bg"])
    accent_color = _hex_to_rgb(template["accent"])
    white        = (255, 255, 255)
    muted        = (180, 180, 180)

    img  = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), bg_color)
    draw = ImageDraw.Draw(img)

    # ── Акцентна смуга зліва ──
    draw.rectangle([(0, 0), (8, IMG_HEIGHT)], fill=accent_color)

    # ── Великий emoji шаблону (фон) ──
    font_emoji_bg = _load_font(FONT_PATH, 320)
    draw.text(
        (IMG_WIDTH - 380, IMG_HEIGHT // 2 - 180),
        template["emoji"],
        font=font_emoji_bg,
        fill=(*accent_color, 18),  # дуже прозорий
    )

    # ── Рубрика (верхній лівий) ──
    font_rubric = _load_font(FONT_PATH, 28)
    draw.text((48, 48), rubric.upper(), font=font_rubric, fill=accent_color)

    # ── Лінія під рубрикою ──
    draw.line([(48, 90), (IMG_WIDTH - 48, 90)], fill=(*accent_color, 80), width=1)

    # ── Заголовок (великий) ──
    font_title = _load_font(FONT_PATH, 64)
    wrapped_title = textwrap.fill(title, width=28)
    draw.text((48, 120), wrapped_title, font=font_title, fill=white)

    # ── Підзаголовок / тіло ──
    title_lines = wrapped_title.count("\n") + 1
    body_y = 120 + title_lines * 76 + 20

    font_body = _load_font(FONT_PATH_REGULAR, 36)
    wrapped_body = textwrap.fill(body, width=52)
    draw.text((48, body_y), wrapped_body, font=font_body, fill=muted)

    # ── Нижня панель ──
    draw.rectangle(
        [(0, IMG_HEIGHT - 80), (IMG_WIDTH, IMG_HEIGHT)],
        fill=tuple(max(0, c - 15) for c in bg_color),
    )

    # ── Персона (нижній лівий) ──
    font_persona = _load_font(FONT_PATH, 26)
    draw.text(
        (48, IMG_HEIGHT - 54),
        f"автор: {persona_name}",
        font=font_persona,
        fill=accent_color,
    )

    # ── Назва каналу (нижній правий) ──
    channel_text = "ФінПро для дітей"
    bbox = draw.textbbox((0, 0), channel_text, font=font_persona)
    text_width = bbox[2] - bbox[0]
    draw.text(
        (IMG_WIDTH - text_width - 48, IMG_HEIGHT - 54),
        channel_text,
        font=font_persona,
        fill=muted,
    )

    # ── Акцентна крапка біля назви каналу ──
    draw.ellipse(
        [
            (IMG_WIDTH - text_width - 64, IMG_HEIGHT - 46),
            (IMG_WIDTH - text_width - 52, IMG_HEIGHT - 34),
        ],
        fill=accent_color,
    )

    # ── Зберігаємо в bytes ──
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer.read()


# ─────────────────────────────────────────
# ГРАФІК ДЛЯ #БіржаДляДітей
# ─────────────────────────────────────────

def generate_chart_image(
    labels: list,
    values: list,
    title: str,
    template: dict,
) -> bytes:
    """
    Генерує простий bar chart через Pillow (без matplotlib).
    labels — назви стовпців, values — числа.
    """
    bg_color     = _hex_to_rgb(template["bg"])
    accent_color = _hex_to_rgb(template["accent"])
    white        = (255, 255, 255)
    muted        = (160, 160, 160)

    img  = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), bg_color)
    draw = ImageDraw.Draw(img)

    font_title = _load_font(FONT_PATH, 48)
    font_label = _load_font(FONT_PATH_REGULAR, 28)
    font_value = _load_font(FONT_PATH, 32)

    # ── Заголовок ──
    draw.text((48, 40), title, font=font_title, fill=white)
    draw.line([(48, 100), (IMG_WIDTH - 48, 100)], fill=accent_color, width=2)

    # ── Параметри графіку ──
    chart_x      = 80
    chart_y      = 560
    chart_width  = IMG_WIDTH - 160
    chart_height = 380
    bar_gap      = 30
    n            = len(labels)
    bar_width    = (chart_width - bar_gap * (n - 1)) // n

    if not values:
        return _save_image(img)

    max_val = max(abs(v) for v in values) or 1

    for i, (label, value) in enumerate(zip(labels, values)):
        x = chart_x + i * (bar_width + bar_gap)

        # Висота стовпця пропорційна значенню
        bar_h = int((abs(value) / max_val) * chart_height * 0.85)
        color = accent_color if value >= 0 else (255, 80, 80)

        # Стовпець
        draw.rectangle(
            [(x, chart_y - bar_h), (x + bar_width, chart_y)],
            fill=color,
        )

        # Заокруглений верх (імітація)
        draw.ellipse(
            [(x, chart_y - bar_h - 8), (x + bar_width, chart_y - bar_h + 8)],
            fill=color,
        )

        # Значення над стовпцем
        val_text = f"{value:+.1f}%" if isinstance(value, float) else str(value)
        bbox = draw.textbbox((0, 0), val_text, font=font_value)
        val_w = bbox[2] - bbox[0]
        draw.text(
            (x + bar_width // 2 - val_w // 2, chart_y - bar_h - 44),
            val_text,
            font=font_value,
            fill=white,
        )

        # Підпис під стовпцем
        bbox = draw.textbbox((0, 0), label, font=font_label)
        lbl_w = bbox[2] - bbox[0]
        draw.text(
            (x + bar_width // 2 - lbl_w // 2, chart_y + 12),
            label,
            font=font_label,
            fill=muted,
        )

    # ── Базова лінія ──
    draw.line([(chart_x, chart_y), (chart_x + chart_width, chart_y)], fill=muted, width=2)

    # ── Лого ──
    font_logo = _load_font(FONT_PATH, 24)
    draw.text((IMG_WIDTH - 280, IMG_HEIGHT - 40), "ФінПро для дітей", font=font_logo, fill=muted)

    return _save_image(img)


# ─────────────────────────────────────────
# КАРТИНКА ДЛЯ КВІЗУ
# ─────────────────────────────────────────

def generate_quiz_image(question: str, template: dict) -> bytes:
    """Картинка з питанням для #ФінКвіз."""
    bg_color     = _hex_to_rgb(template["bg"])
    accent_color = _hex_to_rgb(template["accent"])
    white        = (255, 255, 255)

    img  = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), bg_color)
    draw = ImageDraw.Draw(img)

    # Акцентні кути
    size = 60
    draw.rectangle([(0, 0), (size, 8)], fill=accent_color)
    draw.rectangle([(0, 0), (8, size)], fill=accent_color)
    draw.rectangle([(IMG_WIDTH - size, 0), (IMG_WIDTH, 8)], fill=accent_color)
    draw.rectangle([(IMG_WIDTH - 8, 0), (IMG_WIDTH, size)], fill=accent_color)

    # Заголовок рубрики
    font_rubric = _load_font(FONT_PATH, 36)
    draw.text((48, 48), "🎮 #ФінКвіз", font=font_rubric, fill=accent_color)

    # Велике питання по центру
    font_q = _load_font(FONT_PATH, 54)
    wrapped = textwrap.fill(question, width=32)
    lines   = wrapped.split("\n")
    total_h = len(lines) * 64
    start_y = (IMG_HEIGHT - total_h) // 2 - 20

    for i, line in enumerate(lines):
        bbox  = draw.textbbox((0, 0), line, font=font_q)
        line_w = bbox[2] - bbox[0]
        draw.text(
            ((IMG_WIDTH - line_w) // 2, start_y + i * 68),
            line,
            font=font_q,
            fill=white,
        )

    # Підказка знизу
    font_hint = _load_font(FONT_PATH_REGULAR, 28)
    hint = "Голосуй нижче 👇"
    bbox  = draw.textbbox((0, 0), hint, font=font_hint)
    hint_w = bbox[2] - bbox[0]
    draw.text(
        ((IMG_WIDTH - hint_w) // 2, IMG_HEIGHT - 80),
        hint,
        font=font_hint,
        fill=accent_color,
    )

    return _save_image(img)


# ─────────────────────────────────────────
# ДОПОМІЖНА ФУНКЦІЯ
# ─────────────────────────────────────────

def _save_image(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer.read()
