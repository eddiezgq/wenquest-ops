---
title: 草稿
group: Daily work
order: 4
summary: 在有人确认之前，任何内容都不会写入 ERPNext，也不会发送出去。
video: drafts
try:
  - id: open
    text: 以 **潘悦**（采购）身份登录，打开 *草稿*。
    to: /drafts
    expect: 等待您处理的草稿，或“无。”。
    tour:
      - target: '[data-help="drafts-show"]'
        text: 等待您处理、已确认、已拒收、失败或全部。
  - id: make-po
    text: 打开物料 **HX-BOLT-M8**，选择 *起草补货采购订单*。
    to: /o/Item/HX-BOLT-M8
    expect: 进入 *草稿* 页面，出现一份标有“AI 草稿”的新采购订单，供应商为海湾紧固件（演示），数量为短缺的部分。
    tour:
      - target: '[data-help="object-draft"]'
        text: 根据记录准备一份草稿。此时还没有发送到 ERPNext。
  - id: read
    text: 阅读这份草稿。
    to: /drafts
    expect: 摘要中写明短缺多少、为哪些订单短缺，以及供应商、需求日期和明细行。
    tour:
      - target: '[data-help="drafts-item"]'
        text: 准备了什么、由谁准备、依据哪些记录。
  - id: sales-cannot-see
    text: 以 **赵磊**（销售）身份登录，打开 *草稿*。
    to: /drafts
    expect: 列表中没有这份采购订单。销售不起草采购订单。
  - id: delay-message
    text: 打开 *异常*，打开一个逾期的销售订单，再打开该订单本身，选择 *起草给客户的延期通知*。
    to: /anomalies
    expect: 一份给客户的消息草稿，包含客户、主题“关于您的订单 …… 的最新情况”（含订单号），正文中不出现供应商名称。
  - id: confirm-message
    text: 在这条消息上选择 *确认*。
    to: /drafts
    expect: 状态“已确认”，并出现 *复制后发送* 按钮。系统不会发送；由您自己发送。
    tour:
      - target: '[data-help="drafts-decide"]'
        text: 确认，或填写理由后退回。按钮旁说明了确认后会发生什么。
  - id: reject-po
    text: 再次以 **潘悦** 身份登录。在那份采购订单上填写理由 **仅测试**，然后选择 *退回*。
    to: /drafts
    expect: 草稿从列表中消失。在右上角选择 *已拒收*，可以看到它及其理由。
blocks:
  - text: 有人确认之前，不会向 ERPNext 写入任何内容；确认后的采购订单在 ERPNext 中以草稿创建，不会提交。
    test: tests/test_drafts.py::test_propose_confirm_creates_an_erpnext_draft
  - text: 同一份草稿不能确认两次。
    test: tests/test_drafts.py::test_propose_confirm_creates_an_erpnext_draft
  - text: 只有允许起草该类草稿的角色才能确认它。销售不能起草采购订单；采购不能确认质量检验。
    test: tests/test_drafts.py::test_permissions_by_doctype
  - text: 已退回的草稿不能再确认，也不能再次退回。
    test: tests/test_drafts.py::test_failed_confirmation_can_be_retried_or_rejected
  - text: 草稿不能设置 ERPNext 自行设定的内容，例如单据名称或已提交状态。
    test: tests/test_drafts.py::test_clean_rejects_what_a_draft_may_not_set
  - text: 某个物料如果以前没有采购订单，就不会为它起草采购订单，因为供应商只能靠猜。
    test: tests/test_ai_drafts.py::test_purchase_order_needs_a_known_supplier_and_permission
questions:
  - q: 确认失败了，怎么办？
    a: 草稿会标为“失败”，并附上 ERPNext 返回的错误。等 ERPNext 恢复后再选择 *确认*，或者退回它。
  - q: 确认后，采购订单在哪里？
    a: 在 ERPNext 中，是一份草稿。草稿上“在 ERPNext 中：”后面的链接可以打开它；请在那里检查并提交。
  - q: 同事提到的草稿，我为什么看不到？
    a: 您只能看到您的角色可以起草的那类草稿。采购看不到给客户的消息，销售看不到采购订单。
---

草稿是助手或同事为您准备好、需要您作出决定的内容。

| 草稿 | 确认后 |
| --- | --- |
| 采购订单 | 在 ERPNext 中创建一份采购订单草稿。请在那里检查并提交。 |
| 物料申请 | 在 ERPNext 中创建一份物料申请草稿。 |
| 供应商 | 在 ERPNext 中创建该供应商。 |
| 给客户的消息 | 标记为可发送；复制后由您自己发送。 |
| 不合格品报告 | 在质量模块中开立一份不合格品报告。 |
| 质量检验 | 在 ERPNext 中为该收货创建一份检验草稿。 |

只有角色允许的人才能确认：采购确认采购订单、物料申请和供应商，销售确认给客户的消息，质量确认报告和检验。
草稿有误时，请填写理由后退回。
