"""演示（虚构）：压脚、夹线、下轴与旋梭、送布与针距（第 135 轮 33a）。"""
from __future__ import annotations

import copy

import lib as L
from geo import FEED_Y, LIFT_Y, PRESSER_Y, ROCK_Z, X_BELT, X_LSHAFT0, X_LSHAFT1, ZL, ZU
from lib import X, Y, Z
from reg import PLACES, at, lib_part, part

PY = PRESSER_Y


def presser():
    A = "WQ88-1500"
    part(A, "WQ88-1501", L.cyl(4.5, 270, (0, PY, 22)))
    part(A, "WQ88-1502", L.box((-8, PY - 7, 150), (8, PY + 18, 162), 2).cut(L.cyl(4.6, 20, (0, PY, 148))))
    foot = L.box((-4, PY - 6, 4), (4, PY + 4, 26), 1).fuse(L.box((-10, -14, 0), (14, PY - 2, 3.5), 2))
    foot = foot.cut(L.box((-2, -6, -1), (2, 4, 5))).fuse(L.box((-10, -18, 1), (14, -14, 6), 1))
    part(A, "WQ88-1503", foot)
    # the heavy-material foot that comes with the 7 mm models (added by the option, so placed by no BOM line)
    lib_part("WQ88-1893", foot.fuse(L.box((-10, -20, 0), (14, -14, 9), 1)))
    part(A, "WQ88-1504", L.spring(6.5, 4.5, 64, 1.4, (0, PY, 206)))
    knob = L.cyl(7, 20, (0, PY, 296)).fuse(L.cyl(5, 22, (0, PY, 274)))
    part(A, "WQ88-1505", knob)
    part(A, "WQ88-1506", L.place(L.nut(10), (0, PY, 290)))
    part(A, "WQ88-1507", L.lever([(0, 156, 6), (44, 148, 6)], 5, holes=[(44, 148, 3.1)], origin=(0, PY + 18, 0), u=X, v=Z, n=Y))
    part(A, "WQ88-1508", L.lever([(44, 148, 7), (66, 118, 5)], 4, holes=[(44, 148, 3.1)], origin=(0, 50, 0), u=X, v=Z, n=Y))
    part(A, "WQ88-1509", L.cyl(3, 16, (44, 38, 148), Y))
    part(A, "WQ88-1510", L.lever([(44, 148, 6), (72, 132, 5)], 4, holes=[(44, 148, 3.1), (72, 132, 2.1)],
                                 origin=(0, PY + 23, 0), u=X, v=Z, n=Y))
    part(A, "WQ88-1511", L.cyl(2.5, 262, (72, PY + 25, -130)).fuse(L.cyl(4, 6, (72, PY + 25, 126))))
    part(A, "WQ88-1512", L.box((-6, PY + 11, 140), (6, PY + 14, 205), 1))
    part(A, "WQ88-1513", L.cyl(1.5, 12, (-6, PY - 1, 20), X))
    at(A, "JD-SM6", (8, PY + 6, 156), X)
    at(A, "JD-SM6", (-8, PY + 6, 156), -X)
    for p in ((0, PY + 14, 150), (0, PY + 14, 195), (4, PY, 10)):
        at(A, "LS-S11-64-06", p, Y if p[2] > 100 else X)
    at(A, "LS-S15-64-08", (4, PY - 2, 18), X)
    at(A, "DQ-E10", (44, 36, 148), -Y)
    at(A, "X-3014", (72, PY + 25, 132), Y)

    K = "WQ88-1520"                               # knee lifter under the table, right of the operator's knee
    part(K, "WQ88-1521", L.cyl(6, 250, (50, -120, -80), X))
    part(K, "WQ88-1522", L.lever([(-120, -80, 9), (-100, -80, 6)], 6, holes=[(-120, -80, 6.1)],
                                 origin=(72, 0, 0), u=Y, v=Z, n=X).fuse(L.cyl(3, 10, (72, -100, -80), X)))
    part(K, "WQ88-1523", L.route([(78, -100, -80), (78, PY + 25, -125)], 2.5))
    part(K, "WQ88-1524", L.route([(286, -120, -80), (286, -150, -180), (286, -170, -280)], 3))
    part(K, "WQ88-1525", L.spring(4, 3, 40, 1, (60, -120, -80), X))
    part(K, "WQ88-1526", L.box((230, -186, -330), (330, -176, -260), 8))
    part(K, "WQ88-1527", L.box((240, -192, -320), (320, -186, -270), 10))
    lib_part("WQ88-1528", L.box((-14, -14, 0), (14, 14, 6), 2).fuse(L.box((-6, -14, -36), (6, 14, 0)).cut(
        L.cyl(6.1, 40, (-20, 0, -26), X))))
    for x in (60, 290):
        at(K, "WQ88-1528", (x, -120, -46), -Z)
    for x in (66, 280):
        at(K, "DQ-E12", (x, -120, -80), X)
    at(K, "KX-3016", (286, -170, -282), X)
    for x in (60, 290):
        for dy in (-9, 9):
            at(K, "LS-M5-12", (x, -120 + dy, -40), -Z)
            at(K, "DQ-M5", (x, -120 + dy, -40.5), -Z)

    S = "WQ88-1530"                               # automatic presser lifter: solenoid under the bed
    lib_part("WQ88-1531", L.box((-20, -20, 0), (20, 20, 60), 4).fuse(L.cyl(8, 6, (0, 0, 60))))
    at(S, "WQ88-1531", (130, 50, -160))
    part(S, "WQ88-1532", L.box((100, 25, -98), (160, 75, -94), 3).fuse(L.box((106, 28, -160), (110, 72, -94))))
    part(S, "WQ88-1533", L.lever([(130, -88, 5), (72, -125, 5)], 4, holes=[(130, -88, 2.6)], origin=(0, PY + 27, 0),
                                 u=X, v=Z, n=Y))
    part(S, "WQ88-1534", L.tube(7, 4, 4, (130, 50, -96)))
    part(S, "WQ88-1535", L.cyl(4, 20, (130, 50, -100)))
    for dy in (-12, 12):
        at(S, "LS-M4-10", (150, 50 + dy, -94))
        at(S, "DQ-M4", (150, 50 + dy, -94.6))
    at(S, "DQ-E6", (130, PY + 32, -88), Y)


def tension():
    A = "WQ88-1600"
    x, z = 80.0, 232.0
    part(A, "WQ88-1601", L.cyl(13, 4, (x, -42, z), -Y).fuse(L.box((x - 16, -44, z - 8), (x + 16, -42, z + 8), 2)))
    lib_part("WQ88-1602", L.rounded(L.tube(10, 2.6, 1.4), 0.3))
    at(A, "WQ88-1602", (x, -50, z), -Y)
    at(A, "WQ88-1602", (x, -52, z), Y)
    part(A, "WQ88-1603", L.cyl(2.5, 26, (x, -42, z), -Y))
    part(A, "WQ88-1604", L.spring(4, 1.6, 8, 0.7, (x, -54, z), -Y))
    part(A, "WQ88-1605", L.cyl(7, 6, (x, -62, z), -Y).cut(L.cyl(2.5, 8, (x, -61, z), -Y)))
    part(A, "WQ88-1606", L.cyl(1, 14, (x, -36, z), -Y))
    part(A, "WQ88-1607", __import__("Part").makeTorus(7, 0.5, L.V(x, -48, z), Y).fuse(
        L.route([(x + 7, -48, z), (x + 16, -50, z - 14)], 0.5)))
    part(A, "WQ88-1608", L.tube(9, 3, 2, (x, -44, z), -Y))
    part(A, "WQ88-1609", L.box((-49, -24, 278), (-46, -16, 286), 1).fuse(L.cyl(1.2, 6, (-52, -20, 284), X)))
    lib_part("WQ88-1610", __import__("Part").makeTorus(3, 0.8).fuse(L.cyl(1, 4, (0, 0, -6))))
    at(A, "WQ88-1610", (40, -42, 292), -Y)
    at(A, "WQ88-1610", (250, -42, 292), -Y)
    part(A, "WQ88-1611", L.route([(20, -42, 270), (20, -50, 270), (16, -50, 274)], 0.9))
    part(A, "WQ88-1612", L.box((x - 10, -40, z - 6), (x + 10, -37, z + 6), 1))
    part(A, "WQ88-1613", L.cyl(2, 60, (x + 10, -38, z), X))
    part(A, "WQ88-1614", L.box((x + 10, -48, z - 18), (x + 18, -46, z - 10)))
    for p in ((x - 12, -44, z), (x + 12, -44, z)):
        at(A, "LS-S11-64-04", p, -Y)
    for p in ((-49, -20, 282), (40, -44, 286), (250, -44, 286)):
        at(A, "LS-S9-64-05", p, -X if p[0] < 0 else -Y)
    at(A, "JD-SM5", (x, -60, z + 7))

    P = "WQ88-1620"                               # pre-tension on top of the arm, near the head
    px, py = 30.0, -18.0
    part(P, "WQ88-1621", L.box((px - 10, py - 6, 300), (px + 10, py + 6, 306), 2))
    lib_part("WQ88-1622", L.tube(6, 1.6, 1))
    at(P, "WQ88-1622", (px, py, 306))
    at(P, "WQ88-1622", (px, py, 307.2))
    part(P, "WQ88-1623", L.spring(2.6, 1.2, 6, 0.5, (px, py, 308.5)))
    part(P, "WQ88-1624", L.cyl(4.5, 4, (px, py, 315)))
    part(P, "WQ88-1625", L.cyl(1.5, 22, (px, py, 300)))
    at(P, "LS-S9-64-05", (px + 7, py, 306))

    R = "WQ88-1630"                               # active thread release: solenoid inside the arm
    part(R, "WQ88-1631", L.box((150, -32, 220), (190, -10, 244), 3).fuse(L.cyl(4, 8, (150, -21, 232), -X)))
    part(R, "WQ88-1632", L.box((146, -34, 214), (196, -8, 217), 2))
    part(R, "WQ88-1633", L.cyl(1.8, 50, (142, -24, 232), -X))
    for xx in (154, 190):
        at(R, "LS-M4-08", (xx, -21, 214), -Z)
    at(R, "DQ-E5", (96, -24, 232), -X)


def lower():
    A = "WQ88-1700"
    part(A, "WQ88-1701", L.shaft([(14, 12), (230, 14), (X_LSHAFT1 - X_LSHAFT0 - 244, 12)], (X_LSHAFT0, 0, ZL)))
    part(A, "WQ88-1702", L.tube(9.5, 7, 22, (29, 0, ZL), X).fuse(L.tube(12, 7, 3, (26, 0, ZL), X)))
    part(A, "WQ88-1703", L.tube(9.5, 6, 22, (319, 0, ZL), X))
    part(A, "WQ88-1704", L.pulley(20, 14, (X_BELT - 7, 0, ZL), X, bore=12, teeth=24))
    part(A, "WQ88-1705", L.tube(12, 7, 8, (60, 0, ZL), X))
    part(A, "WQ88-1706", L.cyl(1.5, 60, (40, 8, ZL + 10), X))
    belt = L.lever([(ZU, 0, 21.5), (ZL, 0, 21.5)], 10, origin=(X_BELT - 5, 0, 0), u=Z, v=Y, n=X)
    belt = belt.cut(L.lever([(ZU, 0, 20.2), (ZL, 0, 20.2)], 12, origin=(X_BELT - 6, 0, 0), u=Z, v=Y, n=X))
    lib_part("WQ88-1790", belt)
    at(A, "WQ88-1790", (0, 0, 0))
    at(A, "ZC-6201ZZ", (356, 0, ZL), X)
    at(A, "YF-14", (366, 0, ZL), X)
    for xx in (X_BELT, X_BELT + 4, 64, 2):
        at(A, "JD-SM8", (xx, 0, ZL + 12 if xx > 10 else ZL + 9))
    at(A, "DQ-E12", (318, 0, ZL), X)
    for xx in (35, 325):
        at(A, "LS-S15-64-08", (xx, 0, -8))

    H = "WQ88-1710"                               # rotary hook on the lower shaft end, under the needle
    hook = L.disc(16.5, 10, (-12, 0, ZL), X).cut(L.disc(12, 8, (-14, 0, ZL), X)).fuse(L.tube(8, 6, 14, (-2, 0, ZL), X))
    hook = hook.fuse(L.lever([(0, 16, 1.2), (6, 15, 2.5)], 3, origin=(-12, 0, ZL), u=Y, v=Z, n=X))
    lib_part("WQ88-1711", hook)
    at(H, "WQ88-1711", (0, 0, 0))
    part(H, "WQ88-1712", L.cyl(11.5, 9, (-15, 0, ZL), X).cut(L.cyl(10.4, 8, (-16, 0, ZL), X)).fuse(
        L.box((-17, -3, ZL - 2), (-15, 3, ZL + 2))))
    lib_part("WQ88-1713", bobbin())
    at(H, "WQ88-1713", (-14.5, 0, ZL), X)
    part(H, "WQ88-1714", L.box((-18, -14, -12), (-10, -6, -8), 1).fuse(L.box((-14, -8, -16), (-12, -4, -8))))
    part(H, "WQ88-1715", L.cyl(1.2, 20, (-8, 10, ZL + 14), X))
    for p in ((-16, -12, -8), (-12, -12, -8)):
        at(H, "LS-S9-64-04", p)
    at(H, "LS-S11-64-05", (0, 0, ZL + 8))


def bobbin():
    """A bobbin, along +Z from the origin."""
    return L.tube(10, 2.6, 1).fuse(L.tube(5, 2.6, 7, (0, 0, 1))).fuse(L.tube(10, 2.6, 1, (0, 0, 8)))


def feed():
    A = "WQ88-1800"
    part(A, "WQ88-1801", L.cyl(6, 280, (20, FEED_Y, ROCK_Z), X))
    part(A, "WQ88-1802", L.cyl(5, 190, (10, LIFT_Y, ROCK_Z), X))
    part(A, "WQ88-1803", L.disc(14, 10, (146, 0, ZL), X, bore=14, offset=(0, 2.2)))
    part(A, "WQ88-1804", L.lever([(0, ZL + 2.2, 17), (FEED_Y, ROCK_Z - 20, 6)], 6, holes=[(0, ZL + 2.2, 14.1),
                                 (FEED_Y, ROCK_Z - 20, 4.1)], origin=(148, 0, 0), u=Y, v=Z, n=X))
    part(A, "WQ88-1805", L.disc(13, 10, (116, 0, ZL), X, bore=14, offset=(1.1, 0)))
    part(A, "WQ88-1806", L.lever([(1.1, ZL, 16), (LIFT_Y, ROCK_Z - 20, 6)], 6, holes=[(1.1, ZL, 13.1),
                                 (LIFT_Y, ROCK_Z - 20, 4.1)], origin=(118, 0, 0), u=Y, v=Z, n=X))
    part(A, "WQ88-1807", L.lever([(LIFT_Y, ROCK_Z, 8), (-12, -36, 6)], 8, holes=[(LIFT_Y, ROCK_Z, 5.1)],
                                 origin=(18, 0, 0), u=Y, v=Z, n=X))
    part(A, "WQ88-1808", L.lever([(FEED_Y, ROCK_Z, 9), (FEED_Y, ROCK_Z - 20, 6)], 6, holes=[(FEED_Y, ROCK_Z, 6.1)],
                                 origin=(155, 0, 0), u=Y, v=Z, n=X))
    part(A, "WQ88-1809", L.lever([(LIFT_Y, ROCK_Z, 8), (LIFT_Y, ROCK_Z - 20, 6)], 6, holes=[(LIFT_Y, ROCK_Z, 5.1)],
                                 origin=(126, 0, 0), u=Y, v=Z, n=X))
    part(A, "WQ88-1810", L.box((-28, -10, -26), (62, 10, -16), 2).fuse(L.box((24, -10, -30), (36, 30, -20))))
    part(A, "WQ88-1811", feed_dog(0.8))
    part(A, "WQ88-1812", needle_plate(1.0))
    part(A, "WQ88-1813", L.tube(9, 6.1, 14, (20, FEED_Y, ROCK_Z), X))
    part(A, "WQ88-1814", L.tube(9, 6.1, 14, (280, FEED_Y, ROCK_Z), X))
    lib_part("WQ88-1815", L.tube(8, 5.1, 12))
    for xx in (12, 180):
        at(A, "WQ88-1815", (xx, LIFT_Y, ROCK_Z), X)
    part(A, "WQ88-1816", L.cyl(2.5, 24, (30, 6, -25), Y))
    part(A, "WQ88-1817", L.box((-16, -16, -40), (-8, -8, -32), 1))
    part(A, "WQ88-1818", L.lever([(FEED_Y, ROCK_Z, 9), (12, -24, 6)], 8, holes=[(FEED_Y, ROCK_Z, 6.1)],
                                 origin=(26, 0, 0), u=Y, v=Z, n=X))
    part(A, "WQ88-1819", L.cyl(2.5, 16, (24, 12, -24), X))
    for p in ((20, FEED_Y, ROCK_Z), (294, FEED_Y, ROCK_Z)):
        at(A, "ZC-6000ZZ", (p[0] - 4, p[1], p[2]), X)
    for p in ((148, FEED_Y, ROCK_Z - 20), (118, LIFT_Y, ROCK_Z - 20)):
        at(A, "ZC-HK0810", p, X)
    at(A, "ZC-NA4900", (18, LIFT_Y, ROCK_Z), X)
    for p in ((150, 0, ZL + 14), (120, 0, ZL + 14), (158, FEED_Y, ROCK_Z + 9), (129, LIFT_Y, ROCK_Z + 8),
              (30, FEED_Y, ROCK_Z + 9), (22, LIFT_Y, ROCK_Z + 8)):
        at(A, "JD-SM8", p)
    for p in ((27, FEED_Y, ROCK_Z + 9), (287, FEED_Y, ROCK_Z + 9), (16, LIFT_Y, ROCK_Z + 8), (186, LIFT_Y, ROCK_Z + 8)):
        at(A, "JD-SM6", p)
    for p in ((-38, -24, 0), (38, -24, 0), (-38, 24, 0), (38, 24, 0)):
        at(A, "LS-S11-64-06", p)
    for p in ((-4, 0, -16), (4, 0, -16)):
        at(A, "LS-S9-64-06", p, -Z)
    for p in ((10, LIFT_Y - 8, ROCK_Z - 6), (170, LIFT_Y - 8, ROCK_Z - 6)):
        at(A, "LS-S15-64-12", p, -Y)
    for p in ((8, LIFT_Y, ROCK_Z), (300, FEED_Y, ROCK_Z)):
        at(A, "DQ-E10", p, X)
    at(A, "X-4012", (30, -10, -21), -Y)

    S = "WQ88-1850"                               # stitch length dial and reverse lever on the pillar front
    dx, dz = 345.0, 170.0
    part(S, "WQ88-1851", L.cyl(22, 10, (dx, -55, dz), -Y).fuse(L.cyl(16, 4, (dx, -65, dz), -Y)))
    part(S, "WQ88-1852", L.cyl(4, 40, (dx, -55, dz), Y))
    part(S, "WQ88-1853", L.cyl(3, 60, (dx, -15, dz), -Z))
    part(S, "WQ88-1854", L.box((dx - 28, -57, dz + 18), (dx + 28, -55, dz + 30), 2))
    part(S, "WQ88-1855", L.box((dx - 6, -12, dz - 70), (dx + 6, 0, dz - 58), 2))
    part(S, "WQ88-1856", L.spring(4, 2.5, 20, 0.9, (dx, -6, dz - 58)))
    part(S, "WQ88-1857", L.lever([(dx, 110, 8), (dx - 46, 80, 6), (dx - 60, 78, 8)], 5, holes=[(dx, 110, 4.1)],
                                 origin=(0, -62, 0), u=X, v=Z, n=Y))
    part(S, "WQ88-1858", L.cyl(4, 50, (dx, -57, 110), Y))
    part(S, "WQ88-1859", L.spring(5, 2, 14, 1, (dx, -40, 110), Y))
    part(S, "WQ88-1860", L.route([(dx, -10, 104), (dx - 20, 0, 40), (300, FEED_Y - 6, ROCK_Z + 4)], 3))
    part(S, "WQ88-1861", L.box((294, FEED_Y - 14, ROCK_Z - 10), (316, FEED_Y + 14, ROCK_Z + 10), 2).cut(
        L.cyl(6.1, 30, (290, FEED_Y, ROCK_Z), X)))
    lib_part("WQ88-1862", L.pin(4, 16))
    at(S, "WQ88-1862", (305, FEED_Y - 14, ROCK_Z + 6), -Y)
    at(S, "WQ88-1862", (305, FEED_Y + 14, ROCK_Z + 6), Y)
    for p in ((dx, -38, 110), (dx, -40, dz)):
        at(S, "DQ-E8", p, Y)
    at(S, "DQ-E6", (dx, -10, 104), -Z)
    for p in ((dx + 10, -66, dz), (dx, -60, 118)):
        at(S, "JD-SM6", p, -Y)
    for p in ((dx - 24, -57, dz + 24), (dx + 24, -57, dz + 24)):
        at(S, "LS-S11-64-08", p, -Y)
    at(S, "OR-8", (dx, -46, dz), Y)

    R = "WQ88-1870"                               # automatic reverse: solenoid in the pillar
    part(R, "WQ88-1871", L.box((318, -22, 60), (358, 18, 96), 4).fuse(L.cyl(4, 10, (338, -2, 96))))
    part(R, "WQ88-1872", L.box((312, -26, 56), (364, 22, 59), 2).fuse(L.box((312, 19, 56), (364, 22, 100))))
    part(R, "WQ88-1873", L.lever([(dx, 110, 6), (338, 92, 5)], 4, holes=[(dx, 110, 4.1)], origin=(0, -30, 0),
                                 u=X, v=Z, n=Y))
    part(R, "WQ88-1874", L.cyl(2, 14, (338, -2, 104), -Z))
    for xx in (320, 356):
        at(R, "LS-M4-10", (xx, -2, 59))
        at(R, "DQ-M4", (xx, -2, 59.6))
    at(R, "KX-2010", (338, -2, 92), X)

    E = "WQ88-1880"                               # feed dog height: eccentric sleeve on the lift shaft
    part(E, "WQ88-1881", L.tube(8, 5.1, 10, (60, LIFT_Y, ROCK_Z), X).fuse(L.box((62, LIFT_Y - 3, ROCK_Z + 7), (68, LIFT_Y + 3, ROCK_Z + 12))))
    part(E, "WQ88-1882", L.place(L.screw(3, 8), (65, LIFT_Y, ROCK_Z + 12)))
    at(E, "JD-SM5", (65, LIFT_Y, ROCK_Z - 8), -Z)

    # 7 mm heavy material: the same feed assembly with its own feed dog and needle plate
    T = "WQ88-1890"
    part(T, "WQ88-1891", feed_dog(1.4))
    part(T, "WQ88-1892", needle_plate(1.6))
    for code, pls in PLACES[A].items():
        if code not in ("WQ88-1811", "WQ88-1812"):
            PLACES[T][code] = copy.deepcopy(pls)


def feed_dog(teeth: float):
    dog = L.box((-10, -7, -12), (10, 7, -2)).cut(L.box((-2.5, -2.5, -13), (2.5, 2.5, 0)))
    for k in range(-4, 5):
        dog = dog.fuse(L.box((2 * k - 0.6, -7, -2), (2 * k + 0.6, -3, teeth))).fuse(
            L.box((2 * k - 0.6, 3, -2), (2 * k + 0.6, 7, teeth)))
    return dog


def needle_plate(hole: float):
    p = L.box((-45, -32, -2), (45, 32, 0), 4)
    for cut in (L.cyl(hole, 4, (0, 0, -3)), L.box((-11, -8, -3), (11, -3, 1)), L.box((-11, 3, -3), (11, 8, 1))):
        p = p.cut(cut)
    for xx in range(-40, 41, 10):
        p = p.cut(L.box((xx - 0.2, -32, -0.3), (xx + 0.2, -26, 0.1)))
    return p


def all_():
    presser()
    tension()
    lower()
    feed()
