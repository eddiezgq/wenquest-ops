---
title: 过程 FMEA
group: Quality
order: 9
summary: 过程的失效模式，按您自己的评分标准给出严重度、发生度和探测度；RPN 自动计算；由他人批准并保存。
needs: quality:view
try:
  - id: criteria
    text: 以 **周静**（质量）登录。打开“过程 FMEA”，查看“公司的 FMEA 评分标准”。
    to: /quality/fmea
    expect: 演示公司自己对严重度、发生度和探测度 1 到 10 级的描述，以及它的规则——RPN 不低于 100 或严重度不低于 9 时需采取措施。
    tour:
      - target: '[data-help="fmea-criteria"]'
        text: 您自己的评分标准和规则，按您的程序文件设置。这里的内容都不取自任何标准。
        elsewhere: 请先打开“过程 FMEA”。
      - target: '[data-help="fmea-rule"]'
        text: 一个 RPN 阈值，或一张 S / O / D 范围查找表。规则无法判定的组合会阻止批准。
        elsewhere: 请先打开“过程 FMEA”。
  - id: pfmea
    text: 打开 **PFMEA-00001**，即 M8 螺栓收货与配套。
    to: /quality/fmea
    expect: 三行，各有 S、O、D 和计算出的 RPN（160、60、90）；按规则第一行需要采取措施，并且已有措施；由王丹批准，已固定。
    tour:
      - target: '[data-help="fmea-files"]'
        text: 每份 PFMEA 及其版本、状态，以及自批准以来针对其物料开立的不合格品报告。
        elsewhere: 请先打开“过程 FMEA”。
  - id: draft
    text: 为 PFMEA-00001 开始一个新版本。如果已设置好 AI，按“起草条目”；逐条检查起草的行，给出评分并确认，或者移除。
    to: /quality/fmea
    expect: 起草的行标记为 AI，并且没有评分；在每一行都被确认或移除之前，PFMEA 不能批准，并且须由未编辑过它的人批准。
    tour:
      - target: '[data-help="fmea-rows"]'
        text: RPN = S × O × D，自动计算。AI 起草的行会一直高亮显示，直到有人确认。
        elsewhere: 请先打开一份 PFMEA。
blocks:
  - text: RPN 以及某一行是否需要采取措施，都按公司的规则计算；规则无法判定的组合记为未确定，并阻止批准。
    test: tests/test_fmea.py::test_rules
  - text: PFMEA 由没有负责也没有编辑过它的人签字批准；批准后连同所用的评分标准和一个指纹一起固定，只能通过新版本修改。
    test: tests/test_fmea.py::test_criteria_approval_and_versions
  - text: AI 起草行时会引用它看到的记录，但从不给出评分；每一条起草的行都要等人处理。
    test: tests/test_fmea.py::test_ai_drafts_rows_without_ranks
questions:
  - q: 它和“风险”有什么区别？
    a: 风险（风险管理文件）针对产品的危害和伤害，使用严重度和概率。过程 FMEA 针对过程可能如何失效，使用严重度、发生度和探测度。两者都使用公司自己的评分标准。
  - q: 针对该物料开立了不合格品报告时会怎样？
    a: PFMEA 会列出自批准以来针对其物料的报告，由人决定某个失效模式的发生度是否需要重新评分。任何内容都不会自动改变；修改要通过新版本进行。
  - q: 能用措施优先级表代替 RPN 吗？
    a: 能。选择查找表，输入您自己的 S、O、D 范围以及每个范围对应的优先级；并说明哪些优先级需要采取措施。
---

*过程 FMEA* 逐个步骤列出一个过程可能如何失效：失效模式、它的影响、它的原因，以及已有的、用于预防原因或探测失效的控制措施。每一行按公司自己的评分标准给出三个评分——影响的严重度、原因的发生度、控制措施的探测度——WenQuest Ops 计算 RPN，即 S × O × D。公司的规则规定某一行何时需要采取措施：一个 RPN 阈值，或一张范围查找表。

PFMEA 是受控文件。由没有负责也没有编辑过它的人签字批准；批准后按批准时的样子保存，连同所用的评分标准和一个指纹，只能通过新版本修改。可以从某一行开立纠正或预防措施。

AI 可以根据该物料的相关记录——不合格品报告、检验、投诉、生产批次、原因分析的结论——起草行，并引用这些记录。它从不给出评分；由人检查每一条起草的行，给出评分并确认，或者移除。
