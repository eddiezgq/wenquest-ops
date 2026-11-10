"""演示（虚构）：电控、台板机架、线架、附件包（第 135 轮 33a）。"""
from __future__ import annotations

import lib as L
import Part
from geo import CUTOUT, FLOOR, TABLE, ZU
from head_a import needle
from head_b import bobbin
from lib import V, X, Y, Z
from reg import at, lib_part, part


def electrical():
    A = "WQ88-3000"
    motor = L.cyl(52, 34, (393, 0, ZU), X).fuse(L.cyl(46, 4, (427, 0, ZU), X))
    for k in range(16):                           # cooling fins
        motor = motor.fuse(L.place(Part.makeBox(30, 3, 5, V(2, -1.5, 50)), (393, 0, ZU), X, 22.5 * k))
    part(A, "WQ88-3001", motor.cut(L.cyl(7.5, 60, (380, 0, ZU), X)))
    part(A, "WQ88-3002", L.disc(56, 4, (389, 0, ZU), X, bore=40))
    part(A, "WQ88-3003", L.tube(12, 7, 16, (412, 0, ZU), X))
    part(A, "WQ88-3004", L.box((180, 40, -190), (480, 250, -44), 6).fuse(L.box((200, 30, -170), (260, 40, -150))))
    part(A, "WQ88-3005", L.box((300, -64, 236), (378, -56, 286), 4).fuse(L.box((306, -66, 244), (346, -64, 278))))
    part(A, "WQ88-3006", L.box((300, -56, 232), (378, -55, 290), 2))
    part(A, "WQ88-3007", L.box((280, -30, -230), (360, 30, -190), 4).fuse(L.cyl(4, 20, (300, 0, -250))))
    cables = {"WQ88-3011": ([(400, 30, ZU - 40), (400, 60, 60), (400, 60, -60), (300, 120, -60)], 5),
              "WQ88-3012": ([(130, 50, -110), (180, 120, -110), (200, 140, -60)], 3),
              "WQ88-3013": ([(340, -56, 250), (340, -40, 200), (370, 40, 100), (370, 60, -60), (320, 150, -60)], 3),
              "WQ88-3014": ([(30, -36, 106), (80, -20, 196), (300, 0, 200), (360, 40, 100), (360, 70, -60), (340, 160, -60)], 2),
              "WQ88-3015": ([(396, 30, 262), (390, 50, 150), (380, 70, -60), (360, 170, -60)], 2.5),
              "WQ88-3016": ([(480, 200, -120), (560, 200, -160), (600, 260, -600), (640, 300, FLOOR + 5)], 4),
              "WQ88-3017": ([(480, 220, -150), (520, 240, -150), (540, 300, -40)], 2.5)}
    for code, (pts, r) in cables.items():
        lib_part(code, L.route(pts, r))
        at(A, code, (0, 0, 0))
    tie = L.tube(7, 6, 3).fuse(L.box((6, -2, 0), (10, 2, 3)))
    lib_part("WQ88-3018", tie)
    for k, p in enumerate([(400, 60, 40), (400, 60, 0), (400, 60, -40), (370, 60, 40), (370, 60, -20), (360, 70, 0),
                           (380, 70, 20), (380, 70, -40), (300, 120, -60), (320, 150, -60), (340, 160, -60),
                           (360, 170, -60)]):
        at(A, "WQ88-3018", p, Z if k < 8 else Y)
    lib_part("WQ88-3019", L.box((-6, -4, 0), (6, 4, 2), 1).fuse(L.tube(4, 3, 8, (-4, 0, 6), X)))
    for p in ((280, 120, -40), (320, 140, -40), (360, 160, -40), (420, 180, -40), (460, 200, -40), (520, 230, -40)):
        at(A, "WQ88-3019", p, -Z)
    part(A, "WQ88-3020", L.box((170, 30, -44), (490, 260, -41), 4))
    part(A, "WQ88-3021", L.box((520, -196, -86), (560, -160, -40), 4).fuse(L.box((530, -200, -74), (550, -196, -56))))
    for p in ((190, 45, -44), (470, 45, -44), (190, 245, -44), (470, 245, -44)):
        at(A, "LS-M5-12", p, -Z)
        at(A, "DQ-M5", (p[0], p[1], -46), -Z)
        at(A, "TH-M5", (p[0], p[1], -47.2), -Z)
    for p in ((395, 40, ZU + 40), (395, -40, ZU + 40), (395, 40, ZU - 40), (395, -40, ZU - 40), (300, 20, -190),
              (340, 20, -190)):
        at(A, "LS-M4-10", p, X if p[2] > 0 else -Z)
    for p in ((176, 36, -41), (484, 36, -41), (176, 254, -41), (484, 254, -41)):
        at(A, "LS-M6-16", p, -Z)
        at(A, "DQ-M6", (p[0], p[1], -42), -Z)


def table():
    A = "WQ88-4000"
    (tx0, ty0, tz0), (tx1, ty1, tz1) = TABLE
    (cx0, cy0), (cx1, cy1) = CUTOUT
    top = L.box((tx0, ty0, tz0), (tx1, ty1, tz1), 6).cut(L.box((cx0, cy0, tz0 - 1), (cx1, cy1, 1), 6))
    top = top.cut(L.cyl(20, 50, (520, 340, -45)))                     # a hole for the cables
    part(A, "WQ88-4001", top)
    band = L.box((tx0 - 2, ty0 - 2, tz0), (tx1 + 2, ty1 + 2, tz1), 8).cut(L.box((tx0, ty0, tz0 - 1), (tx1, ty1, tz1 + 1), 6))
    part(A, "WQ88-4002", band)
    part(A, "WQ88-4003", L.shell_box((-470, -180, -150), (-200, 260, -48), 12, r=4).fuse(
        L.box((-470, -190, -150), (-200, -180, -48), 4)).fuse(L.box((-360, -198, -110), (-310, -190, -94), 3)))
    lib_part("WQ88-4004", L.box((0, 0, 0), (12, 430, 30), 1).cut(L.box((3, -1, 4), (13, 431, 26))))
    at(A, "WQ88-4004", (-482, -170, -136))
    at(A, "WQ88-4004", (-200, -170, -136))
    lib_part("WQ88-4005", L.box((-20, -6, -8), (20, 6, 0), 2).fuse(L.cyl(4, 40, (-20, 0, -4), X)))
    at(A, "WQ88-4005", (0, 100, 0))
    at(A, "WQ88-4005", (300, 100, 0))
    part(A, "WQ88-4006", L.cyl(6, 80, (200, 220, 0)).fuse(L.cyl(14, 4, (200, 220, 0))))
    lib_part("WQ88-4007", L.box((-10, -10, 0), (10, 10, 6), 3))
    for p in ((cx0 + 12, cy0 + 12), (cx1 - 12, cy0 + 12), (cx0 + 12, cy1 - 12), (cx1 - 12, cy1 - 12)):
        at(A, "WQ88-4007", (p[0], p[1], -46))
    lib_part("WQ88-4008", L.cyl(10, 6).fuse(L.cyl(4, 6, (0, 0, 6))))
    for p in ((-120, -70), (370, -70), (-120, 70), (370, 70)):
        at(A, "WQ88-4008", (p[0], p[1], -124))
    for p in ((-10, 100, 0), (10, 100, 0), (290, 100, 0), (310, 100, 0), (-30, 100, 0), (330, 100, 0)):
        at(A, "LS-M6-20", p)
        at(A, "DQ-M6", (p[0], p[1], 0))
    for p in ((-476, -100, -100), (-476, 200, -100), (-194, -100, -100), (-194, 200, -100)):
        at(A, "LS-M5-16", p, -X if p[0] < -300 else X)
    for p in ((520, 340, -50), (530, 340, -50)):
        at(A, "LM-M5", p)
    for p in ((-540, 100, -40), (620, 100, -40)):
        at(A, "LS-M8-40", p)

    S = "WQ88-4100"                               # the stand: two side frames, two cross bars, the pedal
    for code, x in (("WQ88-4101", -520.0), ("WQ88-4102", 600.0)):
        leg = L.box((x - 20, -170, FLOOR + 30), (x + 20, -130, -40), 3)
        leg = leg.fuse(L.box((x - 20, 330, FLOOR + 30), (x + 20, 370, -40), 3))
        leg = leg.fuse(L.box((x - 20, -170, -80), (x + 20, 370, -40), 3))
        leg = leg.fuse(L.box((x - 20, -230, FLOOR + 30), (x + 20, 430, FLOOR + 60), 3))
        part(S, code, leg)
    lib_part("WQ88-4103", L.box((0, -15, -15), (1080, 15, 15), 3))
    at(S, "WQ88-4103", (-500, 100, -520))
    at(S, "WQ88-4103", (-500, 100, FLOOR + 120))
    part(S, "WQ88-4104", L.place(L.box((-160, -70, 0), (160, 70, 10), 6), (0, -110, FLOOR + 90), V(0, -0.17, 1)))
    part(S, "WQ88-4105", L.cyl(6, 400, (-200, -60, FLOOR + 80), X))
    part(S, "WQ88-4106", L.route([(0, -140, FLOOR + 100), (150, -60, -400), (300, 0, -252)], 3.5))
    lib_part("WQ88-4107", L.cyl(20, 6).fuse(L.cyl(5, 30, (0, 0, 6))))
    for x in (-520, 600):
        for y in (-200, 400):
            at(S, "WQ88-4107", (x, y, FLOOR))
    bolts = [(x, y, z) for x in (-520, 600) for y in (85, 115) for z in (-520, FLOOR + 120)]
    for x, y, z in bolts:
        at(S, "LS-M8-20", (x - 20 if x < 0 else x + 20, y, z), -X if x < 0 else X)
        at(S, "LM-M8", (x + 22 if x < 0 else x - 28, y, z), X if x < 0 else -X)
        at(S, "DQ-M8", (x - 20.5 if x < 0 else x + 20, y, z), -X if x < 0 else X)
        at(S, "DQ-M8", (x + 20 if x < 0 else x - 21, y, z), X if x < 0 else -X)
        at(S, "TH-M8", (x + 21.2 if x < 0 else x - 23, y, z), X if x < 0 else -X)
    for p in ((-200, -60, FLOOR + 74), (200, -60, FLOOR + 74), (-40, -110, FLOOR + 96), (40, -110, FLOOR + 96)):
        at(S, "LS-M6-25", p)

    T = "WQ88-4200"                               # thread stand at the back right of the table
    tx, ty = 560.0, 330.0
    part(T, "WQ88-4201", L.cyl(6, 560, (tx, ty, 0)))
    part(T, "WQ88-4202", L.box((tx - 60, ty - 30, 0), (tx + 30, ty + 30, 12), 4))
    part(T, "WQ88-4203", L.route([(tx, ty, 555), (tx - 200, ty, 555), (tx - 200, ty - 10, 548)], 3).fuse(
        __import__("Part").makeTorus(5, 1, V(tx - 200, ty - 10, 545))))
    lib_part("WQ88-4204", L.cyl(2.5, 60).fuse(L.cyl(8, 3)))
    at(T, "WQ88-4204", (tx - 40, ty - 15, 12))
    at(T, "WQ88-4204", (tx - 40, ty + 15, 12))
    lib_part("WQ88-4205", L.cyl(16, 3).cut(L.cyl(2.6, 5, (0, 0, -1))))
    at(T, "WQ88-4205", (tx - 40, ty - 15, 15))
    at(T, "WQ88-4205", (tx - 40, ty + 15, 15))
    part(T, "WQ88-4206", L.place(L.nut(12), (tx, ty, -48)))
    for p in ((tx - 40, ty - 15, -46), (tx - 40, ty + 15, -46)):
        at(T, "LM-M6", p)
        at(T, "DQ-M6", (p[0], p[1], -42))


def accessories():
    A = "WQ88-5000"
    ox, oy = -500.0, -150.0                       # laid out on the table, left of the head, as unpacked
    part(A, "WQ88-5001", L.cyl(28, 70, (ox + 40, oy + 40, 0)).fuse(Part.makeCone(28, 6, 40, V(ox + 40, oy + 40, 70))).fuse(
        L.route([(ox + 40, oy + 40, 105), (ox + 40, oy + 80, 150)], 2)))
    for code, y, ln in (("WQ88-5002", oy + 110, 200), ("WQ88-5003", oy + 140, 150)):
        part(A, code, L.cyl(12, 90, (ox, y, 12), X).fuse(L.cyl(3, ln - 90, (ox + 90, y, 12), X)))
    keys = L.box((ox + 120, oy + 10, 0), (ox + 220, oy + 50, 14), 4)
    for k in range(6):
        keys = keys.fuse(L.cyl(1 + k * 0.4, 60 + k * 8, (ox + 130 + k * 15, oy + 20, 14)))
    part(A, "WQ88-5004", keys)
    for k in range(3):
        at(A, "WQ88-1713", (ox + 250 + k * 25, oy + 30, 0))
    for k in range(10):
        at(A, "WQ88-1490", (ox + 120 + k * 8, oy + 200, 1.5), X)
    part(A, "WQ88-5005", L.shell_box((ox, oy + 230, 0), (ox + 300, oy + 400, 24), 2, open_top=False, r=10))
    part(A, "WQ88-5006", L.box((ox, oy + 420, 0), (ox + 148, oy + 630, 12), 2))
    part(A, "WQ88-5007", L.box((ox + 160, oy + 420, 0), (ox + 308, oy + 630, 18), 2))
    part(A, "WQ88-5008", L.box((ox + 320, oy + 420, 0), (ox + 420, oy + 490, 0.6)))
    part(A, "WQ88-5009", L.cyl(35, 160, (ox + 360, oy + 60, 0)).fuse(L.cyl(14, 30, (ox + 360, oy + 60, 160))))
    # the carton (folded flat) and its two foam pads stand on the floor under the table, at the back
    cx, cy = -470.0, 260.0
    part(A, "WQ88-5010", L.box((cx, cy, FLOOR + 32), (cx + 640, cy + 12, FLOOR + 552), 2))
    lib_part("WQ88-5011", L.box((0, 0, 0), (300, 40, 220), 4).cut(L.box((60, -1, 60), (240, 20, 221))))
    at(A, "WQ88-5011", (cx + 20, cy - 44, FLOOR + 32))
    at(A, "WQ88-5011", (cx + 330, cy - 44, FLOOR + 32))
    part(A, "WQ88-5012", L.box((ox + 320, oy + 120, 0), (ox + 440, oy + 220, 8), 4))


def all_():
    lib_part("WQ88-1490", needle())
    lib_part("WQ88-1713", bobbin())
    electrical()
    table()
    accessories()
