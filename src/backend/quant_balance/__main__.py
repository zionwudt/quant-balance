"""模块入口。

允许通过 `python -m quant_balance` 走与命令行脚本相同的启动路径，
避免出现两套入口逻辑逐渐分叉的问题。
"""

from __future__ import annotations

from quant_balance.main import main


if __name__ == "__main__":
    # 直接复用统一主入口，保证模块运行与命令行脚本行为一致。
    main()
