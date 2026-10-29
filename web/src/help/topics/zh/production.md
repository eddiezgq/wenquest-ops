---
title: 生产记录
group: Regulated modules
order: 5
summary: 模板、批次、步骤、物料和放行。
video: production
needs: quality:view
try:
  - id: template
    text: 打开“生产”，在“模板”下打开 **KIT-M8**。阅读它的三个步骤。
    to: /quality/production
    expect: 状态“已启用”，一个“清点 50 只螺栓”检查、一个 0.9 到 1.1 kg 的“整盒重量”测量和一个“标签编号”记录，并以 BOX-12 作为每个批次都要记录的物料。
    tour:
      - target: '[data-help="production-templates"]'
        text: 每个模板及其物料、版本、状态和步骤数。只能从已启用的模板开始批次。
  - id: released
    text: 把记录列表切换到“已放行”，打开已放行的 KIT-M8 批次。阅读它的步骤、物料和放行。
    to: /quality/production
    expect: 每个步骤都合格，并有记录人；“物料”下有一个 BOX-12 批次；还有王丹的签字和一个指纹。
    tour:
      - target: '[data-help="production-records"]'
        text: 每个批次一条记录。在列表上方选择“未关闭”“已放行”“已拒收”“已取消”或“全部”。
  - id: record-steps
    text: 以 **孙明**（运营经理）登录。把列表切换回“未关闭”，打开生产中的 KIT-M8 批次。用读数 **1.02** 和您的密码记录第 2 步，再用标签序列号记录第 3 步。
    to: /quality/production
    expect: 两个步骤都是“合格”，并显示孙明的名字和时间。
    tour:
      - target: '[data-help="production-record-step"]'
        text: 只能记录下一个步骤，并需要操作员的密码。测量值由 WenQuest Ops 对照限值判定。
        elsewhere: 请先打开生产中的 KIT-M8 批次。
  - id: material
    demo: /quality/production/2
    text: 在“物料”下，选择已放行的 BOX-12 批次和用量（**20**，如果剩余不足则填剩余数量）。选择“添加”。
    expect: “已记录物料。”该批次及其供应商出现在列表中。
    tour:
      - target: '[data-help="production-materials"]'
        text: 只能选择来料检验已放行的批次，用量总计不能超过该批次的数量。
        elsewhere: 请先打开生产中的 KIT-M8 批次。
  - id: submit
    demo: /quality/production/2
    text: 输入合格 **20**、报废 **0**，选择“保存”，然后选择“提交审核”。
    expect: 状态“质量审核”。
    tour:
      - target: '[data-help="production-qty"]'
        text: 合格数量和报废数量，两者合计不能超过计划数量。
        elsewhere: 请先打开生产中的 KIT-M8 批次。
  - id: release
    text: 退出登录，以 **周静**（质量）登录，打开该批次，用您的密码选择“放行（签字）”。
    expect: 状态“已放行”和一个指纹。
    tour:
      - target: '[data-help="production-decide"]'
        text: 质量部门用密码放行或拒收该批次。在这个批次中记录过步骤或物料的人不能这样做。
        elsewhere: 请先以周静的身份打开该批次。
blocks:
  - text: 起草或编辑过模板的人不能启用它；已启用模板的步骤不能修改，在数据库里也不行。
    test: tests/test_production.py::test_templates_are_controlled
  - text: 步骤按顺序记录，每一步都要操作员本人的密码；已记录的步骤不能修改。
    test: tests/test_production.py::test_lot_from_start_to_release
  - text: 物料只能来自来料检验已放行的批次，用量总计不能超过该批次的数量。
    test: tests/test_production.py::test_lot_from_start_to_release
  - text: 有不合格步骤还没有不合格品报告时，记录不能提交；该报告未关闭时，记录不能放行。
    test: tests/test_production.py::test_lot_from_start_to_release
  - text: 记录过步骤或物料的人不能放行或拒收该批次；拒收需要写原因。
    test: tests/test_production.py::test_lot_from_start_to_release
  - text: 操作员尚未确认阅读模板的文件，或在步骤要求时没有填写所用设备，就不能记录该步骤；用后来发现超差的设备测量过的批次会被扣留。
    test: tests/test_production.py::test_equipment_and_reading
questions:
  - q: 物料和工单从哪里来？
    a: 来自 ERPNext。WenQuest Ops 在此基础上加上受控的步骤、签字和放行。
  - q: 模板出了新版本，会改变已经开始的批次吗？
    a: 不会。批次开始时就复制了步骤，所以后来的版本不会改变它。
  - q: 某个步骤不合格，怎么办？
    a: 在该步骤上选择“开立不合格品”。每个不合格步骤都有报告后，记录就可以提交；这些报告都关闭后，记录就可以放行。
---

**生产**保存每个生产批次的记录（器械历史记录）。物料、批次和工单都在 ERPNext 中；WenQuest Ops 在此基础上加上受控的步骤、签字和放行。首先为一个 ERPNext 物料起草一个**模板**：它的步骤（由操作员判定合格或不合格的*检查*、有下限和/或上限的*测量*，或记录做了什么的*记录*）、步骤所遵循的受控文件，以及每个批次必须记录的物料。由未起草或编辑过它的人用密码启用；启用后模板即固定，“开始新版本”会把它复制成一份草稿（启用新版本时旧版本停用）。

从已启用的模板“开始一个批次”，填写批号或序列号（每个物料内唯一）和计划数量；步骤会被复制，因此后来的版本不会改变已经开始的批次。步骤按顺序记录，每一步都要操作员的密码。测量值由 WenQuest Ops 对照限值判定，正好等于限值也算在内；填写的设备必须在校准有效期内，某个步骤可以要求必须填写设备。当模板的文件需要阅读时，操作员必须先确认已阅读生效的版本（“我的阅读”）（这是一项设置）。不合格的步骤需要一份不合格品报告：“开立不合格品”会自动填写报告。物料从来料检验已放行的批次中记录，用量总计不能超过该批次的数量。所有步骤都已记录、合格数量已填写、必需的物料已记录后，提交记录；质量部门用密码放行或拒收：做这件事的人不能记录过任何步骤或物料，并且相关的不合格品报告都已关闭。如果某个批次用过的设备后来被发现超差，该批次会列入评估，并在评估签字之前一直被扣留。已放行和已拒收的记录带有指纹，不能再修改；生产中的记录可以写明原因后取消；任何内容都不会被删除。
