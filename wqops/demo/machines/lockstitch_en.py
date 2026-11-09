"""演示数据（虚构）：WQ-8800D 平缝机零件的英文名，给配件手册用（第 124 轮 27d）。人写的对照表，不是 AI 起草；
装入演示时由工程师确认。标准件按规格拼。"""
from __future__ import annotations

import re

NAMES = {
    "WQ-8800D 电脑直驱单针平缝机（演示·虚构）":
        "WQ-8800D Direct-drive Single-needle Lockstitch Machine (demo, fictional)",
    "LED 照明灯 DC5V": "LED lamp DC5V", "一字螺丝刀 大": "Flat screwdriver, large",
    "一字螺丝刀 小": "Flat screwdriver, small", "上轴": "Upper shaft", "上轴中轴套": "Upper shaft middle bushing",
    "上轴前轴套": "Upper shaft front bushing", "上轴同步带轮": "Upper shaft timing pulley",
    "上轴后轴套": "Upper shaft rear bushing", "上轴挡圈": "Upper shaft collar", "上轴油芯": "Upper shaft oil wick",
    "上轴部件": "Upper shaft assembly", "下轴": "Lower shaft", "下轴前轴套": "Lower shaft front bushing",
    "下轴同步带轮": "Lower shaft timing pulley", "下轴后轴套": "Lower shaft rear bushing",
    "下轴挡圈": "Lower shaft collar", "下轴油芯": "Lower shaft oil wick", "下轴部件": "Lower shaft assembly",
    "主动松线部件": "Active thread release assembly", "主线束": "Main wiring harness", "传感器支架": "Sensor bracket",
    "传感器线束": "Sensor harness", "使用说明书": "Instruction manual", "倒缝复位簧": "Reverse feed return spring",
    "倒缝扳手": "Reverse feed lever", "倒缝扳手轴": "Reverse feed lever shaft", "倒缝拉杆": "Reverse feed pull rod",
    "倒缝曲柄": "Reverse feed crank", "倒缝电磁铁 DC24V": "Reverse feed solenoid DC24V",
    "倒缝电磁铁座": "Reverse feed solenoid base", "倒缝连杆": "Reverse feed link", "内六角扳手套装": "Hex key set",
    "切线刀片": "Thread cutter blade", "剪线凸轮": "Thread trimmer cam", "剪线复位簧": "Thread trimmer return spring",
    "剪线曲柄": "Thread trimmer crank", "剪线止动块": "Thread trimmer stopper", "剪线滚轮": "Thread trimmer roller",
    "剪线电磁铁 DC24V": "Thread trimmer solenoid DC24V", "剪线轴": "Thread trimmer shaft",
    "剪线轴座": "Thread trimmer shaft holder", "剪线连杆": "Thread trimmer link", "动刀": "Moving knife",
    "动刀座": "Moving knife holder", "动刀轴": "Moving knife shaft", "包装箱": "Shipping carton",
    "压力调节螺钉": "Pressure regulating screw", "压杆": "Presser bar", "压杆导架": "Presser bar guide bracket",
    "压杆导架滑轨": "Presser bar guide rail", "压簧": "Presser spring", "压脚": "Presser foot",
    "压脚部件": "Presser foot assembly", "压脚铰链销": "Presser foot hinge pin",
    "厚料压脚": "Presser foot, heavy material", "厚料送布牙": "Feed dog, heavy material",
    "厚料针板": "Needle plate, heavy material", "台板": "Table top", "台板封边条": "Table edge band",
    "台板机架部件": "Table and stand assembly", "右立柱": "Right leg", "合格证": "Certificate of conformity",
    "同步带 S3M-540": "Timing belt S3M-540", "后盖板": "Rear cover", "后盖板垫": "Rear cover gasket",
    "吸油网": "Oil strainer", "回油槽": "Oil return groove", "回油管 φ6×300": "Oil return tube φ6×300",
    "夹线器座": "Thread tension base", "夹线板": "Tension disc", "夹线簧": "Tension spring",
    "夹线螺柱": "Tension stud", "夹线螺母": "Tension nut", "夹线部件": "Thread tension assembly",
    "定刀": "Fixed knife", "定刀座": "Fixed knife holder", "尼龙扎带 150": "Cable tie 150", "左立柱": "Left leg",
    "平衡块": "Counterweight", "底板盖": "Bed cover", "底板盖垫": "Bed cover gasket", "手轮": "Handwheel",
    "手轮护罩": "Handwheel guard", "扳手轴": "Lever shaft", "护指器": "Finger guard", "护眼罩": "Eye guard",
    "护眼罩座": "Eye guard bracket", "抬压脚扳手": "Presser foot lifter lever",
    "抬压脚拉杆": "Presser foot lifter pull rod", "抬压脚曲柄": "Presser foot lifter crank",
    "抬压脚杆": "Presser foot lifter bar", "抬压脚电磁铁 DC24V": "Presser foot lifter solenoid DC24V",
    "抬压脚连杆": "Presser foot lifter link", "抬牙偏心轮": "Feed lifting eccentric", "抬牙叉": "Feed lifting fork",
    "抬牙曲柄": "Feed lifting crank", "抬牙滑块": "Feed lifting slide block",
    "抬牙调节偏心套": "Feed lift adjusting eccentric sleeve", "抬牙轴": "Feed lifting shaft",
    "抬牙轴轴套": "Feed lifting shaft bushing", "抬牙连杆": "Feed lifting link",
    "抬牙高度调节部件": "Feed dog height adjusting assembly", "抽屉": "Drawer", "抽屉滑轨": "Drawer slide",
    "拨线器": "Wiper", "拨线器座": "Wiper base", "拨线器轴": "Wiper shaft", "拨线复位簧": "Wiper return spring",
    "拨线电磁铁 DC24V": "Wiper solenoid DC24V", "拨线部件": "Wiper assembly", "挑线曲柄": "Thread take-up crank",
    "挑线曲柄油毡": "Thread take-up crank oil felt", "挑线曲柄销": "Thread take-up crank pin",
    "挑线杆": "Thread take-up lever", "挑线杆过线钩": "Thread take-up lever thread guide",
    "挑线杆防护罩": "Thread take-up lever guard", "挑线簧": "Thread take-up spring",
    "挑线簧止动板": "Thread take-up spring stopper", "挑线簧调节座": "Thread take-up spring regulator",
    "挑线连杆": "Thread take-up link", "挑线连杆销": "Thread take-up link pin", "挑线部件": "Thread take-up assembly",
    "接地线": "Ground wire", "控制箱 220V": "Control box 220V", "控制箱安装板": "Control box mounting plate",
    "摩擦圈": "Friction ring", "操作面板": "Operation panel", "操作面板支架": "Operation panel bracket",
    "操作面板线束": "Operation panel harness", "放油螺塞": "Oil drain plug",
    "断线检测传感器": "Thread breakage sensor", "旋梭 HSH-7.94A": "Rotary hook HSH-7.94A",
    "旋梭定位板": "Rotary hook positioning plate", "旋梭油芯": "Rotary hook oil wick",
    "旋梭部件": "Rotary hook assembly", "机壳": "Machine arm and bed", "机壳后封板": "Arm rear sealing plate",
    "机壳定位销": "Arm dowel pin", "机壳部件": "Machine arm assembly", "机头支杆": "Head rest rod",
    "机头橡胶垫": "Head rubber cushion", "机头部件": "Machine head assembly", "机头铰链": "Machine head hinge",
    "机架部件": "Stand assembly", "机针 DB×1 #14": "Needle DB×1 #14", "松线板": "Thread release plate",
    "松线电磁铁 DC24V": "Thread release solenoid DC24V", "松线电磁铁座": "Thread release solenoid base",
    "松线连杆": "Thread release link", "松线销": "Thread release pin", "松线顶杆": "Thread release push rod",
    "梭芯": "Bobbin", "梭芯套": "Bobbin case", "横档": "Cross bar", "油壶": "Oiler", "油标": "Oil level gauge",
    "油泵体": "Oil pump body", "油泵叶片": "Oil pump vane", "油泵盖": "Oil pump cover", "油泵轴": "Oil pump shaft",
    "油泵部件": "Oil pump assembly", "油盘": "Oil pan", "油盘垫": "Oil pan gasket",
    "油盘支承垫": "Oil pan support cushion", "油窗": "Oil window", "油窗垫": "Oil window gasket",
    "油管 φ4×120": "Oil tube φ4×120", "油管 φ4×260": "Oil tube φ4×260", "油管 φ4×380": "Oil tube φ4×380",
    "油管夹": "Oil tube clamp", "油管接头": "Oil tube joint", "油芯 L150": "Oil wick L150",
    "油芯 L80": "Oil wick L80", "油芯夹": "Oil wick clip", "油量调节螺钉": "Oil amount adjusting screw",
    "泡沫衬垫": "Foam cushion", "润滑部件": "Lubrication assembly", "滑块导轨": "Slide block guide",
    "滑板": "Slide plate", "滑板簧": "Slide plate spring", "满线挡板": "Bobbin winder stop latch",
    "照明与传感部件": "Lamp and sensor assembly", "照明灯支架": "Lamp bracket", "照明灯线束": "Lamp harness",
    "电控部件": "Electrical control assembly", "电机座": "Motor base", "电机联轴器": "Motor coupling",
    "电源开关": "Power switch", "电源线 3×1.0 2m": "Power cord 3×1.0 2m", "电磁铁安装板": "Solenoid mounting plate",
    "电磁铁座": "Solenoid base", "电磁铁线束": "Solenoid harness", "电磁铁轴": "Solenoid shaft",
    "直驱伺服电机 550W": "Direct-drive servo motor 550W", "线卡": "Cable clip", "线架座": "Thread stand base",
    "线架杆": "Thread stand rod", "线架螺母": "Thread stand nut", "线架过线臂": "Thread stand guide arm",
    "线架部件": "Thread stand assembly", "线盘垫": "Spool cushion", "线盘座": "Spool holder",
    "绕线器座": "Bobbin winder base", "绕线器簧": "Bobbin winder spring", "绕线器部件": "Bobbin winder assembly",
    "绕线夹线器": "Bobbin winder tension", "绕线轮": "Bobbin winder wheel", "绕线轴": "Bobbin winder shaft",
    "缓冲垫": "Cushion", "缝纫机油 0.5L": "Sewing machine oil 0.5L", "脚踏拉杆": "Pedal connecting rod",
    "脚踏控制器": "Pedal controller", "脚踏板": "Pedal", "脚踏板轴": "Pedal shaft", "膝控垫": "Knee lifter pad",
    "膝控复位簧": "Knee lifter return spring", "膝控抬压脚部件": "Knee lifter assembly",
    "膝控拉杆": "Knee lifter pull rod", "膝控曲柄": "Knee lifter crank", "膝控板": "Knee lifter plate",
    "膝控轴": "Knee lifter shaft", "膝控轴座": "Knee lifter shaft holder", "膝控连杆": "Knee lifter link",
    "自动倒缝部件": "Automatic reverse feed assembly", "自动剪线部件": "Automatic thread trimmer assembly",
    "自动抬压脚部件": "Automatic presser foot lifter assembly", "调节偏心套螺钉": "Adjusting eccentric sleeve screw",
    "调节器销": "Regulator pin", "调节脚": "Adjustable foot", "调节螺母": "Adjusting nut",
    "轴套油孔塞": "Bushing oil hole plug", "过线环": "Thread guide ring", "过线钩": "Thread guide hook",
    "送布偏心轮": "Feed eccentric", "送布摆杆": "Feed rocker", "送布摆杆销": "Feed rocker pin",
    "送布曲柄": "Feed crank", "送布牙": "Feed dog", "送布牙架": "Feed bar", "送布牙架销": "Feed bar pin",
    "送布调节器": "Feed regulator", "送布轴": "Feed shaft", "送布轴前轴套": "Feed shaft front bushing",
    "送布轴后轴套": "Feed shaft rear bushing", "送布连杆": "Feed link", "送布部件": "Feed mechanism assembly",
    "送布部件（7 mm 厚料）": "Feed mechanism assembly (7 mm, heavy material)", "针位传感器": "Needle position sensor",
    "针夹": "Needle clamp", "针杆": "Needle bar", "针杆上轴套": "Needle bar upper bushing",
    "针杆下轴套": "Needle bar lower bushing", "针杆曲柄": "Needle bar crank", "针杆油毡": "Needle bar oil felt",
    "针杆滑块": "Needle bar slide block", "针杆线钩": "Needle bar thread guide",
    "针杆连接轴": "Needle bar connecting stud", "针杆连接轴挡块": "Needle bar connecting stud stopper",
    "针杆连杆": "Needle bar connecting rod", "针杆部件": "Needle bar assembly",
    "针杆防油圈": "Needle bar oil seal ring", "针板": "Needle plate", "针板座": "Needle plate base",
    "针距指示板": "Stitch length indicator plate", "针距盘": "Stitch length dial",
    "针距调节凸块": "Stitch length adjusting cam block", "针距调节簧": "Stitch length adjusting spring",
    "针距调节螺杆": "Stitch length adjusting screw rod", "针距调节轴": "Stitch length adjusting shaft",
    "针距调节部件": "Stitch length adjusting assembly", "铝铆钉 φ2×5": "Aluminium rivet φ2×5", "铭牌": "Name plate",
    "防尘罩": "Dust cover", "附件包": "Accessory kit", "附件袋": "Accessory bag", "零件图册": "Parts catalogue",
    "面板": "Face plate", "面板垫": "Face plate gasket", "面板过线器": "Face plate thread guide", "顶盖": "Top cover",
    "顶盖垫": "Top cover gasket", "预夹线座": "Pre-tension base", "预夹线板": "Pre-tension disc",
    "预夹线簧": "Pre-tension spring", "预夹线螺柱": "Pre-tension stud", "预夹线螺母": "Pre-tension nut",
    "预夹线部件": "Pre-tension assembly",
}

# the options of the model configuration (a model's name is the base machine's and its options)
OPTIONS = {"5 mm 标准": "5 mm standard", "7 mm 厚料": "7 mm heavy material", "自动剪线": "automatic thread trimmer",
           "无剪线": "no thread trimmer", "自动抬压脚": "automatic presser foot lifter", "膝控抬压脚": "knee lifter"}

# standard parts: the kind of part in Chinese -> in English; the size after it stays as it is
STD = (("内六角螺钉", "Hex socket screw"), ("紧定螺钉", "Set screw"), ("螺钉", "Screw"), ("六角螺母", "Hex nut"),
       ("平垫圈", "Flat washer"), ("弹簧垫圈", "Spring washer"), ("E 型挡圈", "E-ring"), ("O 形圈", "O-ring"),
       ("轴承", "Bearing"), ("圆柱销", "Dowel pin"), ("开口销", "Split pin"), ("橡胶塞", "Rubber plug"),
       ("油封", "Oil seal"))


def en(name: str) -> str | None:
    """The English name, or None when the table has none (then the part keeps no English name: never a guess)."""
    if name in NAMES:
        return NAMES[name]
    base = next((b for b in NAMES if name.startswith(b + " ")), None)
    if base:                                    # a model: the base machine and its options, "a / b / c"
        opts = [OPTIONS.get(o.strip()) for o in name[len(base) + 1:].split(" / ")]
        return f"{NAMES[base]} {' / '.join(opts)}" if all(opts) else None
    for zh, e in STD:
        m = re.fullmatch(rf"{re.escape(zh)} (.+)", name)
        if m:
            return f"{e} {m.group(1)}"
    return None
