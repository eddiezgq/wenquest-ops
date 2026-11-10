"""演示（虚构）：标准件的三维，按名称里的规格建（螺钉、螺母、垫圈、挡圈、轴承、销、橡胶塞、油封、O 形圈）。
每个都画在原点：螺钉、销类的头朝 +Z、杆朝 -Z；垫圈、挡圈、轴承、油封从 z = 0 往 +Z。"""
from __future__ import annotations

import re

import lib as L
from reg import lib_part

BEARINGS = {"6000ZZ": (10, 26, 8, False), "6001ZZ": (12, 28, 8, False), "6201ZZ": (12, 32, 10, False),
            "6202ZZ": (15, 35, 11, False), "608ZZ": (8, 22, 7, False), "HK0810": (8, 12, 10, True),
            "HK1012": (10, 14, 12, True), "HK1210": (12, 16, 10, True), "NA4900": (10, 22, 13, True)}


def build(code: str, name: str):
    m = re.fullmatch(r"螺钉 SM(\d+/\d+)\((\d+)\)×(\d+)", name)
    if m:
        return L.screw(L.INCH_SM[m.group(1)], float(m.group(3)), "cheese")
    m = re.fullmatch(r"内六角螺钉 M(\d+)×(\d+)", name)
    if m:
        return L.screw(float(m.group(1)), float(m.group(2)), "socket")
    m = re.fullmatch(r"紧定螺钉 SM(\d+)/64", name)
    if m:
        d = int(m.group(1)) * 25.4 / 64 + 1.5
        return L.screw(d, d * 1.6, "set")
    m = re.fullmatch(r"六角螺母 M(\d+)", name)
    if m:
        return L.nut(float(m.group(1)))
    m = re.fullmatch(r"(平|弹簧)垫圈 M(\d+)", name)
    if m:
        return L.washer(float(m.group(2)), m.group(1) == "弹簧")
    m = re.fullmatch(r"E 型挡圈 (\d+)", name)
    if m:
        return L.eclip(float(m.group(1)))
    m = re.fullmatch(r"轴承 (\S+)", name)
    if m:
        d, D, B, needle = BEARINGS[m.group(1)]
        return L.bearing(d, D, B, needle)
    m = re.fullmatch(r"圆柱销 φ(\d+)×(\d+)", name)
    if m:
        return L.pin(float(m.group(1)), float(m.group(2)))
    m = re.fullmatch(r"开口销 φ(\d+)×(\d+)", name)
    if m:
        return L.split_pin(float(m.group(1)), float(m.group(2)))
    m = re.fullmatch(r"橡胶塞 φ(\d+)", name)
    if m:
        return L.plug(float(m.group(1)))
    m = re.fullmatch(r"油封 φ(\d+)", name)
    if m:
        return L.oil_seal(float(m.group(1)))
    m = re.fullmatch(r"O 形圈 φ(\d+)×1\.5", name)
    if m:
        return L.oring(float(m.group(1)))
    raise ValueError(f"no standard shape for {code} {name}")


def ensure_all(std: dict) -> None:
    for code, (name, _src, _unit) in std.items():
        lib_part(code, build(code, name))
