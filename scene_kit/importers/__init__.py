"""图像导入子模块 —— 把外部素材（图片）转换为世界里可挂载的结构数据。

这类能力属于「场景导入」而非「数学计算」：它把一张图片变成世界里的路网、地形等
结构，依赖图像处理库；数学内核不在这里，数学算法请用 MathEngine。

当前提供：

- :func:`scene_kit.importers.road_map.extract_road_network_from_image`
  从人工标记的图片中提取路网（交叉点 / 道路边 / 路由点）。
- :func:`scene_kit.importers.road_map.build_path_geometry`
  把提取结果适配为可挂载的 PathGeometry（构造与挂载分离的适配器）。
"""

from scene_kit.importers.road_map import (
    build_path_geometry,
    extract_road_network_from_image,
)

__all__ = ["extract_road_network_from_image", "build_path_geometry"]
