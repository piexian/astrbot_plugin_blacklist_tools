import asyncio
import base64
import io
import os
from typing import Optional, Tuple, Dict
from astrbot.api import logger
from PIL import Image, ImageDraw, ImageFont


class TextToImageConverter:
    def __init__(self):
        self._font_cache: Dict[int, ImageFont.FreeTypeFont] = {}
        self._default_font_path = self._get_default_font_path()
        self._default_font = None

    def _get_default_font_path(self) -> str:
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        font_path = os.path.join(
            plugin_dir, "../", "font", "NotoSerifCJKsc-Regular.otf"
        )
        return font_path

    def _load_font(self, font_size: int) -> ImageFont.FreeTypeFont:
        if font_size not in self._font_cache:
            try:
                if self._default_font_path and os.path.exists(self._default_font_path):
                    font = ImageFont.truetype(self._default_font_path, font_size)
                else:
                    font = ImageFont.load_default()
                    logger.warning("使用系统默认字体")
                self._font_cache[font_size] = font
            except IOError as e:
                logger.error(f"加载字体失败: {e}")
                self._font_cache[font_size] = ImageFont.load_default()
            except Exception as e:
                logger.error(f"加载字体时发生未知错误: {e}")
                self._font_cache[font_size] = ImageFont.load_default()
        return self._font_cache[font_size]

    def text_to_image(
        self,
        text: str,
        enable_markdown: bool = False,
        font_size: int = 24,
        font_color: Tuple[int, int, int] = (255, 255, 255),
        bg_color: Tuple[int, int, int] = (0, 0, 0),
        width: Optional[int] = None,
        padding: int = 20,
        max_width: int = 1200,
        min_width: int = 400,
        line_spacing: int = 5,
        image_format: str = "PNG",
        quality: int = 95,
    ) -> Optional[str]:
        """
        将文本转换为图片

        Args:
            text: 要转换的文本
            enable_markdown: 是否启用Markdown支持（暂未实现）
            font_size: 字体大小
            font_color: 字体颜色，RGB元组
            bg_color: 背景颜色，RGB元组
            width: 图片宽度，如果为None则自动计算
            padding: 内边距
            max_width: 最大图片宽度
            min_width: 最小图片宽度
            line_spacing: 行间距
            image_format: 图片格式，如'PNG', 'JPEG'等
            quality: 图片质量（1-100），仅对JPEG格式有效

        Returns:
            Optional[str]: base64编码的图片数据，失败时返回None
        """
        if not text or not text.strip():
            logger.warning("输入文本为空")
            return None

        try:
            # 加载字体
            font = self._load_font(font_size)

            lines = text.strip().split("\n")

            # 计算文本尺寸
            line_height = font_size + line_spacing
            text_height = len(lines) * line_height
            max_line_width = self._calculate_text_width(lines, font)

            # 计算图片尺寸
            if width is None:
                calculated_width = max_line_width + padding * 2
                width = max(min_width, min(calculated_width, max_width))

            img_height = max(
                text_height + padding * 2, font_size + padding * 2
            )  # 确保最小高度

            # 创建图片并绘制文本
            img = Image.new("RGB", (width, img_height), bg_color)
            draw = ImageDraw.Draw(img)

            # 绘制文本
            y = padding
            for line in lines:
                if line.strip():
                    draw.text((padding, y), line, font=font, fill=font_color)
                y += line_height

            # 保存图片
            buffer = io.BytesIO()
            save_kwargs = {"format": image_format}
            if image_format.upper() == "JPEG":
                save_kwargs["quality"] = quality

            img.save(buffer, **save_kwargs)
            img_data = buffer.getvalue()
            base64_data = base64.b64encode(img_data).decode("utf-8")

            return base64_data
        except IOError as e:
            logger.error(f"图片IO操作失败: {e}")
            return None
        except ValueError as e:
            logger.error(f"参数值错误: {e}")
            return None
        except Exception as e:
            logger.error(f"生成图片时发生未知错误: {e}")
            return None

    def _calculate_text_width(self, lines: list, font: ImageFont.FreeTypeFont) -> int:
        max_line_width = 0

        try:
            for line in lines:
                if not line.strip():
                    continue

                line_width = font.getlength(line)
                max_line_width = max(max_line_width, int(line_width))
        except Exception as e:
            logger.error(f"计算文本宽度时发生错误: {e}")
            max_line_width = (
                max(len(line) * 24 // 2 for line in lines) if lines else 100
            )

        return max_line_width

    async def async_text_to_image(
        self,
        text: str,
        enable_markdown: bool = False,
        font_size: int = 24,
        font_color: Tuple[int, int, int] = (255, 255, 255),
        bg_color: Tuple[int, int, int] = (0, 0, 0),
        width: Optional[int] = None,
        padding: int = 20,
        max_width: int = 1200,
        min_width: int = 400,
        line_spacing: int = 5,
        image_format: str = "PNG",
        quality: int = 95,
    ) -> Optional[str]:
        return await asyncio.to_thread(
            self.text_to_image,
            text,
            enable_markdown,
            font_size,
            font_color,
            bg_color,
            width,
            padding,
            max_width,
            min_width,
            line_spacing,
            image_format,
            quality,
        )


_converter = TextToImageConverter()


async def text_to_image(
    text: str,
    enable_markdown: bool = False,
    font_size: int = 24,
    font_color: Tuple[int, int, int] = (255, 255, 255),
    bg_color: Tuple[int, int, int] = (0, 0, 0),
    width: Optional[int] = None,
    padding: int = 20,
    max_width: int = 1200,
    min_width: int = 400,
    line_spacing: int = 5,
    image_format: str = "PNG",
    quality: int = 95,
) -> Optional[str]:
    return await _converter.async_text_to_image(
        text,
        enable_markdown,
        font_size,
        font_color,
        bg_color,
        width,
        padding,
        max_width,
        min_width,
        line_spacing,
        image_format,
        quality,
    )
