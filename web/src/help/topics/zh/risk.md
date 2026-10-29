---
title: 风险管理
group: Regulated modules
order: 4
summary: 风险准则、风险文件、危害和剩余风险。
video: risk
needs: quality:view
try:
  - id: criteria
    text: 打开“风险”，查看文件列表下方的公司风险准则。
    to: /quality/risk
    expect: 示例 5 × 5 矩阵，并附注“示例 - 请替换为本公司的判定准则”。
    tour:
      - target: '[data-help="risk-criteria"]'
        text: 您自己的严重度和概率等级，以及决定可接受性的矩阵。每次修改都会记录。
  - id: approved
    text: 打开 **M8 螺栓套件（KIT-M8）** 的已批准文件。读一读各项危害、它们的初始和剩余判定，以及内容指纹。
    to: /quality/risk
    expect: 状态为“已批准”，两项危害的剩余风险均可接受，并有王丹的签字。
    tour:
      - target: '[data-help="risk-files"]'
        text: 每份风险文件的当前版本。在列表上方选择草稿、已批准或所有版本。
  - id: draft
    text: 以 **周静**（质量）登录，打开 **包装（BOX-12）** 的草稿。
    to: /quality/risk
    expect: “待批准条件：”，其中列出总体剩余风险结论，以及条目 1 的风险控制措施和剩余风险。
    tour:
      - target: '[data-help="risk-hazards"]'
        text: 每项危害都写明危险情况和伤害。判定由矩阵给出，没有人手工填写。
        elsewhere: 请先打开包装（BOX-12）的草稿。
  - id: control
    text: 在危害 **纸箱太薄** 上选择“编辑”。填写风险控制措施、验证方式，剩余严重度填 **2**，剩余概率填 **1**。选择“保存危害”。
    expect: 剩余风险判定为“可接受”。
    tour:
      - target: '[data-help="risk-hazard-form"]'
        text: 不可接受的风险需要控制措施、验证方式，以及剩余严重度和概率。
        elsewhere: 请先打开包装（BOX-12）的草稿。
  - id: conclusion
    demo: /quality/risk/2
    text: 写下总体剩余风险，选择“保存”。
    expect: “待批准条件”下已没有任何内容。
    tour:
      - target: '[data-help="risk-conclusion"]'
        text: 这份文件的总体剩余风险结论。批准前必须填写。
        elsewhere: 请先打开包装（BOX-12）的草稿。
  - id: approve
    demo: /quality/risk/2
    text: 退出登录，以 **王丹**（负责人）登录，打开这份草稿，用您的密码批准。
    expect: 显示“已批准：文件现已固定。”，并有内容指纹。
    tour:
      - target: '[data-help="risk-approve"]'
        text: 由不是负责人、也没有编辑过这份文件的人批准。批准时会再次查验可接受性并保存结果。
        elsewhere: 请先以王丹的身份打开这份草稿。
  - id: new-version
    text: 在已批准的 **M8 螺栓套件（KIT-M8）** 文件上，选择“开始新版本”。
    expect: 版本 2 成为草稿，危害与原来相同。批准它后，版本 1 被取代。
blocks:
  - text: 风险文件的负责人或编辑过它的人不能批准它。
    test: tests/test_risk.py::test_file_from_draft_to_superseded
  - text: 只要有不可接受的风险缺少控制措施、验证方式或由矩阵判定的剩余风险，或者不可接受的剩余风险没有受益-风险说明，文件就不能批准。
    test: tests/test_risk.py::test_file_from_draft_to_superseded
  - text: 不属于您所设等级的严重度或概率会被拒绝。
    test: tests/test_risk.py::test_file_from_draft_to_superseded
  - text: 已批准的文件及其危害不能修改，即使在数据库里也不行；修改要放到新版本中。
    test: tests/test_risk.py::test_file_from_draft_to_superseded
  - text: 等级保持其类别和排序，等级永远不会被删除。
    test: tests/test_risk.py::test_criteria_are_the_companys
  - text: 草稿只有写明原因才能撤回，撤回的草稿不能再添加危害。
    test: tests/test_risk.py::test_withdraw_a_draft
questions:
  - q: 示例中的严重度和概率等级是标准吗？
    a: 不是。它们只是一个起点示例，必须换成您自己风险管理程序中的准则。
  - q: “未判定”是什么意思？
    a: 矩阵对这个严重度和概率组合没有给出判定。在矩阵做出判定之前，它会阻止批准。
  - q: 以后修改了准则，已批准的文件会变吗？
    a: 不会。已批准的文件保留批准时的判定、准则和内容指纹。
---

“**风险**”为每个产品或产品族保存一份风险管理文件。先在同一页面上设定公司的准则：严重度等级和概率等级（排序、名称、说明），
并在矩阵中指定哪些组合是“可接受”、“尽可能降低”或“不可接受”。这些是您风险管理程序中您自己的准则，不是标准值；
可以载入一个 5 × 5 示例作为起点，但必须替换。对准则的每次修改都会记录。

在文件中，每项危害写明危险情况和伤害，并给出严重度和概率；由矩阵决定可接受性（矩阵没有判定的组合为“未判定”，会阻止批准）。
不可接受的风险需要风险控制措施、验证方式，以及剩余严重度和概率；不可接受的剩余风险需要受益-风险说明。
文件需要一份总体剩余风险结论。由不是负责人、也没有编辑过这份文件的人用密码批准：批准时会再次查验可接受性，
并保存各项判定、所用准则和内容指纹。已批准的文件是固定的；“开始新版本”会把它复制成草稿，批准这份草稿后旧版本即被取代。
草稿可以写明原因后撤回；任何内容都不会被删除。
