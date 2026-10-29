---
title: 助手
group: Daily work
order: 3
summary: 用日常中文提问；回答会引用您的记录。
video: assistant
try:
  - id: panel
    text: 打开 **NCR-00001**，点击右下角的 *问 AI*（或按 Ctrl+J）。点击 *总结这份报告*，然后再追问一个问题。
    demo: /quality/ncr/1
    expect: 面板滑出，知道您正在看一份不合格品报告，回答中附有指向该报告的链接。在页面之间切换时，对话会一直保持打开。
    tour:
      - target: '[data-help="chat-open"]'
        text: 每个页面上都有助手。它知道当前页面和您打开的记录。
  - id: open
    text: 以 **孙明**（运营经理）的身份登录，打开 *助手*。阅读标题下方的那行字。
    to: /assistant
    expect: 由哪个引擎回答——未设置 AI 模型密钥时为“内置规则”——以及助手可以做什么。
    tour:
      - target: '[data-help="assistant-engine"]'
        text: 由哪个引擎回答。没有模型密钥时，由内置规则回答常见问题。
  - id: example
    text: 点击示例 *哪些订单迟交了，原因是什么？*
    to: /assistant
    expect: 迟交的销售订单（每个都是链接），以及过去 30 天的准时交付率。
    tour:
      - target: '[data-help="assistant-examples"]'
        text: 现成的问题。点击其中一个即可提问。
  - id: how
    text: 在回答下方展开 *查找过程*。
    expect: 助手所做的每一步，以及每一步找到了什么。
    tour:
      - target: '[data-help="assistant-steps"]'
        text: 助手为这个回答依次使用的每一个工具。
        elsewhere: 请先提一个问题。
  - id: named
    text: 提问 **HX-BOLT-M8 有什么问题？**
    to: /assistant
    expect: 该物料、它未解决的问题及其原因，并附有链接。
    tour:
      - target: '[data-help="assistant-ask"]'
        text: 用日常中文提问。要问某个订单、物料、采购订单或供应商，直接写出它的编号即可。
  - id: link
    text: 点击回答中的 **HX-BOLT-M8**。
    expect: 该物料自己的页面，显示其详情和未解决的问题。
  - id: useful
    text: 回到 *助手*，在某个回答下方“有用吗？”旁边点击 *是*。
    to: /assistant
    expect: 按钮旁显示“谢谢”。
    tour:
      - target: '[data-help="assistant-useful"]'
        text: 告诉助手这个回答是否有帮助。它会与问题一起保存。
        elsewhere: 请先提一个问题。
  - id: sales-role
    text: 以 **赵磊**（销售）的身份登录，点击示例 *我们的供应商按时交付情况如何？*
    to: /assistant
    expect: 回答说明赵磊的角色无权查看供应商准时交付数据。
blocks:
  - text: 面板只显示您的角色可以查看的记录；没有质量权限时问到质量记录，它会如实说明。
    test: tests/test_ai_chat.py::test_record_tool_and_rules
  - text: 不能打开别人的对话。
    test: tests/test_ai_chat.py::test_chat_api
  - text: 助手只读取您的角色可以查看的内容，由 AI 模型回答时也是如此。
    test: tests/test_ai.py::test_model_cannot_read_past_the_role
  - text: 如果一句话中的数字不在助手查看过的数据里，这句话会被标为未核实。
    test: tests/test_ai.py::test_model_uses_tools_and_numbers_are_checked
  - text: 助手不能使用没有提供给它的工具，例如会修改数据库的工具。
    test: tests/test_ai.py::test_unknown_tool_and_bad_arguments
  - text: 您不能打开别人的提问；只有老板和 AI 专员可以看到所有人的提问。
    test: tests/test_ai.py::test_ai_api
  - text: 助手准备的草稿在有人确认之前一直处于待确认状态。
    test: tests/test_ai_drafts.py::test_model_drafts_stay_pending
questions:
  - q: 没有 AI 模型时它能回答什么？
    a: 迟交订单、缺货物料、准时交付率、供应商准时交付率、库存价值、库存天数、未关闭的异常，以及按编号指定的订单、物料、采购订单或供应商出了什么问题。
  - q: AI 模型不可用时会怎样？
    a: 改由内置规则回答，回答会标为“规则（模型不可用）”。
  - q: 我能看到助手做了什么吗？
    a: 能。在任何回答下方展开 *查找过程* 即可。每次运行连同其步骤都会被记录。
---

用日常中文提问：*哪些订单迟交了，原因是什么？*、*哪些物料缺货？*、*海湾紧固件的情况怎么样？*、
*PO-0031 有什么问题？*

![助手根据记录回答，并附有链接](img/assistant.webp)

- 助手只读取您的角色可以查看的内容，使用的是与各页面相同的工具。它看不到数据库，也上不了互联网。
- 它会注明依据：点击回答中的订单或物料编号即可查看。
- 每个数字都必须出现在它查看过的数据中。含有找不到出处的数字的句子会被标为 **未核实**。
- 它可以准备草稿：补货采购订单、发给客户的延迟通知、不合格品报告。草稿在 **草稿** 页面等待有相应角色的人处理。
- 没有 AI 模型密钥时，由内置规则回答常见问题。系统管理员添加公司自己的 Anthropic 密钥后即可使用 Claude。

每个问题和回答都会连同助手所做的步骤一起保存。请告诉它某个回答是否有用。
