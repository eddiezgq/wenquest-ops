---
title: 流程图
group: Quality
order: 10
summary: 一步一步画出生产过程（含返工回路），并把每一步关联到它的文件、PFMEA 行、检验计划、生产模板和量具。
needs: quality:view
try:
  - id: chart
    text: 以 **周静**（质量）的身份登录。打开 *流程图*，打开 **PF-00001**，即 M8 螺栓收货与配套（演示）。
    to: /quality/flow
    expect: 从收货区到发货共七步；一条从“套件称重”回到“每套配 25 只螺栓”的虚线返工回路；被拒收的批次在来料检验处离开流程。
    tour:
      - target: '[data-help="flow-charts"]'
        text: 每个过程都一步一步画出；由其他人批准，之后即固定。
        elsewhere: 请先打开“流程图”。
  - id: links
    text: 点击步骤 *套件称重*。
    to: /quality/flow
    expect: 它的关联：关于“套件内螺栓缺数”的 PFMEA 行，以及标为“校准逾期”的扭力扳手。
    tour:
      - target: '[data-help="flow-diagram"]'
        text: 点击某一步，查看它关联了什么。关联到不在生效状态的内容会标为 (!)，并会阻止批准。
        elsewhere: 请先打开一张流程图。
      - target: '[data-help="flow-step"]'
        text: 每个关联都可以打开它所指向的文件、PFMEA、检验计划、模板或量具。
        elsewhere: 请先打开一张流程图，并点击某一步。
  - id: version
    text: 点击 *开始新版本*，添加或移动一个步骤，然后请一位没有编辑过它的人批准。
    to: /quality/flow
    expect: 新版本是一份草稿副本；批准后，旧版本变为“已被取代”。
    tour:
      - target: '[data-help="flow-approve"]'
        text: 由不是负责人、也没有编辑过它的人签字批准；每个关联当时指向的内容都会被保留。
        elsewhere: 请先打开一张流程图。
blocks:
  - text: 分支要么指向流程图中的某一步，要么（报废和其他情况）离开流程；返工分支总是指向某一步。
    test: tests/test_flow.py::test_rules
  - text: 某一步关联了不在生效状态的文件、没有已批准版本的 PFMEA 行或已停用的量具时，流程图不能批准。
    test: tests/test_flow.py::test_flow_chart_on_demo_records
  - text: 已批准的流程图连同其关联当时指向的内容一起固定；之后发生变化的内容会被标出。
    test: tests/test_flow.py::test_flow_chart_on_demo_records
questions:
  - q: 它和 PFMEA 有什么关系？
    a: 流程图是 PFMEA 的骨架。把每个操作和检验关联到分析它的 PFMEA 行；没有关联的步骤会列在流程图下方，PFMEA 页面也会列出引用它的流程图步骤。
  - q: 文件改版后，关联指向哪个版本？
    a: 指向当前生效的版本。已批准的流程图保留批准时的版本，并标出已有更新的版本生效；过程是否因此改变，由人来判断。
---

*流程图* 描绘产品是如何一步一步做出来的：操作、检验、搬运、储存和等待，按先后顺序排列。分支表示偏离主路径时会发生什么——
例如偏轻的套件送回重新清点，被拒收的批次退回供应商。

每一步都可以关联它所依据的内容：员工遵循的受控文件、分析它的 PFMEA 行、来料检验计划、生产模板和测量设备。
关联会对照当前生效的内容进行检查；关联到不在生效状态的内容会阻止批准。

流程图是受控文件。由不是负责人、也没有编辑过它的人签字批准；批准后，它连同每个关联当时指向的内容和一个指纹一起保存为已批准状态，
只能通过新版本来修改。
