"""项目路径集中管理。

所有对项目根目录、配置文件、Web 前端目录的引用统一在此处维护，
避免各模块各自用 ``parents[N]`` 硬编码层级。

支持通过环境变量 ``QUANT_BALANCE_ROOT`` 强制指定项目根目录。
"""

from __future__ import annotations

import os
from pathlib import Path


def _detect_project_root() -> Path:
    """向上查找包含 pyproject.toml 的目录作为项目根目录。"""
    env_root = os.getenv("QUANT_BALANCE_ROOT")
    if env_root:
        return Path(env_root).resolve()

    anchor = Path(__file__).resolve().parent  # quant_balance/
    for parent in (anchor, *anchor.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    # 最终回退：src/backend/quant_balance → parents[3]
    return anchor.parents[2]


PROJECT_ROOT: Path = _detect_project_root()
"""项目根目录（包含 pyproject.toml）。"""

CONFIG_DIR: Path = PROJECT_ROOT / "config"
"""配置文件目录。"""

CONFIG_PATH: Path = CONFIG_DIR / "config.toml"
"""主配置文件路径。"""

WEB_DIR: Path = PROJECT_ROOT / "src" / "web"
"""Web 前端静态资源目录。"""

