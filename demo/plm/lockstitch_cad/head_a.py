"""演示（虚构）：机壳部件、上轴部件、挑线部件、针杆部件（第 135 轮 33a）。"""
from __future__ import annotations

import lib as L
from geo import (
    ARM,
    BED,
    FACE_X,
    HEAD,
    NB_BOTTOM,
    NB_TOP,
    PILLAR,
    TIP,
    X_BELT,
    X_SHAFT0,
    X_SHAFT1,
    ZPIN,
    ZSTUD,
    ZU,
)
from lib import X, Y, Z
from reg import at, lib_part, part


def casing():
    A = "WQ88-1100"
    (bx0, by0, bz0), (bx1, by1, bz1) = BED
    bed = L.box((bx0, by0, bz0), (bx1, by1, bz1), 6).cut(L.box((bx0 + 10, by0 + 10, bz0 - 1), (bx1 - 10, by1 - 10, -8)))
    pil = L.box(*PILLAR, 14).cut(L.box((PILLAR[0][0] + 10, -45, -10), (PILLAR[1][0] - 10, 45, 290)))
    arm = L.box(*ARM, 12).cut(L.box((ARM[0][0] + 10, -34, 208), (ARM[1][0] - 12, 34, 292)))
    head = L.box(*HEAD, 10).cut(L.box((FACE_X - 1, -40, 112), (HEAD[1][0] - 8, 40, 292)))
    body = bed.fuse(pil).fuse(arm).fuse(head)
    # bosses for the shaft bushings, the needle bar and the presser bar
    for x in (40.0, 200.0, 330.0):
        body = body.fuse(L.cyl(17, 22, (x - 11, 0, ZU), X))
    for x in (40.0, 330.0):
        body = body.fuse(L.cyl(15, 22, (x - 11, 0, -28), X).fuse(L.box((x - 11, -6, -28), (x + 11, 6, -8))))
    body = body.fuse(L.cyl(10, 18, (0, 0, 105))).fuse(L.cyl(10, 16, (0, 0, 250)))
    body = body.fuse(L.cyl(9, 16, (0, 24, 105))).fuse(L.cyl(9, 14, (0, 24, 276)))
    # bores, openings
    for cut in (L.cyl(8.2, 460, (-60, 0, ZU), X), L.cyl(7.2, 420, (-60, 0, -28), X),
                L.cyl(6.1, 220, (0, 0, 95)), L.cyl(5.1, 210, (0, 24, 95)),
                L.box((-45, -32, -10), (45, 32, 2)),                     # needle plate seat
                L.box((-40, -88.5, -6), (40, -32, 2)),                    # slide plate opening
                L.box((60, -25, 288), (250, 25, 310)),                    # top cover opening
                L.box((315, 45, 40), (375, 60, 260)),                     # rear cover opening
                L.cyl(12, 20, (150, -50, 250), Y),                         # oil window
                L.box((-36, -60, 228), (-24, -40, 284))):                 # take-up lever slot
        body = body.cut(cut)
    part(A, "WQ88-1101", body.removeSplitter())
    face = L.box((FACE_X - 3, -46, 108), (FACE_X, 46, 298), 8).cut(L.cyl(4, 6, (FACE_X - 4, -30, 140), X))
    part(A, "WQ88-1102", face)
    part(A, "WQ88-1103", L.box((FACE_X - 0.0, -44, 110), (FACE_X + 0.8, 44, 296), 6).cut(
        L.box((FACE_X - 1, -36, 116), (FACE_X + 2, 36, 288))))
    part(A, "WQ88-1104", L.box((310, 55, 35), (380, 58, 265), 8))
    part(A, "WQ88-1105", L.box((312, 54.2, 37), (378, 55, 263), 6).cut(L.box((318, 53, 44), (372, 56, 256))))
    part(A, "WQ88-1106", L.box((55, -30, 300), (255, 30, 303), 10))
    part(A, "WQ88-1107", L.box((57, -28, 299.2), (253, 28, 300), 8).cut(L.box((64, -20, 298), (246, 20, 301))))
    part(A, "WQ88-1108", L.cyl(14, 3, (150, -45, 250), Y).fuse(L.cyl(11, 4, (150, -48, 250), Y)).cut(
        L.cyl(9, 2, (150, -48.5, 250), Y)))
    part(A, "WQ88-1109", L.tube(14, 10, 0.8, (150, -42.8, 250), Y))
    part(A, "WQ88-1110", L.box((200, -80, -68), (380, 80, -65), 6))
    part(A, "WQ88-1111", L.box((202, -78, -65), (378, 78, -64.2), 4).cut(L.box((210, -70, -66), (370, 70, -63))))
    part(A, "WQ88-1112", L.box((180, -45.8, 262), (260, -42.2, 282), 2).cut(L.box((184, -47, 266), (256, -45, 278))))
    lib_part("WQ88-1113", L.pin(6, 14))
    at(A, "WQ88-1113", (-30, 40, 14), -Z)
    at(A, "WQ88-1113", (370, -40, 14), -Z)
    part(A, "WQ88-1114", L.box((-50, -40, -14), (50, 40, -10), 4).cut(L.box((-12, -14, -15), (12, 14, -9))))
    part(A, "WQ88-1115", L.box((-38, -86, -2), (38, -33, 0), 6).fuse(L.box((-6, -84, 0), (6, -80, 1.2))))
    part(A, "WQ88-1116", L.box((-20, -60, -3.2), (20, -50, -2.6)))
    part(A, "WQ88-1117", L.box((-30, -78, 60), (30, -76, 105), 6))                 # clear eye guard in front of the needle
    part(A, "WQ88-1118", L.box((-38, -60, 105), (-30, -46, 140), 2).fuse(L.cyl(3, 22, (-34, -78, 100), Y)))
    part(A, "WQ88-1119", L.lever([(0, 0, 4), (24, 0, 4)], 2, origin=(-12, -16, 26), u=X, v=Y, n=Z))
    part(A, "WQ88-1120", L.box((385, -48, 20), (393, 48, 290), 6))
    # bought and standard parts of the casing
    lib_part("WQ88-1190", L.cyl(1, 5, (0, 0, -5)).fuse(L.cyl(2, 1)))
    at(A, "WQ88-1190", (200, -45.8, 266), -Y)
    at(A, "WQ88-1190", (240, -45.8, 266), -Y)
    for code, pts in (("XJ-6", [(100, -42, 220), (280, -42, 220), (100, 42, 220), (280, 42, 220)]),
                      ("XJ-8", [(320, -55, 60), (320, -55, 120), (360, -55, 60), (-20, -48, 200), (20, -48, 200),
                                (380, -55, 280)]),
                      ("XJ-12", [(60, 42, 260), (120, 42, 260), (180, 42, 260)]),
                      ("XJ-20", [(330, -55, 200), (360, -55, 200)])):
        for p in pts:
            at(A, code, p, -Y if p[1] < 0 else Y)
    at(A, "XJ-25", (390, 0, 150), X)
    for p in ((FACE_X - 3, -38, 120), (FACE_X - 3, 38, 120), (FACE_X - 3, -38, 288)):
        at(A, "LS-S11-64-08", p, -X)
    for p in ((60, -26, 303), (150, -26, 303), (250, -26, 303), (60, 26, 303), (150, 26, 303), (250, 26, 303)):
        at(A, "LS-S11-64-06", p)
    for p in ((316, 58, 40), (374, 58, 40), (316, 58, 260), (374, 58, 260)):
        at(A, "LS-S9-64-05", p, Y)
    for p in ((-34, -60, 136), (-34, -60, 112)):
        at(A, "LS-S15-64-12", p, -X)
    for p in ((205, -75, -68), (375, -75, -68), (205, 75, -68), (375, 75, -68)):
        at(A, "LS-M4-08", p, -Z)


def upper_shaft():
    A = "WQ88-1200"
    part(A, "WQ88-1201", L.shaft([(12, 14), (180, 16), (60, 15), (X_SHAFT1 - X_SHAFT0 - 252, 14)], (X_SHAFT0, 0, ZU)))
    part(A, "WQ88-1202", L.tube(10, 8, 22, (29, 0, ZU), X).fuse(L.tube(13, 8, 3, (29, 0, ZU), X)))
    part(A, "WQ88-1203", L.tube(10, 8, 22, (189, 0, ZU), X))
    part(A, "WQ88-1204", L.tube(10, 7.5, 18, (321, 0, ZU), X).fuse(L.tube(13, 7.5, 3, (339, 0, ZU), X)))
    part(A, "WQ88-1205", L.tube(14, 8, 8, (60, 0, ZU), X).cut(L.cyl(2, 20, (64, 0, ZU), Z)))
    cw = L.lever([(0, 0, 14), (0, -28, 26)], 14, holes=[(0, 0, 8)], origin=(268, 0, ZU), u=Y, v=Z, n=X)
    part(A, "WQ88-1206", cw)
    part(A, "WQ88-1207", L.pulley(20, 14, (X_BELT - 7, 0, ZU), X, bore=14, teeth=24))
    hw = L.disc(42, 12, (440, 0, ZU), X, bore=14).cut(L.disc(34, 8, (444, 0, ZU), X)).fuse(L.tube(12, 7, 22, (430, 0, ZU), X))
    part(A, "WQ88-1208", hw)
    part(A, "WQ88-1209", L.tube(47, 44, 18, (436, 0, ZU), X).fuse(L.tube(47, 20, 2, (436, 0, ZU), X)).cut(
        L.box((420, -50, ZU - 50), (460, 50, ZU - 20))))
    part(A, "WQ88-1210", L.cyl(1.5, 70, (40, 9, ZU + 14), X))
    lib_part("WQ88-1211", L.box((-3, -2, 0), (3, 2, 6)).cut(L.cyl(1.6, 6, (0, -3, 3), Y)))
    at(A, "WQ88-1211", (60, 9, ZU + 14))
    at(A, "WQ88-1211", (180, 9, ZU + 14))
    lib_part("WQ88-1212", L.cyl(3, 1.2).fuse(L.cyl(2, 4, (0, 0, -4))))
    at(A, "WQ88-1212", (40, 0, ZU + 17))
    at(A, "WQ88-1212", (200, 0, ZU + 17))
    at(A, "ZC-6202ZZ", (360, 0, ZU), X)
    at(A, "YF-25", (371, 0, ZU), X)
    for x in (66, 280, 349, 438):
        at(A, "JD-SM8", (x, 0, ZU + 13 if x != 280 else ZU + 15))
    for x in (12, 34, 194):
        at(A, "JD-SM6", (x, 0, ZU - 11), -Z)
    for p in ((448, 30, ZU), (448, -30, ZU)):
        at(A, "LS-S15-64-10", p, X)
    for p in ((436, 0, ZU + 46), (436, 0, ZU - 46)):
        at(A, "LS-S11-64-05", p, Z if p[2] > ZU else -Z)
    at(A, "DQ-E15", (318, 0, ZU), X)


def takeup():
    A = "WQ88-1300"
    xc = -26.0                       # the take-up crank and lever sit outside the needle crank, in front of the face
    pin = (0.0, ZPIN)                # Y, Z of the crank pin (needle at the top)
    piv = (34.0, ZU + 34)            # Y, Z of the link pin (fixed in the head)
    eye = (-62.0, ZU + 6)            # the thread eye, out through the slot in the front
    part(A, "WQ88-1301", L.lever([(0, ZU, 13), (pin[0], pin[1], 8)], 6, holes=[(0, ZU, 6.1)], origin=(xc, 0, 0), u=Y, v=Z, n=X))
    part(A, "WQ88-1302", L.cyl(4, 22, (xc - 14, pin[0], pin[1]), X).fuse(L.cyl(6, 2, (xc - 16, pin[0], pin[1]), X)))
    part(A, "WQ88-1303", L.lever([(piv[0], piv[1], 7), (14, ZU + 30, 6)], 5, holes=[(piv[0], piv[1], 3.1), (14, ZU + 30, 3.1)],
                                 origin=(xc - 13, 0, 0), u=Y, v=Z, n=X))
    part(A, "WQ88-1304", L.lever([(pin[0], pin[1], 7), (14, ZU + 30, 5), (eye[0], eye[1], 4)], 4,
                                 holes=[(pin[0], pin[1], 4.1), (14, ZU + 30, 3.1), (eye[0], eye[1], 1.4)],
                                 origin=(xc - 8, 0, 0), u=Y, v=Z, n=X))
    part(A, "WQ88-1305", L.cyl(3, 28, (xc - 16, piv[0], piv[1]), X).fuse(L.cyl(4.5, 2, (xc - 18, piv[0], piv[1]), X)))
    part(A, "WQ88-1306", L.box((-40, -70, ZU - 14), (-16, -66, ZU + 26), 4))
    part(A, "WQ88-1307", L.cyl(1, 10, (xc - 6, eye[0] - 2, eye[1] + 4), X).fuse(L.cyl(2, 2, (xc - 6, eye[0] - 2, eye[1] + 4), X)))
    part(A, "WQ88-1308", L.tube(13, 7, 2, (xc + 6, 0, ZU), X))
    at(A, "ZC-HK1012", (xc - 8, pin[0], pin[1]), X)
    at(A, "ZC-HK0810", (xc - 13, piv[0], piv[1]), X)
    for p in ((xc + 3, 0, ZU + 13), (xc + 3, 0, ZU - 13)):
        at(A, "JD-SM6", p, Z if p[2] > ZU else -Z)
    for p in ((-40, -68, ZU - 10), (-40, -68, ZU + 22)):
        at(A, "LS-S11-64-06", p, -X)
    at(A, "LS-S9-64-04", (xc - 4, eye[0] - 2, eye[1] - 4), -X)
    at(A, "DQ-E8", (xc - 17, pin[0], pin[1]), -X)


def needle_bar():
    A = "WQ88-1400"
    # crank on the shaft end, its pin pointing to -X; the rod runs down to the stud on the needle bar block
    crank = L.lever([(0, ZU, 14), (0, ZPIN, 9), (0, ZU - 18, 18)], 10, holes=[(0, ZU, 7.1)], origin=(-6, 0, 0), u=Y, v=Z, n=X)
    crank = crank.fuse(L.cyl(11, 10, (4, 0, ZU), X).cut(L.cyl(7.1, 12, (3, 0, ZU), X)))
    crank = crank.fuse(L.cyl(6, 12, (-18, 0, ZPIN), X))
    part(A, "WQ88-1401", crank)
    part(A, "WQ88-1402", L.lever([(0, ZPIN, 12), (0, ZSTUD, 7)], 6, holes=[(0, ZPIN, 8.1), (0, ZSTUD, 3.6)],
                                 origin=(-16, 0, 0), u=Y, v=Z, n=X))
    part(A, "WQ88-1403", L.cyl(3.5, 14, (-18, 0, ZSTUD), X).fuse(L.cyl(5.5, 2, (-20, 0, ZSTUD), X)))
    part(A, "WQ88-1404", L.cyl(4, NB_TOP - NB_BOTTOM, (0, 0, NB_BOTTOM)))
    part(A, "WQ88-1405", L.tube(6, 4.05, 16, (0, 0, 250)).fuse(L.tube(8, 4.05, 2, (0, 0, 266))))
    part(A, "WQ88-1406", L.tube(6, 4.05, 18, (0, 0, 105)).fuse(L.tube(8, 4.05, 2, (0, 0, 103))))
    part(A, "WQ88-1407", L.box((-6, -8, ZSTUD - 8), (6, 8, ZSTUD + 8)).cut(L.cyl(4.05, 20, (0, 0, ZSTUD - 10))))
    part(A, "WQ88-1408", L.box((-10, 9, 150), (10, 13, 255), 2).cut(L.box((-3, 8, 160), (3, 14, 245))))
    part(A, "WQ88-1409", L.box((-5, -5, NB_BOTTOM - 14), (5, 5, NB_BOTTOM), 2).cut(L.cyl(1.05, 20, (0, 0, NB_BOTTOM - 16))))
    part(A, "WQ88-1410", L.box((-1, -9, NB_BOTTOM + 10), (1, -4, NB_BOTTOM + 13)).fuse(
        L.cyl(1.6, 2, (-1, -10, NB_BOTTOM + 11.5), X)))
    part(A, "WQ88-1411", L.tube(6, 4.05, 3, (0, 0, 246)))
    part(A, "WQ88-1412", L.tube(7, 4.05, 2, (0, 0, 100)))
    part(A, "WQ88-1413", L.box((-24, -6, ZSTUD + 6), (-18, 6, ZSTUD + 9)))
    lib_part("WQ88-1490", needle())
    at(A, "WQ88-1490", (0, 0, TIP))
    at(A, "ZC-HK1210", (-16, 0, ZPIN), X)
    for p in ((10, 0, ZU + 11), (10, 0, ZU - 11)):
        at(A, "JD-SM8", p, Z if p[2] > ZU else -Z)
    for p in ((6, 0, ZSTUD + 4), (6, 0, ZSTUD - 4)):
        at(A, "JD-SM5", p, X)
    for p in ((0, 13, 156), (0, 13, 250)):
        at(A, "LS-S11-64-08", p, Y)
    for p in ((5, 0, NB_BOTTOM - 4), (5, 0, NB_BOTTOM - 10)):
        at(A, "LS-S9-64-04", p, X)
    at(A, "LS-S9-64-06", (-21, 0, ZSTUD + 9))
    at(A, "OR-10", (0, 0, 248))


def needle():
    """Machine needle DB×1 #14, its point at the origin, shank up +Z."""
    import Part
    return Part.makeCone(0.0, 0.45, 6).fuse(L.cyl(0.45, 26, (0, 0, 6))).fuse(L.cyl(0.9, 6, (0, 0, 26))).fuse(
        L.cyl(1.0, 34, (0, 0, 32)))


def all_():
    casing()
    upper_shaft()
    takeup()
    needle_bar()
