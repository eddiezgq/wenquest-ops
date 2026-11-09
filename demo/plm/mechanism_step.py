"""演示（虚构）：用问渠缝纫机设计软件生成平缝机机构零件的三维，每个零件一份 STEP，
给蓝湾演示的配件手册用（第 124 轮 27d）。

设计软件在问渠仓库 eddiezgq/WenQuest 的 services/gateway/app/sewcore/cad.py；默认参数、主轴转角 0°。
坐标就是整机坐标，所以 BOM 行的装配位置都是“原地”。在 FreeCAD 里跑：

    WQ_SEWCORE=<WenQuest>/services/gateway/app freecadcmd -c "exec(open('demo/plm/mechanism_step.py').read())"

写出 wqops/demo/manual/mechanism/<编码>.step（演示装入时读）。
设计软件里的零件名 → 蓝湾的零件编码：wqops/demo/machines/lockstitch.py 的 MECHANISM。
"""
import os
import sys

OUT = os.path.join(os.getcwd(), "wqops", "demo", "manual", "mechanism")
sys.path.insert(0, os.environ["WQ_SEWCORE"])
sys.path.insert(0, os.getcwd())
from sewcore import cad  # noqa: E402

from wqops.demo.machines.lockstitch import MECHANISM  # noqa: E402

for name, _zh, shape, _color in cad.freecad_shapes(cad.parts3d(None, 0.0, "lockstitch")):
    if name in MECHANISM:
        out = os.path.join(OUT, MECHANISM[name] + ".step")
        shape.exportStep(out)
        print(name, MECHANISM[name], os.path.getsize(out))
