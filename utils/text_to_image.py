import logging
import base64
import io
import asyncio
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("astrbot")

# 字体缓存
_font_cache = {}


def base64_to_data_url(base64_data, mime_type="image/png"):
    """
    将base64数据转换为data URL
    Args:
        base64_data: base64编码的数据
        mime_type: MIME类型，默认为image/png
    Returns:
        data URL字符串
    """
    return f"data:{mime_type};base64,{base64_data}"


async def _load_font_async(font_size):
    """
    异步加载字体，使用缓存
    Args:
        font_size: 字体大小
    Returns:
        字体对象
    """
    # 检查缓存
    cache_key = f"{font_size}"
    if cache_key in _font_cache:
        return _font_cache[cache_key]

    # 在线程池中执行字体加载
    loop = asyncio.get_event_loop()

    def _load_font():
        font = None
        font_paths = [
            "msyh.ttc",  # Windows 微软雅黑
            "NotoSansCJK-Regular.ttc",  # Linux 思源黑体
            "PingFang.ttc",  # macOS 苹方
            "Arial.ttf",  # 通用 Arial
        ]

        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except Exception:
                continue

        # 如果没有找到字体，使用默认字体
        if font is None:
            font = ImageFont.load_default()

        return font

    try:
        font = await loop.run_in_executor(None, _load_font)
        # 缓存字体
        _font_cache[cache_key] = font
        return font
    except Exception as e:
        logger.error(f"加载字体失败: {e}")
        return ImageFont.load_default()


async def text_to_image(
    text,
    enable_markdown=False,
    font_size=24,
    font_color=(255, 255, 255),  # 白色字体
    bg_color=(0, 0, 0),  # 黑色背景
    width=None,  # 默认为None，表示自动计算宽度
    padding=20,
    max_width=1200,  # 最大宽度限制
    min_width=400,  # 最小宽度限制
):
    """
    将文本转换为图片（异步版本）
    Args:
        text: 要转换的文本
        enable_markdown: 是否启用Markdown支持（暂未实现）
        font_size: 字体大小
        font_color: 字体颜色
        bg_color: 背景颜色
        width: 图片宽度
        padding: 内边距
    Returns:
        base64编码的图片数据
    """
    try:
        # 异步加载字体
        font = await _load_font_async(font_size)

        # 计算文本高度
        lines = text.split("\n")
        line_height = font_size + 5
        text_height = len(lines) * line_height

        # 在线程池中执行文本宽度计算
        loop = asyncio.get_event_loop()

        def _calculate_text_width():
            max_line_width = 0
            # 创建一个临时图片用于计算文本宽度
            temp_img = Image.new("RGB", (1, 1), bg_color)
            temp_draw = ImageDraw.Draw(temp_img)

            for line in lines:
                # 使用textbbox获取文本边界框
                bbox = temp_draw.textbbox((0, 0), line, font=font)
                line_width = bbox[2] - bbox[0]  # 右边界 - 左边界
                max_line_width = max(max_line_width, line_width)

            return max_line_width

        max_line_width = await loop.run_in_executor(None, _calculate_text_width)

        # 计算图片宽度
        if width is None:
            # 自动计算宽度：文本最大宽度 + 左右内边距
            calculated_width = max_line_width + padding * 2
            # 确保宽度在最小和最大限制之间
            width = max(min_width, min(calculated_width, max_width))

        # 在线程池中执行图片创建和文本绘制
        def _create_image():
            # 创建图片
            img_height = text_height + padding * 2
            img = Image.new("RGB", (width, img_height), bg_color)
            draw = ImageDraw.Draw(img)

            # 绘制文本
            y = padding
            for line in lines:
                draw.text((padding, y), line, font=font, fill=font_color)
                y += line_height

            # 转换为base64
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            img_data = buffer.getvalue()
            base64_data = base64.b64encode(img_data).decode("utf-8")

            return base64_data

        base64_data = await loop.run_in_executor(None, _create_image)
        return base64_data
    except Exception as e:
        logger.error(f"文本转图片失败: {e}")
        return None
