---
title: 常见问题
group: Help
order: 1
summary: 常见问题解答。
video: questions
try:
  - id: freshness
    text: 以 **王丹**（老板）身份登录，打开 *看板*。在较宽的窗口中，阅读页面标题旁边的那一行。
    to: /
    expect: WenQuest Ops 上次读取 ERPNext 的时间。大约每 5 分钟更新一次。
    tour:
      - target: '[data-help="dashboard-asof"]'
        text: WenQuest Ops 上次读取 ERPNext 的时间。
  - id: fictional
    text: 看侧边栏顶部公司名称的下方，然后打开 *对象*，搜索 **海湾**。
    to: /objects
    expect: 海港五金供应（演示）下方的“虚构演示”，以及供应商海湾紧固件（演示）。
  - id: runs-kept
    text: 打开 *助手*，问 **缺什么？**，然后刷新页面。
    to: /assistant
    expect: 问题和回答仍在，并附有 *查找过程*。
    tour:
      - target: '[data-help="assistant-ask"]'
        text: 每个问题和回答都会保存，连同助手所走的每一步。
  - id: own-runs
    text: 以 **赵磊**（销售）身份登录，打开 *助手*。
    to: /assistant
    expect: 只有赵磊自己的问题，看不到王丹的。
blocks:
  - text: 没有记录支撑的数字显示“未知”，绝不显示 0。
    test: tests/test_overview.py::test_overview_for_the_owner
  - text: 助手不能修改 ERPNext；它准备的内容要等人确认。
    test: tests/test_drafts.py::test_ai_drafts_wait_for_a_person
  - text: 除非您是老板或 AI 专员，否则不能打开别人向助手提的问题。
    test: tests/test_ai.py::test_ai_api
questions:
  - q: 我连续输错了几次密码，现在登录不了。
    a: 连续输错 5 次密码，账号会被锁定 10 分钟。请等待，或请老板为您设置新密码，这样也会解锁账号。
  - q: 在哪里可以找到所有要测试的步骤？
    a: 在 *帮助* 页面选择 *验收清单*。它列出您能看到的各主题中所有“动手试试”的步骤。
  - q: 为什么大屏上不显示任何金额？
    a: 访客模式已开启。它只显示占比、数量和曲线，不显示客户或供应商的名称。老板可以关闭它。
---

**为什么某个数字显示“未知”？** 计算它所需的记录缺失，例如在该期间没有任何交货。系统绝不会在缺少数据时显示 0。

**数据有多新？** WenQuest Ops 每 5 分钟读取一次 ERPNext。老板可以立即启动同步。

**我在 ERPNext 中改了东西，但这里看不到。** 等下一次同步，或请老板立即同步。

**助手能修改 ERPNext 吗？** 不能。它只准备草稿；由人确认；之后采购订单由人在 ERPNext 中提交。

**为什么不能编辑已关闭的报告？** 已签字的质量记录会被锁定，这样在审核时才可信。请附理由取消，或开立一份新报告。

**AI 的回答保存在哪里？** 每次运行都会连同步骤一起记录。您能看到自己的；老板和 AI 专员能看到全部。

**这些演示数据是真的吗？** 不是。海港五金供应（演示）及其中的所有客户、供应商和物料都是虚构的。
