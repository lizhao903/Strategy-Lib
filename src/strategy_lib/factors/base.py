"""Factor 基类。

每个因子声明：参数、所需列、方向（1=高值看多/-1=高值看空）。
单 asset 接口：compute(df) -> Series
多 asset 接口（cross-sectional 研究）：compute_panel(panel) -> DataFrame (index=time, cols=symbols)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

import pandas as pd


class Factor(ABC):
    """因子基类。"""

    # 子类必须覆盖
    name: ClassVar[str] = ""
    required_columns: ClassVar[tuple[str, ...]] = ("close",)
    # 1 = 因子值越高越看多，-1 = 越高越看空（用于统一信号方向）
    direction: ClassVar[int] = 1

    def __init__(self, **params) -> None:
        self.params = params
        if not self.name:
            raise NotImplementedError(f"{type(self).__name__} 必须设置 class-level `name`")
        registry.register(self)

    # ---- 子类实现 ----

    @abstractmethod
    def _compute(self, df: pd.DataFrame) -> pd.Series:
        """单 asset 计算。返回与 df.index 对齐的 Series（缺失部分用 NaN）。"""

    # ---- 公共 API ----

    def compute(self, df: pd.DataFrame) -> pd.Series:
        missing = [c for c in self.required_columns if c not in df.columns]
        if missing:
            raise ValueError(f"{self.name}: missing required columns {missing}")
        out = self._compute(df)
        out.name = self.full_name
        return out

    def compute_panel(self, panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """多 asset 计算。返回 wide DataFrame（index=time, columns=symbol）。"""
        cols = {sym: self.compute(df) for sym, df in panel.items()}
        return pd.DataFrame(cols)

    @property
    def full_name(self) -> str:
        if not self.params:
            return self.name
        suffix = "_".join(f"{k}{v}" for k, v in sorted(self.params.items()))
        return f"{self.name}_{suffix}"

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.params})"


class FactorRegistry:
    """因子注册表。用于通过 yaml 配置实例化因子。"""

    def __init__(self) -> None:
        self._classes: dict[str, type[Factor]] = {}

    def register(self, factor: Factor) -> None:
        self._classes[factor.name] = type(factor)

    def get_class(self, name: str) -> type[Factor]:
        if name not in self._classes:
            raise KeyError(f"unknown factor: {name}. registered: {list(self._classes)}")
        return self._classes[name]

    def create(self, name: str, **params) -> Factor:
        return self.get_class(name)(**params)

    def list(self) -> list[str]:
        return sorted(self._classes)


registry = FactorRegistry()
