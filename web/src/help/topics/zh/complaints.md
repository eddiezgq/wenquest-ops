---
title: 投诉
group: Regulated modules
order: 1
summary: 接收、调查、评估是否须上报、答复客户、关闭。
video: complaints
needs: quality:view
try:
  - id: open-closed
    text: 打开 *投诉*，把列表切换为 *已关闭*。打开关于两只五孔插座外壳开裂的那条投诉，看看它是怎样调查、决定和答复的。
    to: /quality/complaints
    expect: 状态“已关闭”、“无需上报”及其理由，以及两个签字（周静的决定、王丹的关闭）。
    tour:
      - target: '[data-help="complaints-list"]'
        text: 每条投诉的接收时间、产品、是否有人受伤、状态和上报情况。在列表上方选择未关闭、已关闭、已取消或全部。
  - id: record
    text: 以 **孙明**（运营经理）身份登录。选择 *记录投诉*，填写客户和发生了什么，然后选择 *记录*。
    to: /quality/complaints
    expect: 一个状态为“新建”的新投诉页面；按钮下方列出开始调查前还缺什么。
    tour:
      - target: '[data-help="complaints-new"]'
        text: 记录一条新投诉。能记录质量工作的人可以看到这个按钮。
      - target: '[data-help="complaints-form"]'
        click: '[data-help="complaints-new"]'
        text: 何时收到、公司何时首次知悉、来自谁、哪个产品、发生了什么、是否有人受伤、产品是否失效。
  - id: start
    demo: /quality/complaints/3
    text: 把负责人设为您自己，填写产品（例如 **OUTLET-DUP**），把 *是否有人受伤？* 设为 **否**。选择 *保存*，再选择 *开始调查*。
    expect: 状态“调查”，并出现根本原因、调查与结论、给客户的答复三个输入框。
    tour:
      - target: '[data-help="complaint-details"]'
        text: 开始调查前，必须填写负责人、产品以及是否有人受伤。
        elsewhere: 请先打开您新建的投诉（投诉，然后点它的编号）。
      - target: '[data-help="complaint-start"]'
        text: 没有缺项且全部已保存后，开始调查。
        elsewhere: 请先打开您新建的投诉。
  - id: investigate
    text: 填写根本原因以及调查与结论。选择 *保存*。
    expect: “已保存。”
  - id: decide
    demo: /quality/complaints/2
    text: 退出登录，以 **周静**（质量）身份登录。打开这条投诉，三个问题都回答 **否**，选择 *无需上报*，填写理由，并用您的密码签字。
    expect: 状态“已评估”；调查内容和问题的回答都不能再修改。
    tour:
      - target: '[data-help="complaint-assess"]'
        text: 由负责人以外的人回答三个问题并作出决定。如有回答“是”，页面会提示这通常意味着须上报，并显示截止日期。
        elsewhere: 请先以周静身份打开这条投诉。
  - id: close
    text: 填写给客户的答复并选择 *保存*。然后用您的密码签署 *关闭（签字）*。
    expect: 状态“已关闭”，以及周静的两个签字。
    tour:
      - target: '[data-help="complaint-close"]'
        text: 这里列出还缺什么。由负责人以外的人关闭投诉。
        elsewhere: 请先以周静身份打开这条投诉。
blocks:
  - text: 晚于今天的日期会被拒绝；公司首次知悉的日期晚于投诉接收日期，也会被拒绝。
    test: tests/test_complaints.py::test_from_receipt_to_close
  - text: 没有负责人、产品以及是否有人受伤的信息，调查不能开始。
    test: tests/test_complaints.py::test_from_receipt_to_close
  - text: 负责人既不能决定是否上报，也不能关闭投诉。须由其他人用自己的密码办理，而且只能在调查结论已填写、三个问题都已回答之后。
    test: tests/test_complaints.py::test_from_receipt_to_close
  - text: 一旦作出决定，调查内容和决定都不能修改，在数据库里也改不了。
    test: tests/test_complaints.py::test_from_receipt_to_close
  - text: 须上报却缺少报告编号，或缺少给客户的答复时，投诉不能关闭；已关闭的投诉不能修改或删除。
    test: tests/test_complaints.py::test_from_receipt_to_close
  - text: 重复的投诉只能附理由取消；不调查须附理由，并由负责人以外的人批准。
    test: tests/test_complaints.py::test_exceptions_no_investigation_and_cancel
questions:
  - q: WenQuest Ops 会决定投诉是否须上报吗？
    a: 不会。它提出三个问题；如有回答“是”，会提示这通常意味着须上报，并显示截止日期。由人来决定并签字。回答了“是”却决定不上报也可以，但须写明理由，并计为例外。
  - q: 上报截止期限从哪里来？
    a: 来自公司的设置，从公司首次知悉之日起算。请按您适用的法规要求设置。
  - q: 能从投诉开立不合格品报告或纠正措施吗？
    a: 可以。投诉未关闭时，投诉页面上有 *开立不合格品* 和 *建立纠正措施* 两个按钮。
---

侧边栏的 **投诉** 用于记录每条投诉：何时收到、公司何时首次知悉、来自谁、哪个产品、发生了什么、是否有人受伤、
产品是否失效。为投诉指定负责人并开始调查；记录根本原因和结论（或由质量部门批准不调查，并写明理由）。

随后由负责人以外的人用密码决定是否须向监管机构上报。WenQuest Ops 会提出三个问题（是否造成伤害；是否存在
一旦再次发生可能造成伤害的失效；是否涉及召回或纠正），如有回答“是”，会提示这通常意味着须上报，并显示从公司
首次知悉之日起算的截止日期。它从不替您决定：回答了“是”却决定不上报也可以，但须写明理由，并计为例外。截止期限
是公司的设置，请按您适用的法规要求设置。上报在 WenQuest Ops 之外进行；请把报告编号和日期填在这里。一旦作出
决定，调查内容和决定都不能再修改。

所需内容齐全后（结论、应上报时的报告、给客户的答复），由负责人以外的人用密码关闭投诉；WenQuest Ops 会一次
列出所有缺项。可以从投诉开立不合格品报告或纠正措施。重复的投诉附理由取消；任何记录都不会删除。ISO 的投诉
检查项既读取这些投诉，也读取投诉登记表。
