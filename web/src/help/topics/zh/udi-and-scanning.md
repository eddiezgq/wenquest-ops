---
title: 器械标签与扫码
group: Regulated modules
order: 6
summary: 记录每个物料的器械标识，为已放行的批次打印标签，扫码查找对应的记录。
video: udi-and-scanning
needs: quality:view
try:
  - id: identifier
    text: 以 **周静**（质量经理）登录。打开“生产”，然后打开“器械标识”。要添加一个标识，选择物料，选择 GS1 或 HIBCC，输入发码机构给您的标识，然后保存。
    to: /quality/udi
    demo: /quality/udi
    expect: 在演示中，HX-BOLT-M8 的 GTIN 为 09521234567899（GS1 把前缀 952 留作示例用）；它的历史记录写明是谁设置的。校验位错误的会被拒绝。
    tour:
      - target: '[data-help="udi-form"]'
        text: 发码机构给这个物料的标识。校验位错误的会被拒绝；系统不会自己编造标识。
        elsewhere: 只有质量团队能设置标识。
      - target: '[data-help="udi-list"]'
        text: 每个有标识的物料，以及是谁设置或修改的。
  - id: label
    text: 打开该物料的一个已放行批次（在演示中是 HX-BOLT-M8 的 DHR-00001），查看“器械标签”。输入失效日期后打印，或下载用于标签打印机的 ZPL 文件。
    demo: /quality/production/1
    expect: 一个 GS1 DataMatrix 码和文字 (01)09521234567899(11)…(17)…(10)<批号>。
    tour:
      - target: '[data-help="production-label"]'
        text: 已放行批次的标签。每次打印都会记录打印人和打印数量。
        elsewhere: 请先打开一个已放行的生产批次。
  - id: scan
    text: 打开“扫码”，输入或扫描标签上的文字。
    to: /scan
    expect: 读出标识、批号和日期，并附有指向物料、批次及其追溯的链接。
    tour:
      - target: '[data-help="scan-box"]'
        text: 条码扫描枪会把内容输入到这里。在手机或平板上，请使用摄像头。
blocks:
  - text: 校验位错误的 GTIN，或已分配给其他物料的 GTIN，会被拒绝。
    test: tests/test_udi.py::test_labels_and_scans
  - text: 只有已放行的批次才能打印标签，失效日期不能早于生产日期。
    test: tests/test_udi.py::test_labels_and_scans
  - text: 标识的每次修改和标签的每次打印都会保存，不能删除。
    test: tests/test_udi.py::test_labels_and_scans
  - text: 任何人都可以读码；只有质量团队能看到它匹配的记录。
    test: tests/test_udi.py::test_udi_api
questions:
  - q: 从哪里获得器械标识？
    a: 从经美国 FDA 认可的发码机构获得，例如 GS1（GTIN）或 HIBCC（标签商代码；它免费的 UDI Builder 可以制作 HIBC 标签）。WenQuest Ops 只校验标识，从不签发标识。
  - q: 这会向 FDA 发送什么内容吗？
    a: 不会。向 FDA 的 GUDID 提交器械信息，要在 GUDID 系统中进行。
  - q: 哪些扫描枪可以用？
    a: 任何能把读到的内容直接输入的 USB 或蓝牙扫描枪，以及在浏览器中使用的手机或平板摄像头。可以读取 GS1 DataMatrix、GS1-128、HIBC 码、GS1 网址和外箱上的 GTIN。请把扫描枪设置为发送 GS1 码的 GS 分隔符（大多数扫描枪以 Ctrl+] 发送，扫码框会把它写成 <GS>）；没有分隔符，就无法区分后面跟着序列号的批号。
---

医疗器械带有唯一器械标识（UDI）：型号的器械标识（DI），以及该件产品的生产标识，例如批号、序列号和日期。
在“器械标识”中记录每个物料的 DI。之后，已放行的批次就会显示它的标签，可以打印在纸上或标签打印机上。

“扫码”可以读取标签、包装箱或供应商来货上的码，找到对应的物料以及它所属的生产批次或来料批次，并附有追溯链接。
