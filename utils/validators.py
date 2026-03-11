"""贴图尺寸与放置校验工具"""

from .constants import MIN_TEXTURE_SIZE, VALID_TEXTURE_SIZES


def is_power_of_two(n: int) -> bool:
    """判断是否为2的次方"""
    return n > 0 and (n & (n - 1)) == 0


def validate_texture_size(width: int, height: int) -> tuple[bool, str]:
    """
    校验贴图尺寸合法性。
    返回 (是否合法, 错误信息)
    """
    if width < MIN_TEXTURE_SIZE or height < MIN_TEXTURE_SIZE:
        return False, f"尺寸不能小于 {MIN_TEXTURE_SIZE}px"

    if not is_power_of_two(width):
        return False, f"宽度 {width} 不是2的次方"

    if not is_power_of_two(height):
        return False, f"高度 {height} 不是2的次方"

    if width not in VALID_TEXTURE_SIZES:
        return False, f"宽度 {width} 不在支持范围内 (16~2048)"

    if height not in VALID_TEXTURE_SIZES:
        return False, f"高度 {height} 不在支持范围内 (16~2048)"

    return True, ""


def validate_placement(x: int, y: int, width: int, height: int, atlas_size: int) -> tuple[bool, str]:
    """
    校验贴图放置是否越界。
    x, y 为网格坐标（以 GRID_UNIT 为单位），width/height 为像素尺寸。
    """
    from .constants import GRID_UNIT

    grid_w = width // GRID_UNIT
    grid_h = height // GRID_UNIT
    grid_max = atlas_size // GRID_UNIT

    if x < 0 or y < 0:
        return False, "坐标不能为负数"

    if x + grid_w > grid_max:
        return False, f"水平方向越界: {x}+{grid_w} > {grid_max}"

    if y + grid_h > grid_max:
        return False, f"垂直方向越界: {y}+{grid_h} > {grid_max}"

    return True, ""
