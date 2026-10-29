---
title: 测量设备
group: Regulated modules
order: 2
summary: 量具、校准，以及校准不合格会影响哪些结果。
video: measuring-equipment
needs: quality:view
try:
  - id: list
    text: 打开“测量设备”。找到扭力扳手 **TW-02**，它的下次到期日已经过了。
    to: /quality/gauges
    expect: CAL-01 和 CAL-02 为“在用”；TW-02 的到期日显示为红色，并带有“（已逾期）”。
    tour:
      - target: '[data-help="gauges-list"]'
        text: 每台设备及其状态、最近一次合格校准，以及下次校准的到期时间。
  - id: overdue
    demo: /quality/gauges/3
    text: 打开 **TW-02**。
    expect: “不能使用：TW-02 的校准已于……到期”，后面是日期。
    tour:
      - target: '[data-help="gauge-usable"]'
        text: 设备今天能否使用，不能用的原因是什么。
        elsewhere: 请先从列表中打开 TW-02。
  - id: record
    demo: /quality/gauges/3
    text: 以 **周静**（质量）登录。在 TW-02 上记录一次校准：日期为今天，校准方为 **海湾计量校准实验室（演示）**，结果为“合格”。选择“记录”。
    expect: “校准已记录：需由他人批准。”以及新的一行“周静 记录”。
    tour:
      - target: '[data-help="gauge-record"]'
        text: 日期、校准方、证书、合格还是超差、校准前状态和校准后状态。
        elsewhere: 请先打开 TW-02。
  - id: approve
    demo: /quality/gauges/3
    text: 退出登录，以 **王丹**（老板）登录。打开 TW-02，用您的密码批准这次新校准。
    expect: 状态“在用”、“可以使用”，下次到期日为今天之后六个月。
    tour:
      - target: '[data-help="gauge-calibrations"]'
        text: 校准由记录它或最后修改它的人以外的人用密码批准。
        elsewhere: 请先打开 TW-02。
  - id: fail
    text: 以 **周静** 的身份打开 **CAL-01**，记录一次日期为昨天的校准，结果选“不合格（超差）”，并写明发现的情况。再以 **王丹** 的身份批准它。
    expect: CAL-01 变为“停用”，并出现一个红色框，列出自最近一次合格校准以来用它测量过的来料检验。
    tour:
      - target: '[data-help="gauge-impact"]'
        text: 自最近一次合格校准以来，这台设备测量过的内容。由质量部门判断这些结果是否仍然有效。
        elsewhere: 不合格的校准获批后，再打开 CAL-01。
  - id: assess
    text: 以 **周静** 的身份写明这些结果是否仍然有效，需要时勾选“开立不合格品报告”，然后选择“签署评估”。
    expect: 该评估出现在“超差评估”下；CAL-01 仍然停用。
  - id: back
    text: 为 CAL-01 记录一次日期为今天的合格校准，并由 **王丹** 批准。
    expect: CAL-01 恢复为“在用”。
blocks:
  - text: 记录校准的人，或最后修改它的人，不能批准它。
    test: tests/test_calibration.py::test_calibration_approved_by_someone_else
  - text: 早于最近一次已批准校准的合格校准会被拒绝；已批准的校准不能修改，在数据库里也不行。
    test: tests/test_calibration.py::test_calibration_approved_by_someone_else
  - text: 超差的设备保持停用，直到评估签字、且故障之后的一次合格校准获批；它的状态不能手动设置。
    test: tests/test_calibration.py::test_out_of_tolerance
  - text: 评估需要书面结论；一旦签字就不能修改。
    test: tests/test_calibration.py::test_out_of_tolerance
  - text: 如果来料检验所用的设备在当天处于停用状态或已过到期日，检验员不能签署该检验。
    test: tests/test_calibration.py::test_inspection_names_equipment_in_calibration
  - text: 即使关闭了“必须填写设备”的要求，检验上填写的设备仍会被检查。
    test: tests/test_calibration.py::test_named_equipment_is_checked_even_when_not_required
questions:
  - q: 为什么新设备是停用状态？
    a: 在它的第一次合格校准获批之前，一直保持停用。
  - q: 为什么我不能批准自己记录的校准？
    a: 校准由记录它或最后修改它的人以外的人用密码批准。
  - q: 用后来发现超差的设备测量过的生产批次会怎样？
    a: 它们会列入评估，并在评估签字之前一直被扣留。
---

**测量设备**列出公司的量具和仪器，以及每台的校准周期。新设备在第一次合格校准获批之前处于停用状态。记录每一次校准（日期、校准方、证书、合格还是超差、校准前状态和校准后状态）；由记录它或最后修改它的人以外的人用密码批准。合格的校准会设定下次到期日；早于最近一次合格校准的校准不能被批准。

当校准发现设备超差时，批准这次校准会使设备停用，并列出自最近一次合格校准以来用它测量过的来料检验。质量部门写明这些结果是否仍然有效并签字（同时可以开立不合格品报告）。评估签字、且故障之后的一次合格校准获批后，设备恢复在用。

只要登记了任何一台设备，来料检验就要为每个测量特性填写所用的设备；只有该设备在当天处于在用状态且未过到期日，检验员才能签字；所用的设备及其当时的到期日会随检验一起保存。这一要求可以在“来料检验 → 检验等级 → 谁可以做什么”中关闭。ISO 校准检查既读取这份清单，也读取校准登记表。
