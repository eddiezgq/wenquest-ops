---
title: 差距报告与内审清单
group: Quality system
order: 3
summary: 缺了什么，每个差距一项待办，以及内审清单。
video: gaps-and-audits
needs: quality:view
try:
  - id: open
    text: 以 **周静**（质量）登录。在“质量体系”页面，选择“差距报告”。如果没有这个按钮，请先采用 GB/T 19001-2016 / ISO 9001（见“质量体系”）。
    to: /system/gaps
    expect: 有多少控制点未满足或未知，以及按过程列出的差距和背后的记录。
    tour:
      - target: '[data-help="qms-gaps"]'
        path: /system
        text: 采用标准后才会显示。
        elsewhere: 请先在“质量体系”中采用一项标准。
      - target: '[data-help="gaps-summary"]'
        path: /system/gaps
        text: 最近一次检查的数量。控制点满足后，检查会自动关闭对应的待办。
  - id: todo
    text: 在第一个差距上，负责人填 **王丹**，到期日选一个月后，然后选择“添加待办”。
    to: /system/gaps
    expect: 表单的位置变成“待办：”，后面是标题、王丹和到期日。
    tour:
      - target: '[data-help="gaps-todo"]'
        path: /system/gaps
        text: 每个差距都有这个框。给它建一项待办，指定负责人和到期日；之后可以修改、标记完成或放弃。
        elsewhere: 采用标准后，差距报告才会列出控制点（质量体系）。
  - id: all
    text: 选择“为每个差距建待办”。
    to: /system/gaps
    expect: 现在每个差距都有待办；“已有待办”的数量与差距数量一致。
    tour:
      - target: '[data-help="gaps-todo-all"]'
        path: /system/gaps
        text: 为每个还没有待办的差距各建一项。
        elsewhere: 采用标准且存在差距后才会出现。
  - id: drop
    text: 在一项待办上写一条备注，例如“已由 QP-04 覆盖”，然后选择“放弃”。再勾选“显示已关闭的待办”。
    to: /system/gaps
    expect: “待办已放弃。”该差距可以再建新的待办，被放弃的那项连同您的备注一起列出。
    tour:
      - target: '[data-help="gaps-closed"]'
        path: /system/gaps
        text: 已关闭的待办会保留，并记录是谁关闭的、为什么关闭。
        elsewhere: 从差距建过待办后才会出现。
  - id: checklist
    text: 回到“质量体系”，选择“内审清单”。选择过程“外部提供的产品和服务”。
    to: /system/audit
    expect: 给审核员的问题，每个问题都附有记录显示的情况、要查看的记录样本以及发现的差距。
    tour:
      - target: '[data-help="qms-audit"]'
        path: /system
        text: 采用标准后才会显示。
        elsewhere: 请先在“质量体系”中采用一项标准。
      - target: '[data-help="audit-process"]'
        path: /system/audit
        text: 全部过程，或一次一个过程。
      - target: '[data-help="audit-questions"]'
        path: /system/audit
        text: 打印出来带去审核。每个问题都留有审核员写备注的空间。
  - id: record-audit
    text: 选择“在内审登记表中记录这次审核”。
    to: /system/audit
    expect: 内审登记表。在这里记录审核及其发现，然后用密码批准。
    tour:
      - target: '[data-help="audit-register"]'
        path: /system/audit
        text: 审核结束后在这里记录（见“登记表”）。
        elsewhere: 采用标准后才会出现内审清单（质量体系）。
blocks:
  - text: 一个差距同一时间只有一项未完成的待办。
    test: tests/test_gaps.py::test_gaps_and_todos
  - text: 放弃待办需要写原因；已关闭的待办不能修改或删除，在数据库里也不行。
    test: tests/test_gaps.py::test_gaps_and_todos
  - text: 采用标准之前不会生成差距报告；只有查看权限的人不能添加待办，也不能请求起草文件。
    test: tests/test_gaps.py::test_gaps_api
  - text: AI 起草的文件，必须先经过确认，再由一位没有发起请求、没有确认也没有送审它的人用密码批准，才会生效。
    test: tests/test_gaps.py::test_the_model_drafts_a_missing_document
  - text: 没有正文或被截断的草稿不会保存。
    test: tests/test_gaps.py::test_the_model_drafts_a_missing_document
questions:
  - q: 为什么没有“用 AI 起草文件”按钮？
    a: 它需要公司的模型密钥、采用标准的权限，以及一个需要用文件来证明的差距，例如质量方针。
  - q: 待办需要我自己关闭吗？
    a: 不需要。之后的检查发现控制点已满足时，会自动关闭待办。您也可以标记完成，或写明原因后放弃。
---

“差距报告”（在“质量体系”页面上）按过程列出每个未满足或未知的控制点，以及背后的记录。给每个差距建一项待办，指定负责人和到期日，或者选择“为每个差距建待办”。之后的检查发现控制点已满足时，待办会由检查自动关闭；您也可以标记完成，或写明原因后放弃。已关闭的待办会保留。

缺少某份文件时（例如质量方针），有权采用标准的人可以选择“用 AI 起草文件”（需要公司的模型密钥）。草稿进入“文件”，标明是 AI 写的草稿；凡是需要您提供事实的地方都写着“[to fill: ...]”标记，并附有一份待填写事项清单。草稿要经过您审阅、确认，再由他人批准后才生效；之后把它关联到对应的控制点。

## 内审清单

“内审清单”把一个过程的控制点变成给审核员的问题，每个问题都附有记录显示的情况、要查看的记录样本以及发现的差距。把它打印出来带去审核，然后在内审登记表中记录这次审核及其发现。
