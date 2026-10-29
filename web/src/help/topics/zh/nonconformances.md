---
title: 不合格品报告与 8D
group: Quality
order: 1
summary: 报告、隔离、决定产品如何处置、签字。
video: nonconformances
needs: quality:view
try:
  - id: open-list
    text: 以 **周静**（质量）的身份登录。打开 *质量*，停留在 *不合格品* 标签页。
    to: /quality?tab=ncrs
    expect: NCR-00001，即针对被拒收的 HX-BOLT-M8 批次的严重不合格品报告，状态为“已处置”。
    tour:
      - target: '[data-help="quality-tabs"]'
        text: 不合格品、纠正措施、来料检验、供应商质量、控制图和工作流。
      - target: '[data-help="quality-list"]'
        text: 未关闭的报告。使用列表上方的 *显示* 可以查看已关闭或已取消的报告。
  - id: open-demo
    demo: /quality/ncr/1
    text: 打开 **NCR-00001**。阅读为隔离该批次所做的工作，以及处置方式（退回供应商）。
    expect: 右侧方框中写着“严重不合格品报告在关联的纠正措施关闭后才能关闭。”，纠正措施下列有 CAPA-00001。
    tour:
      - target: '[data-help="ncr-next-step"]'
        text: 这份报告的下一步。随着报告推进，它会随之变化。
        elsewhere: 请先打开 NCR-00001（质量 → 不合格品）。
  - id: try-close
    text: 在 **CAPA-00001** 仍未关闭时，写一条关闭说明，输入密码，点击 *关闭（签字）*。
    expect: “NCR-00001 为严重：关联的纠正措施关闭后才能关闭”。没有任何内容被签字。
  - id: new
    text: 回到 *质量*，点击 *新建不合格品*。填写标题（例如 **纸箱压坏**）和描述，选择 *轻微*，物料 **BOX-12**，数量 **20**。点击 *建立报告*。
    to: /quality?tab=ncrs
    expect: 一份新报告，状态为“未关闭”，负责人是您。
    tour:
      - target: '[data-help="ncr-new"]'
        text: 打开表单。只有有权记录质量工作的人才能看到它。
      - target: '[data-help="ncr-form"]'
        click: '[data-help="ncr-new"]'
        text: 严重不合格品报告在关闭前需要有纠正措施。
  - id: contain
    text: 写下为防止这些纸箱继续流转所做的工作（例如 **已移到收货台旁单独存放**），点击 *保存隔离措施*。
    expect: 状态变为“已隔离”，并出现 *处置* 方框。
  - id: concession
    demo: /quality/ncr/2
    text: 选择处置方式 *照用（让步接收）（需批准）*，数量 **20**，并写明理由。点击 *提交处置*。
    expect: 状态变为“待批准”，并显示“这是您提交的，须由其他人批准。”
    tour:
      - target: '[data-help="ncr-next-step"]'
        text: 处置是您提交的，所以您不能在这里批准。
        elsewhere: 请先打开您新建的报告。
  - id: approve-close
    demo: /quality/ncr/1
    text: 退出登录，以 **孙明**（运营经理）的身份登录。打开这份报告，输入密码，点击 *批准（签字）*。然后写一条关闭说明，再次输入密码，点击 *关闭（签字）*。
    expect: 状态变为“已关闭”，并有两个签字：“处置已批准”和“不合格品已关闭”。
    tour:
      - target: '[data-help="ncr-signatures"]'
        text: 每个签字都有姓名、时间和含义。签字不能修改或删除。
        elsewhere: 请先打开报告。
blocks:
  - text: 提交了需批准处置的人不能自己批准；须由其他人用自己的密码签字。
    test: tests/test_quality.py::test_concession_needs_another_persons_signed_approval
  - text: 严重不合格品报告在关联的纠正措施关闭之前不能关闭。
    test: tests/test_quality.py::test_capa_stages
  - text: 处置方式必须是公司设定的类型之一，必须写明理由，数量不得超过报告的数量。不按顺序的步骤会被拒绝。
    test: tests/test_quality.py::test_ncr_without_approval
  - text: 一次检验只能对应一份不合格品报告。
    test: tests/test_quality.py::test_ncr_without_approval
  - text: 已关闭的报告不能取消，其 8D 也不能修改。
    test: tests/test_quality.py::test_ncr_without_approval
  - text: 只有八个部分都写完，才能用密码把 8D 标记为完成；之后不能再修改。
    test: tests/test_quality.py::test_8d_is_signed
questions:
  - q: 报告从哪里来？
    a: 来料检验被拒收时会自动开立报告，无论是在 ERPNext 中拒收，还是在 *来料检验* 中拒收批次。您也可以用 *新建不合格品* 手动开立。
  - q: 哪些处置方式需要批准？
    a: 默认情况下，退回供应商、返工 / 挑选和报废都不需要批准。*照用（让步接收）* 需要由提交人以外的人批准。这些类型都是配置项。
  - q: 报告上显示“严重度未知”，我该怎么办？
    a: 从旧台账导入的报告可能没有严重程度。请在报告上选择 *轻微* 或 *严重*；选好之前报告不能关闭。
  - q: 我可以删除报告吗？
    a: 不可以。请写明理由后取消它。报告、其历史记录和签字都会保留。
---

![一份不合格品报告](img/quality-ncr.webp)

侧边栏中的 *质量* 打开时位于 *不合格品* 标签页。检验被拒收时会自动开立报告；您也可以用 *新建不合格品* 手动开立。
报告右侧的方框始终显示它的下一步。

1. **隔离**：为防止不良品继续流转所做的工作（例如，移入质检隔离仓）。
2. **处置**：退回供应商、返工 / 挑选、报废，或照用（让步接收），并写明数量和理由。
   需要批准的类型（例如 *照用*）必须由 **其他人** 用其本人密码批准。
3. **关闭**：用您的密码签字。*严重* 不合格品报告只有在其纠正措施关闭后才能关闭。

报告可以写明理由后取消。任何内容都不会被删除。

## 8D

在报告上填写八个部分，点击 *保存 8D*。*标记 8D 完成（签字）* 即为签字确认；之后不能再修改。

## 纠正措施

报告底部的 *创建纠正措施* 会开立一项与之关联的纠正或预防措施。一份报告同一时间只能有一项未关闭的纠正措施。
