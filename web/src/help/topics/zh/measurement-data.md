---
title: 测量数据
group: Quality
order: 4
summary: 来自量具和测量设备的读数，以及您自己检验和批次的控制图。
video: measurement-data
needs: quality:view
try:
  - id: chart
    text: 以 **周静**（质量）登录。打开“质量”，进入“SPC”标签页，选择 **BOX-12 — 纸板厚度**（来自来料检验的那一项）。
    to: /quality?tab=spc
    expect: 已签字的 BOX-12 来料检验的控制图，每次检验一个点；数值较少时，Cp 和 Cpk 标注为仅供粗略参考。
    tour:
      - target: '[data-help="spc-pick"]'
        text: 来自您的来料检验、生产批次和 ERPNext 检验的物料和特性。
        elsewhere: 请先选择“SPC”标签页。
      - target: '[data-help="spc-capability"]'
        text: 由代码根据检验计划的规格限计算。上下限不全时显示“未知”。
  - id: gauge
    text: 打开一份进行中的来料检验，它的检验计划中有计量特性（在演示中是 BOX-12 的 IQC-00005）。点击第一个空的读数格，用能自动输入读数的量具测量（或输入一个数字后按回车）。
    demo: /quality/iqc/5
    expect: 光标移到同一特性的下一个样本，这样您可以依次测量每个样本。
  - id: file
    text: 在同一份检验的“测量文件”下，选择一个 CSV 文件，它的第一行写明零件和特性，例如 `Sample,纸板厚度`，之后每个零件一行（`1,4.02`、`2,3.98`）。
    demo: /quality/iqc/5
    expect: 预览把列匹配到特性，把各零件放到还没有读数的前几个样本上，此时还不写入任何内容。在演示中，样本 1-4 来自 box12-cmm-export.csv，列在文件框下方。
    tour:
      - target: '[data-help="iqc-import"]'
        text: 来自测量设备的 CSV，或 Q-DAS 文件。在您签字之前不会写入任何内容。
        elsewhere: 请先打开一份进行中的来料检验。
  - id: sign
    text: 写明测量所用的设备，输入您的密码后导入。
    expect: 读数出现在表格中，带有文件标记；文件会保存，可以从这份检验中下载。
blocks:
  - text: 只有名称一致或由您选择时，文件中的特征才会对应到某个特性；判定依据检验计划的规格限，而不是文件中的。
    test: tests/test_measurements.py::test_matching_and_placing
  - text: 文件中无法作为数字读取的值，或测量程序标记过的值，不会导入，并会列出来。
    test: tests/test_measurements.py::test_reading_files
  - text: 导入需要签字；预览后被改动过的文件或已经导入过的文件会被拒绝；校准失效的设备会被拒绝。
    test: tests/test_measurements.py::test_import_into_an_inspection
  - text: 上下限不全或没有离散度时，过程能力为“未知”，绝不判为通过。
    test: tests/test_measurements.py::test_control_charts_of_the_hubs_readings
questions:
  - q: 哪些量具和设备可以用？
    a: 能以键盘输入方式发送读数的量具（大多数带 USB 线的数显卡尺、千分尺和百分表），以及任何能导出 CSV 或 Q-DAS（.dfq）的三坐标测量机、三维扫描仪或量具软件。如果是 PDF 报告，请从测量软件中导出 CSV。
  - q: 能读取哪些格式的 CSV？
    a: 每个测量特征一行（零件、特征、坐标轴、名义值、实测值、公差，即 PC-DMIS 和 Calypso 导出的格式），或每个零件一行、每个特性一列。
  - q: 生产测量数据从哪里来？
    a: 来自生产批次中的测量步骤，由操作员记录。它们显示在同样的控制图上，每个批次一个值。
---

测量值通过三种方式进入检验：手工输入、由能自动输入读数的量具发送，或从测量设备导出的文件中导入。每个读数都写明是谁录入的；
来自文件的读数还写明是哪个文件，该文件原样保存在检验中。

“SPC”标签页根据已签字的来料检验（每次检验一个子组）、生产批次（每个批次一个值）和 ERPNext 质量检验绘制控制图。
控制限、判异规则和过程能力都由代码计算。违反规则意味着需要查看原因：“建立不合格品报告”会发起一份报告，并带入控制图上的信号。
