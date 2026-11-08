"""演示数据（虚构）：WQ-737 电脑直驱四线包缝机的旧 BOM 写成 Excel 层级表。数据在 wqops/demo/machines/overlock.py。

    python demo/plm/overlock_bom.py              # 写出 demo/plm/包缝机BOM-演示.xlsx
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from wqops.demo.machines.lockstitch import write
from wqops.demo.machines.overlock import TREE

if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("包缝机BOM-演示.xlsx")
    print(write(out, TREE), out)
