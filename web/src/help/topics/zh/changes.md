---
title: 变更
group: Regulated modules
order: 3
summary: 评估、批准、实施并检查一项变更。
video: changes
needs: quality:view
try:
  - id: open-closed
    text: 打开“变更”，把列表切换到“已关闭”，打开 **M8 螺栓增加第二供应商**。阅读四个问题的回答、实施情况和有效性检查。
    to: /quality/changes
    expect: 状态“已关闭”和两个签字：批准和关闭。
    tour:
      - target: '[data-help="changes-list"]'
        text: 每项变更及其类型、状态、负责人和目标日期。在列表上方选择“未关闭”“已关闭”“已取消”或“全部”。
  - id: draft
    text: 把列表切换回“未关闭”，打开草稿 **发货区更换新标签打印机**。
    to: /quality/changes
    expect: 按钮下方显示“提交前需要”以及还缺少的内容，例如变更原因和四个问题的回答。
    tour:
      - target: '[data-help="change-assess"]'
        text: 由人回答的四个问题。法规问题答“是”时需要写明法规决定；确认问题答“是”时需要写明计划。
        elsewhere: 请先打开这项草稿变更。
  - id: refused
    demo: /quality/changes/2
    text: 以 **周静**（质量）登录。打开 **质检隔离仓迁至夹层隔离笼**，这项变更由周静提出并提交，然后尝试用您的密码批准它。
    expect: 被拒绝。变更须由没有提出、负责、提交或编辑过它的人批准。
    tour:
      - target: '[data-help="change-steps"]'
        text: 用密码批准，或者退回为草稿并写明需要修改的地方。
        elsewhere: 请先打开已提交的变更。
  - id: approve
    text: 退出登录，以 **王丹**（老板）登录，打开同一项变更，用您的密码批准它。
    expect: 状态“已批准”和王丹的签字。
  - id: implement
    demo: /quality/changes/1
    text: 以负责人 **孙明**（运营经理）登录。写明实施情况，选择“保存”，然后选择“标记为已实施”。
    expect: 状态“已实施”和一个“有效性检查”框。
    tour:
      - target: '[data-help="change-impl"]'
        text: 它所变更的每份文件的新版本、需要时的确认结果，以及实施情况。
        elsewhere: 请先打开已批准的变更。
  - id: effectiveness
    text: 写下有效性检查，选择“保存”。
    expect: “已保存。”孙明是这项变更的负责人，因此不能关闭它。
  - id: close
    text: 以 **周静** 登录，用您的密码选择“关闭（签字）”。
    expect: 状态“已关闭”。
blocks:
  - text: 缺少变更内容、原因、负责人、评估或四个问题中任何一个的回答时，变更不能提交。
    test: tests/test_change_control.py::test_change_from_draft_to_closed
  - text: 提交后，评估过的内容不能修改，在数据库里也不行。只有目标日期可以调整，每次调整都会记录。
    test: tests/test_change_control.py::test_change_from_draft_to_closed
  - text: 提出、负责、提交或编辑过变更的人不能批准它。
    test: tests/test_change_control.py::test_send_back_and_cancel
  - text: 只有它所变更的每份文件的新版本都在变更之后获批并已生效，并且在需要时已写明确认结果，变更才能标记为已实施。
    test: tests/test_change_control.py::test_change_from_draft_to_closed
  - text: 关闭需要有效性检查，并由负责人以外的人进行。已关闭的变更不能修改或删除。
    test: tests/test_change_control.py::test_change_from_draft_to_closed
  - text: 一旦它带来的新版本文件已经生效，变更就不能取消；只能实施并关闭。
    test: tests/test_change_control.py::test_change_from_draft_to_closed
questions:
  - q: 质量部门退回了我的变更，怎么办？
    a: 它重新成为草稿，退回原因记在历史中。按要求修改后再次提交。之后编辑过它的人不能批准它。
  - q: 提交后目标日期还能调整吗？
    a: 能。在变更关闭之前，目标日期都可以调整，每次调整都会记录。
  - q: 变更可以引用哪些文件？
    a: 只能引用已生效的文件。每份文件都有一个在变更之后获批的新版本并已生效时，变更即可实施。
---

**变更**记录对产品、过程、供应商、文件、软件或设备的变更。先提出一项草稿：变更内容、原因、负责人、它所变更的已生效文件，以及由人回答的四个问题（是否影响已经放行的产品；是否可能需要向监管部门提交申请或通报；风险管理文件是否需要更新；是否需要先进行验证或确认）。法规问题答“是”时需要写明法规决定；确认问题答“是”时需要写明计划。提交后，评估过的内容即固定（质量部门可以写明原因退回；目标日期仍可调整，每次调整都会记录）。由没有提出、负责、提交或编辑过它的人用密码批准。当它所变更的每份文件的新版本都已生效，并且在需要时已写明确认结果，变更即标记为已实施；有效性检查之后，由负责人以外的人用密码关闭。实施之前可以写明原因取消变更；任何内容都不会被删除。
