---
title: 旧台账
group: Documents
order: 3
summary: 导入旧的不合格品台账、纠正预防措施台账或供应商名录。
video: old-ledgers
needs: quality:view
try:
  - id: open
    text: 以 **周静**（质量）登录。在“文件”的“待审核”标签页中，打开 **不合格品台账 2025-2026.xlsx**。
    to: /documents?tab=review
    expect: 右侧有一个“作为台账导入”框。
    tour:
      - target: '[data-help="doc-ledger"]'
        text: Excel 和 CSV 文件才会显示。选择台账的种类，或让系统根据各列来判断。
        elsewhere: 请先从“待审核”标签页打开不合格品台账。
  - id: read
    text: 台账种类保持不变，选择“读取台账”。
    expect: 页面“导入不合格品台账”，标记为“待检查”，表头下有 7 行。
    tour:
      - target: '[data-help="ledger-mapping"]'
        text: 哪一列填入哪个字段；每个选项字段下面，是台账中的用词与我们用词的对应关系。
        elsewhere: 请先在不合格品台账上选择“读取台账”。
  - id: words
    text: 在“处置”这一行，找到台账中的用词 **退货**。如果它还是“未知”，请为它选择“退回供应商”。选择“保存对应关系”。
    expect: 下面各行现在显示该行的处置；只剩下一条备注，是关于状态“作废 - 重复录入”的。
    tour:
      - target: '[data-help="ledger-save"]'
        text: 保持“未知”的用词在记录中留空。导入前请先保存对应关系。
        elsewhere: 请先打开台账页面。
  - id: rows
    text: 阅读各行及其备注。
    expect: 7 行可导入，每行都显示将会变成什么。
    tour:
      - target: '[data-help="ledger-rows"]'
        text: 每一行将会变成什么。琥珀色的备注会随该行一起导入；红色的行会被跳过。
        elsewhere: 请先打开台账页面。
  - id: sign
    text: 输入您的密码，选择“导入 7 行（签字）”。
    expect: 标记“已导入”，以及一张表，列出每一行的处理结果，并链接到每条新记录。
    tour:
      - target: '[data-help="ledger-import"]'
        text: 记录由代码创建；AI 从不写入数据。导入用您的密码签字。
        elsewhere: 请先打开台账页面。
      - target: '[data-help="ledger-outcomes"]'
        text: 每一行的处理结果会永久保留，下方是签字。
  - id: records
    text: 在侧边栏中打开“质量”，查看不合格品报告。
    to: /quality
    expect: 台账中的 NCR 保留它们自己的编号（例如 NCR-2025-01）；台账中已关闭的显示为已关闭，即“在 WenQuest Ops 之前已关闭”。
  - id: again
    text: 回到“文件”中的不合格品台账，再次选择“读取台账”。
    expect: 各行上方显示“7 行已导入”。按这次读取结果导入时，这些行会全部跳过。
blocks:
  - text: 导入用您的密码签字；密码错误会被拒绝，失败的尝试会被记录。
    test: tests/test_ledgers.py::test_ncr_log_import_is_signed_and_happens_once
  - text: 一份台账只导入一次；再次读取同一个文件时，已导入的行会被跳过。
    test: tests/test_ledgers.py::test_ncr_log_import_is_signed_and_happens_once
  - text: 无法唯一确定含义的用词、日期或数量保持未知；不做任何猜测。
    test: tests/test_ledgers.py::test_rows_keep_unknowns_unknown
  - text: 对应关系中引用了表格里没有的列时，会被拒绝。
    test: tests/test_ledgers.py::test_mapping_changes_by_a_person
  - text: 只有 Excel 和 CSV 文件才能作为台账读取。采购只能导入供应商名录；没有质量记录编辑权限的人不能导入其他任何台账。
    test: tests/test_ledgers.py::test_ledgers_api
questions:
  - q: AI 把某一列认错了，怎么办？
    a: 在“各列对应哪个字段”中选择正确的列，然后选择“保存对应关系”。下面各行随即显示将要导入的内容。
  - q: 台账中已关闭的行会被 ISO 检查判定吗？
    a: 不会。以已关闭状态导入的记录算作历史，不参与判定。导入后仍未关闭的记录和其他记录一样参与判定。
  - q: 供应商名录有什么用？
    a: 它为每个还不在 ERPNext 中的供应商生成一份草稿。由采购在“草稿”中确认；已在 ERPNext 中的供应商会被跳过。
---

![各列对应哪个字段](img/ledger.webp)

文件库中的电子表格可以把它的行导入 WenQuest Ops。打开它，选择**读取台账**：

1. AI 查看各列和部分样本行，提议这是哪种台账（不合格品台账、纠正措施台账或供应商名录）、哪一列填入哪个字段，以及台账中的用词与我们用词的对应关系（“退货” → 退回供应商）。没有密钥时，由规则按列名匹配。
2. 您核对每个字段和每个用词。保持*未知*的用词在记录中留空；不做任何猜测。下面各行显示每行将会变成什么，并对无法读取的日期或数值附上备注。
3. 用您的密码**导入（签字）**。记录由代码创建；AI 从不写入数据。

- 每份 NCR 和纠正措施都保留台账中的编号和日期，并注明它来自哪个文件、哪一行。台账中已关闭的行保持关闭（“在 WenQuest Ops 之前已关闭”）；未关闭的在这里继续处理。当台账中写明的 NCR 已被导入时，纠正措施会与它关联。
- 供应商名录为每个还不在 ERPNext 中的供应商生成一份草稿；由采购在“草稿”中确认。
- 每一行只导入一次：再次读取同一份台账时，已导入的行会被跳过。

导入不合格品台账和纠正预防措施台账需要质量记录的编辑权限；导入供应商名录需要起草采购的权限。
