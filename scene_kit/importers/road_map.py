"""图像导入器 —— 从标记图片中提取路网结构并挂载到世界。

本模块属于 SK 的「场景导入」能力：把一张人工标记过的地图图片转换成世界里的路网。
它不做数学计算，只做「图片 → 结构数据」的提取与整理，因此依赖图像处理库
（scikit-image / Pillow）而非数学内核。

来源：从 CNO 的 ``generate_roadsNetwork_by_importImage`` 适配迁移。原始实现中的
边界检查缺失、整数类型未转换等问题已在本实现中修正；预览绘图依赖已移除。

使用方式::

    from scene_kit.importers.road_map import extract_road_network_from_image

    roads = extract_road_network_from_image(
        origin_image="map.png",
        signed_image="map_marked.png",
    )
    print(len(roads["junctions"]), "个交叉点")
    print(len(roads["edges"]), "条道路边")
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

__all__ = ["extract_road_network_from_image"]

# 八邻域偏移
_NEIGHBOR_OFFSETS: tuple[tuple[int, int], ...] = tuple(
    (row_offset, col_offset)
    for row_offset in range(-1, 2)
    for col_offset in range(-1, 2)
    if row_offset != 0 or col_offset != 0
)


def extract_road_network_from_image(
    origin_image: str | Path,
    signed_image: str | Path,
    merge_junction_threshold: int = 10,
    min_edge_pixel_length: int = 10,
    interpolate_distance: float = 4.0,
) -> dict:
    """从原始图与标记图中提取路网结构。

    算法步骤：

    1. 在标记图中找出被标红的像素（人工描出的道路）；
    2. 对红色区域做膨胀、连通组件分割，再逐组件骨架化；
    3. 检测骨架上的交叉点与端点，并融合相互过近的交叉点；
    4. 沿骨架像素逐条追踪出道路边（记录每条的像素路径）；
    5. 沿每条边的像素路径按距离插值，生成路由点。

    Args:
        origin_image: 原始图片路径（当前仅用于校验可读性，不参与提取）。
        signed_image: 标记图片路径，其中道路被涂成纯红 ``(255, 0, 0)``。
        merge_junction_threshold: 融合相邻交叉点的距离阈值（像素）。
        min_edge_pixel_length: 道路边的最小像素长度，短于此值的边被丢弃。
        interpolate_distance: 路由点插值间距（像素）。

    Returns:
        dict: 路网结构，含三个键：

        - ``junctions``: ``{id: (行, 列)}`` 交叉点/端点像素坐标；
        - ``edges``: ``{id: {"id", "endpoints", "pixels"}}`` 道路边，
          ``endpoints`` 为两个交叉点 id，``pixels`` 为该边的像素路径序列；
        - ``interpolated_nodes``: ``{id: (node_id, edge_id, neighbor_pair, (行, 列))}``
          路由点，``neighbor_pair`` 为该点在路径上前后相邻的节点 id。

    Raises:
        ImportError: 未安装图像处理可选依赖。
        ValueError: 标记图中未找到任何红色像素。
    """
    try:
        from PIL import Image
        from skimage import filters, measure, morphology
        from skimage import io as skio
    except ImportError as exc:  # pragma: no cover - 依赖缺失时的显式提示
        raise ImportError(
            "图像导入需要可选依赖 scikit-image 与 Pillow，请安装：uv sync --extra importers"
        ) from exc

    origin_path = Path(origin_image)
    signed_path = Path(signed_image)
    if not origin_path.is_file():
        raise FileNotFoundError(f"原始图片不存在：{origin_path}")
    if not signed_path.is_file():
        raise FileNotFoundError(f"标记图片不存在：{signed_path}")

    # 大图不受默认像素上限限制
    original_max_pixels = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None
    try:
        image_signed = skio.imread(signed_path)
        skeleton = _extract_skeleton(image_signed, morphology, measure)

        # 骨架转灰度后做二值化，得到道路像素掩码
        if skeleton.ndim == 3:
            from skimage import color

            gray = color.rgb2gray(skeleton)
        else:
            gray = skeleton
        road_mask = gray > filters.threshold_otsu(gray)

        junctions = _detect_junctions(road_mask)
        junctions = _merge_near_junctions(junctions, merge_junction_threshold)

        edges, id_map = _trace_edges(road_mask, junctions, min_edge_pixel_length)
        interpolated_nodes = _build_interpolated_nodes(edges, interpolate_distance)
    finally:
        Image.MAX_IMAGE_PIXELS = original_max_pixels

    return {
        "junctions": {index: coordinate for index, coordinate in enumerate(junctions)},
        "edges": {
            index: {"id": edge_id, "endpoints": endpoints, "pixels": pixels}
            for index, (edge_id, endpoints, pixels) in enumerate(edges)
        },
        "interpolated_nodes": {
            index: node for index, node in enumerate(interpolated_nodes)
        },
        "skeleton_id_map": id_map,
        "road_mask": road_mask,
    }


def _extract_skeleton(image_signed: np.ndarray, morphology, measure) -> np.ndarray:
    """从标记图中提取道路骨架（红像素 → 膨胀 → 连通组件 → 骨架化）。"""
    if image_signed.ndim == 3:
        marked = np.all(image_signed[:, :, :3] == [255, 0, 0], axis=-1)
    else:
        marked = image_signed > 0
    if not marked.any():
        raise ValueError("标记图中未找到红色像素 (255, 0, 0)，无法提取道路。")

    dilated = morphology.dilation(marked, np.ones((3, 3), dtype=bool))
    labeled = measure.label(dilated)
    skeleton = np.zeros_like(marked)
    for label_index in range(1, labeled.max() + 1):
        skeleton |= morphology.skeletonize(labeled == label_index)
    return skeleton


def _detect_junctions(skeleton: np.ndarray) -> list[tuple[int, int]]:
    """检测骨架上的交叉点（邻居数 ≥3）与端点（邻居数 =1）。"""
    from scipy.ndimage import convolve

    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
    neighbor_count = convolve(skeleton.astype(int), kernel, mode="constant", cval=0)

    junctions: list[tuple[int, int]] = []
    rows, cols = skeleton.shape
    for row in range(1, rows - 1):
        for col in range(1, cols - 1):
            if not skeleton[row, col]:
                continue
            count = neighbor_count[row, col]
            if count >= 3 or count == 1:
                junctions.append((row, col))
    return junctions


def _merge_near_junctions(
    junctions: list[tuple[int, int]], threshold: int
) -> list[tuple[int, int]]:
    """把相互距离小于阈值的交叉点融合为一个（取离均值最近的那个像素）。"""
    if not junctions:
        return []

    junction_array = np.asarray(junctions)
    merged: list[tuple[int, int]] = []
    processed = np.zeros(len(junctions), dtype=bool)

    for index, junction in enumerate(junction_array):
        if processed[index]:
            continue
        distances = np.linalg.norm(junction_array - junction, axis=1)
        close_by = distances < threshold
        centroid = junction_array[close_by].mean(axis=0)
        offsets = np.linalg.norm(junction_array[close_by] - centroid, axis=1)
        nearest = junction_array[close_by][int(np.argmin(offsets))]
        merged.append((int(nearest[0]), int(nearest[1])))
        processed[close_by] = True

    return merged


def _trace_edges(
    road_mask: np.ndarray,
    junctions: list[tuple[int, int]],
    min_edge_pixel_length: int,
) -> tuple[list[tuple[int, tuple[int, int], list[tuple[int, int]]]], np.ndarray]:
    """沿骨架像素追踪道路边。

    像素标记约定：``-1`` 待填充道路像素，``-2`` 非道路像素，``-3`` 交叉点/端点，
    ``-4`` 边的起止像素，``>=0`` 已归属某条边的像素。

    Returns:
        (edges, id_map)：edges 为 ``(edge_id, (端点1, 端点2), 像素序列)`` 列表；
        id_map 为像素级边归属图。
    """
    rows, cols = road_mask.shape
    id_map = np.full((rows, cols), -2, dtype=int)
    id_map[road_mask] = -1
    for row, col in junctions:
        id_map[row, col] = -3

    # 标记每条的边的起止像素（交叉点周围的待填充像素）
    for row, col in junctions:
        for row_offset, col_offset in _NEIGHBOR_OFFSETS:
            neighbor_row, neighbor_col = row + row_offset, col + col_offset
            if not _in_bounds(neighbor_row, neighbor_col, rows, cols):
                continue
            if id_map[neighbor_row, neighbor_col] == -1:
                id_map[neighbor_row, neighbor_col] = -4

    edges: list[tuple[int, tuple[int, int], list[tuple[int, int]]]] = []
    edge_id = 0

    for junction_index, (row, col) in enumerate(junctions):
        for row_offset, col_offset in _NEIGHBOR_OFFSETS:
            start_row, start_col = row + row_offset, col + col_offset
            if not _in_bounds(start_row, start_col, rows, cols):
                continue
            if id_map[start_row, start_col] != -4:
                continue

            first_endpoint = junction_index
            second_endpoint: int | None = None
            edge_pixels: list[tuple[int, int]] = []
            cur_row, cur_col = start_row, start_col
            tracing = True

            while tracing:
                if not _in_bounds(cur_row, cur_col, rows, cols):
                    # 越界：把当前交叉点作为远端端点收口
                    second_endpoint, _ = _nearest_junction(
                        (cur_row, cur_col), junctions
                    )
                    break

                neighbors = [
                    (cur_row + dr, cur_col + dc) for dr, dc in _NEIGHBOR_OFFSETS
                ]
                neighbor_values = [
                    id_map[nr, nc] if _in_bounds(nr, nc, rows, cols) else -2
                    for nr, nc in neighbors
                ]
                current_value = id_map[cur_row, cur_col]

                if current_value in (-1, -4):
                    id_map[cur_row, cur_col] = edge_id
                    edge_pixels.append((cur_row, cur_col))

                    if -4 in neighbor_values:
                        cur_row, cur_col = neighbors[neighbor_values.index(-4)]
                    elif -1 in neighbor_values:
                        cur_row, cur_col = neighbors[neighbor_values.index(-1)]
                    else:
                        # 走到别的边或非道路区，用最近交叉点收口
                        second_endpoint, _ = _nearest_junction(
                            (cur_row, cur_col), junctions
                        )
                        break

                    # 抵达另一个交叉点／端点像素时结束本条边
                    if current_value == -4:
                        cross_index = _find_crossing(
                            neighbors, neighbor_values, (row, col)
                        )
                        if cross_index is not None:
                            second_endpoint = cross_index
                            break
                else:
                    break

            if second_endpoint is None:
                continue
            if len(edge_pixels) < min_edge_pixel_length:
                continue

            edges.append((edge_id, (first_endpoint, second_endpoint), edge_pixels))
            edge_id += 1

    return edges, id_map


def _find_crossing(
    neighbors: list[tuple[int, int]],
    neighbor_values: list[int],
    origin: tuple[int, int],
) -> int | None:
    """若当前像素的邻居里存在交叉点，返回该交叉点在本轮搜索中的序号。"""
    if -3 not in neighbor_values:
        return None
    crossing_index = neighbor_values.index(-3)
    if neighbors[crossing_index] == origin:
        return None
    return crossing_index


def _nearest_junction(
    point: tuple[int, int], junctions: list[tuple[int, int]]
) -> tuple[int, float]:
    """返回距目标点最近的交叉点序号与距离。"""
    best_index, best_distance = -1, float("inf")
    for index, junction in enumerate(junctions):
        distance = float(np.linalg.norm(np.asarray(junction) - np.asarray(point)))
        if distance < best_distance:
            best_index, best_distance = index, distance
    return best_index, best_distance


def _in_bounds(row: int, col: int, rows: int, cols: int) -> bool:
    """像素坐标是否落在图像范围内。"""
    return 0 <= row < rows and 0 <= col < cols


def _build_interpolated_nodes(
    edges: list[tuple[int, tuple[int, int], list[tuple[int, int]]]],
    interpolate_distance: float,
) -> list[tuple[int, int, tuple[int, int], tuple[float, float]]]:
    """沿每条边的像素路径按间距插值，生成路由点。"""
    interpolated_nodes: list[tuple[int, int, tuple[int, int], tuple[float, float]]] = []
    for edge_id, endpoints, pixels in edges:
        points = _interpolate_along_path(pixels, interpolate_distance)
        last_index = len(points) - 1
        for index, point in enumerate(points):
            if index == 0:
                neighbor_pair = (endpoints[0], index + 1)
            elif index == last_index:
                neighbor_pair = (index - 1, endpoints[1])
            else:
                neighbor_pair = (index - 1, index + 1)
            interpolated_nodes.append((index, edge_id, neighbor_pair, point))
    return interpolated_nodes


def _interpolate_along_path(
    pixels: list[tuple[int, int]], distance: float
) -> list[tuple[float, float]]:
    """沿像素路径按给定间距线性插值。"""
    if len(pixels) < 2 or distance <= 0:
        return []

    cumulative = [0.0]
    for index in range(1, len(pixels)):
        previous_row, previous_col = pixels[index - 1]
        row, col = pixels[index]
        cumulative.append(
            cumulative[-1]
            + float(np.hypot(row - previous_row, col - previous_col))
        )

    total = cumulative[-1]
    if total <= 0:
        return []

    num_points = int(total / distance)
    if num_points <= 0:
        return []
    adjusted = distance + (total % distance) / num_points

    points: list[tuple[float, float]] = []
    for step in range(1, num_points):
        target = step * adjusted
        for index in range(1, len(cumulative)):
            if cumulative[index] < target:
                continue
            segment = cumulative[index] - cumulative[index - 1]
            ratio = 0.0 if segment == 0 else (target - cumulative[index - 1]) / segment
            previous_row, previous_col = pixels[index - 1]
            row, col = pixels[index]
            points.append(
                (
                    previous_row + ratio * (row - previous_row),
                    previous_col + ratio * (col - previous_col),
                )
            )
            break
    return points
