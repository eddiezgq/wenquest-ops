"""演示数据（虚构）：WQ-8800D 电脑直驱单针平缝机的旧 BOM 写成 Excel 层级表。数据在 wqops/demo/machines/lockstitch.py。

    python demo/plm/lockstitch_bom.py            # 写出 demo/plm/平缝机BOM-演示.xlsx
用法：质量 ERP“工程设计 → 设计数据”，上传 Excel，选这个文件。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from wqops.demo.machines.lockstitch import *  # noqa: F403
from wqops.demo.machines.lockstitch import TREE, write

if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("平缝机BOM-演示.xlsx")
    print(write(out, TREE), out)
