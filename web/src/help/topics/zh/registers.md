---
title: 登记表
group: Quality system
order: 2
summary: 培训、审核、目标、风险以及标准要求的其他记录。
video: registers
needs: quality:view
try:
  - id: open
    text: 以 **周静**（质量）身份登录。在 *质量体系* 页面的 *登记表* 框中打开 *培训与能力*。
    to: /system/registers/training
    expect: 李强（QP-05 来料检验）和潘悦（QP-04 采购）的演示条目，状态都是“已记录”。
    tour:
      - target: '[data-help="qms-registers"]'
        path: /system
        text: 每个登记表一个框，并显示条目数。采用标准后才会出现。
        elsewhere: 请先在质量体系页面采用一项标准，或使用“带我去”。
      - target: '[data-help="register-entries"]'
        path: /system/registers/training
        text: 全部条目，最新的在前。已作废的条目默认隐藏，勾选“显示已作废条目”即可看到。
  - id: record
    text: 记录一个条目：人员 **李强**，培训或技能 **WI-WH-03 拣货与包装**，日期为今天，结果 *胜任*。选择 *记录*。
    to: /system/registers/training
    expect: “条目已记录。”，新条目出现在最上面。
    tour:
      - target: '[data-help="register-form"]'
        path: /system/registers/training
        text: 该登记表的字段；带红色星号的为必填。留空的字段保持未知。
  - id: change
    text: 在您的条目上选择 *修改*，填写培训人或评估人 **孙明**，然后选择 *保存修改*。
    expect: “条目已修改。”培训条目始终可以修改，不用密码批准。
  - id: audits
    text: 打开内部审核登记表。
    to: /system/registers/audits
    expect: 孙明对“收货”的演示审核，状态为“已批准”（王丹批准），没有 *修改* 按钮。
  - id: approve
    text: 记录一次由 **孙明** 对 **发货** 进行的审核，日期为今天。在该条目上选择 *批准*，输入您的密码，然后选择 *批准（签字）*。
    to: /system/registers/audits
    expect: “已批准并锁定。”，“已批准”下方显示您的名字。
  - id: void
    text: 在这条审核上选择 *作废*，填写理由“练习时录入”，输入您的密码，然后选择 *作废该条目*。
    to: /system/registers/audits
    expect: “条目已作废。”该条目被隐藏；勾选 *显示已作废条目* 可以看到它被划掉，并附有理由。
blocks:
  - text: 缺少必填字段的条目会被拒绝。
    test: tests/test_registers.py::test_entries_are_signed_locked_voided_and_judged
  - text: 已批准的条目不能修改，在数据库里也改不了；请附理由作废它，再记录一条新的。
    test: tests/test_registers.py::test_entries_are_signed_locked_voided_and_judged
  - text: 作废须写明理由；作废已批准的条目还须输入您的密码。
    test: tests/test_registers.py::test_entries_are_signed_locked_voided_and_judged
  - text: 只有内部审核和管理评审用密码批准；培训条目不能批准。
    test: tests/test_registers.py::test_entries_are_signed_locked_voided_and_judged
  - text: 条目不会被删除；每次修改都保留在其历史中。
    test: tests/test_registers.py::test_entries_are_signed_locked_voided_and_judged
questions:
  - q: 为什么某个登记表的检查项显示“未知”？
    a: 该登记表是空的。在您开始使用之前它一直是未知，绝不会被算作符合。
  - q: 能把我们原来的培训矩阵导进来吗？
    a: 可以。在 *文件* 中上传，打开后导入为“登记表：培训与能力”。已签字的登记表（例如以前的管理评审）的数据行，经签字导入后即为已批准状态。
  - q: 投诉、校准和管理评审现在记在哪里？
    a: 它们在侧边栏中各有自己的页面。检查项会把这些记录和登记表条目一起读取。
---

除了不合格品和文件，标准还要求保存其他记录。*质量体系* 为每一类都准备了登记表：培训与能力、测量设备与校准、
内部审核、管理评审、质量目标、风险和机遇、顾客反馈与投诉、供应商批准。从 *登记表* 框中打开一个（采用标准后
才会出现），用表单记录条目，条目未锁定时可以修改。内部审核和管理评审用您的密码批准，批准后即锁定。录错的条目
附理由作废；任何记录都不会删除，每次修改都会保留。

检查项会读取这些登记表：培训未过期或已跟进；设备已校准且未到期；在设定天数内有已批准的内部审核和管理评审；
每项目标和风险都按时评审；投诉按时答复；过去一年采购过的每家供应商都已批准。这些天数在 *设置* 中。登记表为空
时结果为“未知”，直到您开始使用它。

投诉、测量设备和管理评审在侧边栏中也有各自的页面（*投诉*、*测量设备*、*管理评审*）。检查项会把在那里创建的
记录和对应登记表的条目一起读取，所以在各自页面上创建的记录不必再在登记表中重复录入。

旧的电子表格，例如培训矩阵或校准台账，导入方式与不合格品台账相同：在 *文件* 中上传，打开后导入为“登记表：…”。
各列会自动对应到登记表的字段，您核对后再签字导入。
