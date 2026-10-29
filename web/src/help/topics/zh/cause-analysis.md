---
title: 原因分析
group: Quality
order: 8
summary: 在不合格品报告、纠正措施或投诉上做鱼骨图和 5 Why 分析，AI 给出的建议须引用您的记录。
needs: quality:view
try:
  - id: fishbone
    text: '以 **周静**（质量）身份登录。打开 *质量工具* 的 *原因分析* 标签页，打开 **RCA-00001**，即针对被拒收的 HX-BOLT-M8 批次所做的鱼骨图。'
    to: /quality/tools?tab=causes
    expect: 各原因分布在各自的“鱼骨”上，每条都附有所依据的记录；根本原因已签字，并写入该报告 8D 的 D4。
    tour:
      - target: '[data-help="causes-list"]'
        text: 所有分析，以及它们所针对的记录。请从不合格品报告、纠正措施或投诉上开始一项分析。
        elsewhere: 请先打开质量工具的原因分析标签页。
  - id: why
    text: 打开 **RCA-00002**，即针对“M8 螺栓滑丝”投诉所做的 5 Why。自己回答“为什么 3”；如果已配置 AI，也可以点 *建议“为什么 3”的答案*。
    to: /quality/tools?tab=causes
    expect: 每个“为什么”都建立在上一个答案之上；在您接受、编辑或删除之前，AI 的建议以虚线显示。
    tour:
      - target: '[data-help="cause-whys"]'
        text: 每个“为什么”只有一个确认的答案。只有有人接受了本问的答案，下一个“为什么”才会打开。
        elsewhere: 请先打开一个 5 Why。
      - target: '[data-help="cause-suggest"]'
        text: AI 读取 *AI 读取的记录* 中列出的记录，并且必须引用它们。未引用任何所提供记录的建议会被丢弃。
        elsewhere: 请打开一项尚未结束的分析。
  - id: conclude
    text: 每条建议都处理完后，填写根本原因，输入您的密码，然后点 *得出结论并签字*。
    to: /quality/tools?tab=causes
    expect: 该记录的根本原因末尾加上了您的结论和分析编号；分析不能再修改，只能追加补充说明。
    tour:
      - target: '[data-help="cause-conclude"]'
        text: 用您的密码签字，并追加到该记录的根本原因中；原有内容保留。
        elsewhere: 请打开一项尚未结束的分析。
blocks:
  - text: AI 的建议如果没有引用提供给它的任何记录，会被丢弃，本次运行会记录丢弃了什么。
    test: tests/test_cause_analysis.py::test_fishbone_on_a_report
  - text: AI 的每条建议都须由人接受、编辑或删除，分析才能得出结论。
    test: tests/test_cause_analysis.py::test_fishbone_on_a_report
  - text: 只有上一个“为什么”的答案被接受后，下一个“为什么”才会打开；其他答案所依据的答案不能先删除。
    test: tests/test_cause_analysis.py::test_five_why_on_a_complaint_and_a_capa
  - text: 分析一旦得出结论就不再修改；后来的发现以补充说明的形式追加。
    test: tests/test_cause_analysis.py::test_fishbone_on_a_report
questions:
  - q: AI 读取哪些内容？
    a: 被分析的记录及相关记录——同一物料或同一供应商的其他报告、进货检验、投诉和生产批次，用于该物料的测量设备，近期的变更以及以前的结论。打开 *AI 读取的记录* 可以看到清单。
  - q: 能用我们自己的分类，代替常用的六类吗？
    a: 可以，但要通过 API 开始鱼骨图；在页面上开始时，分类为人员、设备、物料、方法、环境和测量。
  - q: 一定要用 AI 吗？
    a: 不用。没有模型密钥时，由人自己添加所有原因；其他功能完全一样。
---

*鱼骨图* 把一个问题的可能原因分到几个类别中——人员、设备、物料、方法、环境、测量。*5 Why* 先问问题为什么发生，
再问那又是为什么，一直问到公司可以改变的地方。两者都挂在所分析的记录上：不合格品报告、纠正措施或投诉。请从该
记录页面的底部开始。

每个原因都可以注明它所依据的记录，例如一次进货检验或以前的一份报告，这些编号会被核对。AI 可以根据同样的记录
提出原因建议；它必须引用这些记录，引用了未提供给它的记录的建议会被丢弃。在有人接受、编辑或删除之前，建议一直
以虚线显示。

结论用您的密码签字，并追加到该记录的根本原因中：报告 8D 的 D4 部分，或纠正措施、投诉的根本原因。此后分析会
原样保存。
