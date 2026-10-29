---
title: 来料检验
group: Quality
order: 3
summary: 抽样表、检验计划、检验批次和放行决定。
video: incoming-inspection
needs: quality:view
try:
  - id: open
    text: 以 **周静**（质量）的身份登录，在侧边栏打开 *来料检验*。
    to: /quality/iqc
    expect: 在 *待检批次* 下，有一条 CBL-12-50 的收货记录，标着“无检验计划”；在 *检验* 下，有一个 BOX-12 批次为“已签字，待决定”，一个 OUTLET-DUP 批次为“进行中”。
    tour:
      - target: '[data-help="iqc-tabs"]'
        text: 检验、检验计划、公司的抽样表和检验等级。
      - target: '[data-help="iqc-waiting"]'
        text: 需要到货检验的物料的收货行。有在用检验计划的物料可以在这里抽样。
      - target: '[data-help="iqc-inspections"]'
        text: 各次检验，以及抽样时使用的检验等级和 n、Ac、Re。
  - id: table
    text: 点击 *抽样表* 标签页。
    to: /quality/iqc?tab=table
    expect: AQL 1、正常检验的三行，每一行都已对照演示公司自己的表核对。
    tour:
      - target: '[data-help="iqc-table"]'
        text: 公司自己的行。WenQuest Ops 不提供这些数值。被检验用过的行不能修改。
        elsewhere: 请先点击“抽样表”标签页。
  - id: plan
    text: 点击 *检验计划* 标签页，打开 **BOX-12** 的检验计划。
    to: /quality/iqc?tab=plans
    expect: 状态“已启用”、一个指纹，以及两个特性：纸板厚度（3.5 至 4.5 mm）和印刷清晰。
    tour:
      - target: '[data-help="iqc-plans"]'
        text: 所有检验计划及其版本。在用的计划被冻结；任何修改都是一个新版本。
        elsewhere: 请先点击“检验计划”标签页。
  - id: decide-own
    demo: /quality/iqc/3
    text: 回到 *检验*，打开状态为 *已签字，待决定* 的 BOX-12 批次。这个批次是您签字的。输入密码，点击 *放行（签字）*。
    expect: “批次须由签字检验员以外的人放行或拒收”。该批次仍未决定。
    tour:
      - target: '[data-help="iqc-summary"]'
        text: 批次、检验计划版本和所用的抽样方案。结果由代码根据读数判定。
        elsewhere: 打开状态为“已签字，待决定”的 BOX-12 批次（来料检验 → 检验）。
      - target: '[data-help="iqc-decide"]'
        text: 由检验员以外的人在这里放行或拒收批次。
  - id: release
    text: 退出登录，以 **王丹**（老板）的身份登录。打开同一次检验，写一条备注，输入密码，点击 *放行（签字）*。
    expect: 状态变为“已放行”，并有一个链接指向“草稿”页面上等待确认的 ERPNext 草稿。
  - id: finish
    demo: /quality/iqc/4
    text: 再以 **周静** 的身份登录，打开状态为 *进行中* 的 OUTLET-DUP 批次。每个读数都选 **合格**，点击 *保存读数*，然后输入密码，点击 *签字（判定批次）*。
    expect: 状态变为“已签字，待决定”，结果为“接收”。
    tour:
      - target: '[data-help="iqc-readings"]'
        text: 每个样本单位一行，每个特性一列。一个单位只要有一个读数不合格，该单位即不合格。
        elsewhere: 请先打开 OUTLET-DUP 的检验。
  - id: levels
    text: 点击 *检验等级* 标签页，查看每个供应商、每个物料已决定的批次，以及转移规则。
    to: /quality/iqc?tab=levels
    expect: 每个批次显示为 A（接收）或 R（拒收），以及默认的转移规则。
    tour:
      - target: '[data-help="iqc-levels"]'
        text: 每个供应商的每个物料当前按哪个检验等级检验。规则会建议转移；由人来转移，并写明理由。
        elsewhere: 请先点击“检验等级”标签页。
      - target: '[data-help="iqc-rules"]'
        text: 初始规则只是默认值。请按您的程序文件进行设置。
  - id: erpnext-draft
    text: 打开 *质量*，点击 *来料检验* 标签页。为 CBL-12-50 的收货记录输入样本量 **5**，点击 *起草检验*。
    to: /quality?tab=incoming
    expect: 进入“草稿”页面，其中的 ERPNext 质量检验正等待质量部门确认。
    tour:
      - target: '[data-help="incoming-receipts"]'
        text: 在 ERPNext 中标记为需要检验、但还没有检验的物料的收货记录。
        elsewhere: 请先在“质量”页面点击“来料检验”标签页。
blocks:
  - text: 检验计划须由起草人以外的人用密码启用，而且只有在抽样表中有该 AQL 的行时才能启用。启用后不能修改。
    test: tests/test_iqc.py::test_plans_frozen_once_enabled
  - text: 相互重叠的抽样表行会被拒绝；把一行标记为已核对时，必须写明对照的来源。
    test: tests/test_iqc.py::test_sampling_table_is_company_data
  - text: 没有在用的检验计划就不能检验批次；收货记录上的批次沿用收货记录的供应商和数量。
    test: tests/test_iqc.py::test_inspection_from_receipt_to_erpnext
  - text: 只有所有读数都已录入才能签字；签字后读数不能修改，检验也不能作废。
    test: tests/test_iqc.py::test_inspection_from_receipt_to_erpnext
  - text: 检验员不能放行或拒收自己检验的批次。用尚未核对的抽样表行抽样的批次，放行时必须写明理由。
    test: tests/test_iqc.py::test_inspection_from_receipt_to_erpnext
  - text: 转移检验等级需要写明理由，而且不能从放宽检验直接转到加严检验。
    test: tests/test_iqc.py::test_switching_is_suggested_and_confirmed
questions:
  - q: 样本量、Ac 和 Re 从哪里来？
    a: 来自公司的抽样表，依据检验计划的 AQL、批量和该供应商的检验等级确定。WenQuest Ops 不提供这些数值。
  - q: 被拒收的批次会怎样？
    a: 结果以一份“拒收”的 ERPNext 质量检验进入草稿，等待确认，同时开立一份不合格品报告。该检验在 ERPNext 中提交后，报告会与它关联。
  - q: 为什么我不能为某个批次开始检验？
    a: 该物料没有在用的检验计划，或该批次已在检验中，或在 *合格供应商* 中该供应商未获批准供应此物料。提示信息会说明是哪一种情况。
---

在 ERPNext 中勾选了 *Inspection Required before Purchase*（采购前需检验）的物料，到货后会列在 *质量* 页面的
*来料检验* 标签页中。在那里填写样本量并起草检验；质量部门在“草稿”页面确认；然后在 ERPNext 中录入读数。

如果要按检验计划和抽样表来检验，请使用侧边栏中的 **来料检验**：

- **抽样表**：由老板或质量部门根据公司所用标准的受控副本，录入公司抽样表的各行（AQL、检验等级、批量范围、
  样本量 n 和接收数 Ac；Re 为 Ac + 1）。WenQuest Ops 不提供这些数值。有人对照该副本核对过某一行后，
  把它标记为已核对，并写明来源。被检验用过的行不能修改：请将其归档，再新增一行。
- **检验计划**：一份物料的检验计划规定其 AQL 和要检查的特性：计量特性带下限和/或上限，或者是合格/不合格的计数特性。
  检验计划须由起草人以外的人用密码启用，启用后即被冻结；任何修改都是一个新版本。
- **检验**：从一条待检的收货行开始（也可以为不在收货记录上的批次开始）。抽样表根据批量和该供应商的检验等级给出 n、
  Ac 和 Re；批量小于样本量时逐件检验。录入读数并签字：批次由代码判定（一个样本单位只要有一个读数不合格即不合格；
  不合格单位数不超过 Ac 时批次接收）。然后由检验员以外的人用密码放行或拒收批次。结果作为 ERPNext 质量检验进入草稿，
  等待确认；被拒收的批次会开立一份不合格品报告，该检验在 ERPNext 中提交后，报告会与它关联。用尚未核对的抽样表行
  抽样的批次会被标出，放行时必须写明理由。
- **检验等级**：转移规则根据当前等级下已决定的批次，建议把某个供应商的某个物料在正常、加严和放宽检验之间转移。
  由人来转移，并写明理由。初始规则只是默认值：请按您的程序文件进行设置。谁可以做什么（“须由其他人”这类规则）
  也可以在那里关闭。
