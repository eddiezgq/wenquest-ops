---
title: 从其他系统导入
group: Documents
order: 4
summary: 把旧系统中的物料、客户、供应商、期初库存和未完成订单导入 ERPNext。
video: data-import
needs: data:import
try:
  - id: file
    text: '在您的电脑上保存一个名为 **products.csv** 的小 CSV 文件，内容为以下三行：`Product/Service Name,Sales Description,Type,Sales Price / Rate`，然后 `TEST-1,Test product,Inventory,9.50`，然后 `HX-BOLT-M8,Bolt,Inventory,68.00`。'
    expect: 一个类似 QuickBooks 物料导出的文件。
  - id: upload
    text: 以 **王丹**（老板）或 **孙明**（运营经理）身份登录。打开 *文件*，把该文件拖进去。
    to: /documents
    tour:
      - target: '[data-help="docs-drop"]'
        text: 把导出文件拖到这里。它会像其他文件一样保存在文件库中。
  - id: kind
    text: 打开该文件，在 *作为台账导入* 下选择 **物料（导入 ERPNext）** 并开始。
    expect: 各列已对应到 ERPNext 的字段：Product/Service Name 对应物料编码，Type 对应库存物料。
    tour:
      - target: '[data-help="doc-ledger"]'
        text: 选择文件里是什么内容。配置了 AI 密钥时由 AI 给出建议；没有密钥时按列名判断。
        elsewhere: 请先打开您上传的文件。
  - id: preview
    text: 查看各行。
    expect: TEST-1 可以导入；HX-BOLT-M8 显示“ERPNext 中已有，名称为 HX-BOLT-M8：已跳过”。
    tour:
      - target: '[data-help="ledger-rows"]'
        text: 每一行以及它将如何处理。此时还没有写入任何内容。
        elsewhere: 请先开始导入您的文件。
  - id: sign
    text: 输入您的密码，选择 *导入 1 行（签字）*。
    expect: “已写入 ERPNext：创建 1 条……”；WenQuest Ops 读回后，TEST-1 会链接到它的页面。
    tour:
      - target: '[data-help="ledger-import"]'
        text: 用您的密码签字。物料、客户和供应商会直接创建；期初库存和订单在 ERPNext 中为草稿，除非您勾选该选项。
        elsewhere: 请先开始导入您的文件。
  - id: again
    text: 对同一个文件再开始一次导入，查看各行。
    expect: 这次两行都被跳过。任何记录都不会重复。
blocks:
  - text: ERPNext 中已有的记录，或在文件中出现两次的记录，会被跳过，不会重复。
    test: tests/test_erp_import.py::test_items_then_stock_then_orders
  - text: 期初库存或订单中引用了 ERPNext 尚没有的物料、仓库或客户时，会等到这些先导入后再处理。
    test: tests/test_erp_import.py::test_items_then_stock_then_orders
  - text: 一张订单只要有一行无法导入，整张订单都不导入。
    test: tests/test_erp_import.py::test_refused_rows_and_a_part_of_an_order
  - text: 只有老板和运营经理可以向 ERPNext 导入，而且须用自己的密码。
    test: tests/test_erp_import.py::test_erp_import_api
questions:
  - q: 可以从哪些系统导入？
    a: 任何能导出 Excel 或 CSV 的系统。系统能识别 QuickBooks、NetSuite、SAP Business One 和 Odoo 导出文件的常用列名；其他情况请核对对应关系，或让 AI 给出建议。
  - q: 应该按什么顺序导入？
    a: 先导入物料、客户和供应商，再导入期初库存，最后导入未完成的销售订单和采购订单。后面的文件要用到前面创建的记录。
  - q: 为什么我的订单是草稿？
    a: 这样在它们生效前，会有人在 ERPNext 中检查一遍。如果想直接提交，签字时勾选该选项即可。
---

换用 ERPNext，意味着要把旧系统中的记录带过来。从旧系统导出 Excel 或 CSV，把文件放进 *文件*，然后导入为
ERPNext 的某一类数据：物料、客户、供应商、期初库存、未完成的销售订单或未完成的采购订单。

WenQuest Ops 会把各列对应到 ERPNext 的字段：依据 QuickBooks、NetSuite、SAP Business One 和 Odoo 导出文件的
常用列名，或者借助 AI（AI 会注明它用了哪些列）。对应关系由您核对和修改。预览会显示每一行：可以导入、因 ERPNext
已有而跳过，或因引用了 ERPNext 尚没有的内容而等待。无法读取的值保持未知；不会猜测任何内容。

签字后，各行会写入 ERPNext。物料、客户和供应商直接创建。期初库存合成一张库存盘点单，订单号相同的订单行合成
一张订单；两者在 ERPNext 中都是草稿，由人检查后提交，除非您选择立即提交。每一行的处理结果都会保留。如果
ERPNext 拒绝某一行或无法连接，该行会连同原因一并跳过：稍后再导入一次该文件，只会导入剩下的部分。
