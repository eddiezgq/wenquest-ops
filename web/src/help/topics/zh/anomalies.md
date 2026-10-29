---
title: 异常与根本原因
group: Daily work
order: 2
summary: 规则发现的问题，及其原因和影响。
video: anomalies
try:
  - id: list
    text: 以 **孙明**（运营经理）的身份登录，打开 *异常*。
    to: /anomalies
    expect: 当前的问题，其中包括 HX-BOLT-M8 不够未完成订单使用、迟交的销售订单，以及海湾紧固件（演示）的采购订单。
    tour:
      - target: '[data-help="anomalies-list"]'
        text: 每个问题及其严重程度、发现它的规则、所涉及的记录和开始时间。
  - id: open-short
    text: 打开显示 **HX-BOLT-M8** 缺货的那条异常。
    expect: 缺什么、缺多少，以及一条通常由采购处理的建议措施。
    tour:
      - target: '[data-help="anomaly-hint"]'
        text: 该怎么处理，以及通常由哪个角色处理。
        elsewhere: 请先打开 HX-BOLT-M8 的异常。
  - id: causes
    text: 阅读同一页面上的 *原因与影响*。
    expect: 本应补充螺栓的采购订单及其延迟天数，以及正在等待的订单和客户。
    tour:
      - target: '[data-help="anomaly-causes"]'
        text: 问题为什么发生（一步一步列出），以及它影响到什么。每一步都写明理由和数字。
        elsewhere: 请先打开一条异常。
  - id: acknowledge
    text: 输入一条备注，例如 **正在催海湾紧固件**，然后点击 *确认收到*。
    expect: 状态变为“已确认收到”，日志中新增一行，包含您的邮箱和备注。
    tour:
      - target: '[data-help="anomaly-status"]'
        text: 确认收到、标为处理中，或关闭它。备注可填可不填。
        elsewhere: 请先打开一条异常。
      - target: '[data-help="anomaly-log"]'
        text: 这条异常发生过的所有事情，以及是谁做的。
  - id: close
    text: 输入一条备注，点击 *关闭*。
    expect: 状态变为“已关闭”；按钮消失。
  - id: closed-list
    text: 回到 *异常*，在右上角的列表中选择 *已关闭*。
    to: /anomalies
    expect: 您刚才关闭的那条异常。
    tour:
      - target: '[data-help="anomalies-show"]'
        text: 进行中、已解决、已关闭或全部。
  - id: sales-view
    text: 以 **赵磊**（销售）的身份登录，打开 *异常*。打开一条迟交的销售订单。
    to: /anomalies
    expect: 只有订单和物料方面的问题。原因追溯到物料为止；不显示采购订单和供应商。
blocks:
  - text: 已关闭的异常不能重新打开。如果问题仍然存在，会开立一条新的异常。
    test: tests/test_anomalies.py::test_life_cycle
  - text: 一次同步正常并不会让异常变为已解决；问题必须连续两次都不再出现。
    test: tests/test_anomalies.py::test_life_cycle
  - text: 您只能看到您的角色可以查看的异常。销售不能打开采购订单的异常。
    test: tests/test_anomalies.py::test_anomaly_api_by_role
  - text: 原因与影响中不包含您的角色无权查看的记录。
    test: tests/test_anomalies.py::test_anomaly_api_by_role
questions:
  - q: 我关闭了一条异常，它又出现了，为什么？
    a: 下次检查时问题仍然存在，所以规则开立了一条新的异常。关闭异常并不能消除原因。
  - q: 问题什么时候会变为严重？
    a: 销售订单超过交货日期 7 天以上即变为严重。日志中显示为“已升级”。
  - q: 规则可以修改吗？
    a: 各项阈值（例如供应商准时交付率 90% 的目标）保存在系统的规则文件中，而不是在页面上设置。
---

每次同步后，规则会查找以下问题：

- 销售订单超过交货日期（超过 7 天为严重）；
- 7 天内到期的销售订单有物料缺货；
- 某物料不够未完成订单使用；
- 采购订单超过要求到货日期；
- 供应商准时交付率低于 90%（90 天内至少 3 个收货行）；
- 质量检验被拒收；
- 纠正措施的某一步已逾期。

每条异常都附有建议措施，以及通常负责处理的角色。

**原因与影响。** 打开一条异常（或任何订单、物料、采购订单、供应商或检验），即可看到 *为什么*，
例如 *SO-0042 在等螺栓 → 螺栓缺 50 → 采购订单迟了 6 天 → 供应商 3 个收货行中只有 1 个准时*，
以及 *影响到什么*，例如正在等待某个被拒收批次的订单和客户。每一步都写明理由和数字。

**生命周期。** *确认收到*、标为 *处理中*，或 *关闭*，每一步都可以附上备注。如果问题连续两次同步都不再出现，
异常会自动变为已解决。所有操作都会记录在日志中。

![一个迟交订单追溯到缺货物料和迟交的供应商](img/anomaly-late-order.webp)
