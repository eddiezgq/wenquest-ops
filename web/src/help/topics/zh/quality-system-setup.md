---
title: 设置质量体系
group: Quality system
order: 4
summary: 回答几个问题，系统据此建议设置。
video: quality-system-setup
needs: quality:view
try:
  - id: open
    text: 以 **周静**（质量）的身份登录。在 *质量体系* 页面保持选中 **GB/T 19001-2016 / ISO 9001**，点击 *设置* 按钮。
    to: /system/setup
    expect: “设置 GB/T 19001-2016 / ISO 9001”，共三部分。如果该标准尚未采用，页面会提示先采用它。
    tour:
      - target: '[data-help="qms-setup"]'
        path: /system
        text: 让您正在查看的标准适合贵公司的情况。
      - target: '[data-help="setup-questions"]'
        path: /system/setup
        text: 关于公司的几个问题。在您用密码声明之前，什么都不会改变。
  - id: answer
    text: 为演示公司作答：提供什么——**紧固件、电气和包装用品，经销**；是否自行设计产品——**否**；是否持有客户或供方的财产——**否**；是否使用测量设备——**是**。点击 *保存回答*。
    to: /system/setup
    expect: 在 *回答的结论* 下，设计和开发以及顾客财产标为“不适用”，测量标为“适用”，每一项都附有理由。
  - id: declare
    text: 输入密码，点击 *声明（签字）*。
    to: /system/setup
    expect: 这些控制点标为“（已声明）”；在 *质量体系* 页面上它们显示“不适用”，或参与判断。
    tour:
      - target: '[data-help="setup-declare"]'
        path: /system/setup
        text: 您的回答对每项要求意味着什么。一次签字即可全部声明。
        elsewhere: 请先保存回答。
  - id: procedures
    text: 查看 *来自您自己的程序文件*。在有公司模型密钥的情况下，勾选 **QP-11** 测量设备校准，点击 *阅读 1 份并给出建议*；逐条接受或拒绝建议。
    to: /system/setup
    expect: 生效的程序文件（演示中为 QP-05 和 QP-11），或者一条提示，说明这需要公司的模型密钥。每条建议都引用了程序文件的原文。
    tour:
      - target: '[data-help="setup-procedures"]'
        path: /system/setup
        text: 由 AI 提出建议；WenQuest Ops 核对每段引文确实出自该程序文件；由您逐条接受或拒绝。
  - id: write
    text: 在 *根据工作流生成的程序文件* 下，点击 *编写不合格品控制程序*。
    to: /system/setup
    expect: 一个指向 *不合格品控制程序* 的链接，后面注明“来自”所用的工作流，状态“待审核”。
    tour:
      - target: '[data-help="setup-written"]'
        path: /system/setup
        text: 程序文件写的就是在用工作流的实际做法。工作流修改后，请重新编写。
  - id: review-it
    text: 打开新生成的程序文件，点击 *确认*。
    expect: 一份草稿；只有其他人批准后才生效（参见 *受控文件与阅读*）。
blocks:
  - text: 回答必须与问题相符；是/否问题只接受“是”或“否”，标准没有提出的问题会被拒绝。
    test: tests/test_setup.py::test_questionnaire
  - text: 声明回答的结论需要您的密码；已经声明过的回答不会重复声明。
    test: tests/test_setup.py::test_questionnaire
  - text: 没有通过检查的建议，例如排除了始终适用的要求，或数值超出范围，不能被接受。
    test: tests/test_setup.py::test_changes_proposed_from_procedures
  - text: 接受“某项要求不适用”的建议需要您的密码。
    test: tests/test_setup.py::test_changes_proposed_from_procedures
  - text: 生成的程序文件在其他人批准之前一直是草稿，即使被确认为其他类型也是如此。
    test: tests/test_setup.py::test_procedures_written_from_the_workflow
  - text: 只能查看的人不能回答问题，也不能编写程序文件。
    test: tests/test_setup.py::test_setup_api
questions:
  - q: AI 会自行修改设置吗？
    a: 不会。每条建议都要等您接受或拒绝。接受后，所做的修改与您手动修改完全相同。
  - q: 工作流改了，生成的程序文件还对吗？
    a: 页面会标出“工作流此后已更改：请重新编写”。请重新编写；新的程序文件同样要经过批准。
---

*质量体系* 页面上的 *设置* 帮助您让标准适合贵公司的情况：

1. **关于公司。** 几个问题：您生产或提供什么，是否设计产品，是否持有客户的财产，交付后是否有活动，是否使用测量设备。
   回答会说明哪些要求可能不适用；您用密码一次性声明。
2. **来自您自己的程序文件。** 在有公司模型密钥的情况下，AI 阅读您选择的程序文件（生效的那些），并建议设置
   （例如量具多久校准一次）、哪些要求不适用，以及哪份程序文件可以证明某项要求。每条建议都引用程序文件的原文，
   WenQuest Ops 会核对引文确实存在。由您逐条接受或拒绝；接受后，所做的修改与您手动修改完全相同，而声明仍然需要您的密码。
   不合格品和纠正措施流程的修改建议在 *质量 → 工作流* 中提出。
3. **根据工作流生成的程序文件。** WenQuest Ops 根据在用的工作流编写不合格品控制程序和纠正措施程序，
   因此程序文件写的正是系统的实际做法。它们进入 *文件* 待审核，经其他人批准后生效。工作流修改后，页面会提示：请重新编写。
