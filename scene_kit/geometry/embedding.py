"""Embedding —— 结构几何的显式嵌入声明。

「构造与挂载分离」（主设计 §3.8 结论 1/2）：结构（节点坐标 + 连接关系）
由构造侧（数学引擎、图像导入器等）生成；坐标**属于哪个空间、用什么度规**
必须由导入方在这里显式声明，SK 不根据数值范围或 geometry 类型猜测语义。

未声明嵌入（embedding=None）的结构只提供拓扑类查询（邻接、路由跳数、
参数坐标归属），不提供任何长度/距离/坐标解析。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Embedding"]

# SK 内置的度规名（构造 PathGeometry 等时校验；不认识的度规直接拒绝）
KNOWN_METRICS = ("euclidean", "manhattan")


@dataclass(frozen=True)
class Embedding:
    """坐标空间与度规的显式声明。

    Args:
        space: 坐标所属空间的名称标识（如 "pixel"、"world-euclid2"、"latlon"）。
            SK 不解释其含义，只原样携带并投影进需要空间信息的下游。
        metric: 坐标间距离的度规名，限于 KNOWN_METRICS。
        dims: 坐标维度（2 或 3）。
        unit: 长度单位（如 "px"、"m"），仅作标注，SK 不做换算。
        meta: 其余声明性附注（比例尺、原点约定等）。
    """

    space: str
    metric: str = "euclidean"
    dims: int = 2
    unit: str = "unit"
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.metric not in KNOWN_METRICS:
            raise ValueError(
                f"未知度规 {self.metric!r}，SK 内置度规限于 {KNOWN_METRICS}；"
                "其余度规请在构造侧换算后声明。"
            )
        if self.dims not in (2, 3):
            raise ValueError(f"dims 只能是 2 或 3，当前值: {self.dims!r}")
