---
title: 供应商质量与控制图
group: Quality
order: 5
summary: 按供应商统计的事实，以及您测量数据的控制图。
video: supplier-quality
needs: quality:view
try:
  - id: suppliers
    text: 以 **周静**（质量）身份登录。打开 *质量*，选择 *供应商质量* 标签页。
    to: /quality?tab=suppliers
    expect: 按供应商列出的最近 90 天数据。海湾紧固件（演示）有一个拒收批次、一份不合格品报告，并且在 CAPA-00001 关闭之前，有一项未关闭的纠正措施。
    tour:
      - target: '[data-help="supplier-scores"]'
        text: 只列事实，全部从 ERPNext 和质量记录中统计。没有凭空打出的分数。
  - id: unknown
    text: 看 **沿海包装（演示）**。在此期间，它没有任何批次在 ERPNext 中检验过。
    expect: 它的拒收率显示“未知”，而不是 0%。
  - id: chart
    text: 选择 *SPC* 标签页，选择 **HX-BOLT-M8** 及其中径。
    to: /quality?tab=spc
    expect: 一张由每次检验读数绘成的控制图；随着中径逐渐变大，违反判异规则的点会被标出。
    tour:
      - target: '[data-help="spc-pick"]'
        text: 所有有测量值的物料和特性，数据来自进货检验、生产批次和 ERPNext 检验。
        elsewhere: 请先选择 SPC 标签页。
      - target: '[data-help="spc-chart"]'
        text: 中心线、控制限和规格限。标出的点违反了某条 Western Electric 判异规则。
  - id: signals
    text: 阅读控制图下方的 *报警信号* 和 *过程能力* 两个框。
    expect: 每条被违反的规则及对应的点；以及 Cp、Cpk、Pp 和 Ppk，连同数据个数和超出规格的个数。
    tour:
      - target: '[data-help="spc-signals"]'
        text: 每个违反规则的点，以及违反的是哪条规则。
        elsewhere: 请先选择 SPC 标签页和一个物料。
      - target: '[data-help="spc-capability"]'
        text: 只有读数同时有上、下规格限时才显示。
blocks:
  - text: 不给任何供应商打分或评级。没有检验批次的供应商，拒收率为未知，而不是 0。
    test: tests/test_quality_data.py::test_supplier_facts
  - text: 数据太少时不绘制控制图。
    test: tests/test_quality_data.py::test_individuals_and_rules
  - text: 无权查看质量记录的人看不到供应商质量。
    test: tests/test_quality_data.py::test_quality_data_api
questions:
  - q: 哪些批次计入统计？
    a: 最近 90 天内在 ERPNext 中针对采购收货提交的进货质量检验。仍在草稿页面等待确认的检验暂不计入。
  - q: 为什么用单值图，而不是均值-极差图（X-bar R）？
    a: 均值-极差图要求每次检验的读数个数相同，且在 2 到 10 个之间。否则控制图显示单个值。
  - q: 这里的让步接收指什么？
    a: 已关闭、且其处置需要批准的不合格品报告，例如处置为“让步接收”（照原样使用）。
---

侧边栏的 *质量*，*供应商质量* 标签页：按供应商列出最近 90 天的事实。已检验和被拒收的批次、拒收率、准时交货率、
不合格品报告、让步接收和未关闭的纠正措施。没有凭空打出的分数。

## 控制图（SPC）

![漂移参数的控制图](img/quality-spc.webp)

*质量*，*SPC* 标签页：ERPNext 检验中的数值读数，按物料和参数绘成控制图：每次检验的读数个数相同（2–10 个）时
用均值-极差图（X-bar R），否则用单值图。违反 Western Electric 判异规则的点会被标出。有规格限时，还会给出 Cp、
Cpk、Pp 和 Ppk。
