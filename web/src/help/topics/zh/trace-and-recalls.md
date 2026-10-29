---
title: 追溯与召回
group: Regulated modules
order: 6
summary: 批次从哪里来、到哪里去，以及如何召回。
video: trace-and-recalls
needs: quality:view
try:
  - id: drill
    text: 打开“追溯与召回”，把列表设为“已关闭”，打开 **模拟召回演练：KIT-M8**。读一读收货方、已通知和已确认的比例，以及有效性结论。
    to: /quality/recalls
    expect: 状态为“已关闭”，每个收货方都已通知，并有王丹的签字。
    tour:
      - target: '[data-help="recalls-list"]'
        text: 每次召回都列出等级、状态、负责人和开启日期。在列表上方选择草稿和进行中、已关闭、已取消或全部。
      - target: '[data-help="recalls-trace"]'
        text: 打开追溯页面。召回从一次追溯开始。
  - id: trace-lot
    text: 选择“追溯批次”。从“生产批次”开始，选择已放行的 KIT-M8 批次，然后选择“追溯”。
    to: /quality/trace
    expect: 它所用的 BOX-12 批次及其供应商、在 ERPNext 中找到的发货，以及它所在的召回。
    tour:
      - target: '[data-help="trace-pick"]'
        text: 从一个生产批次、一个来料批次或一条投诉开始。
        elsewhere: 请先打开追溯页面（追溯与召回，然后选择追溯批次）。
      - target: '[data-help="trace-back"]'
        text: 批次从哪里来。它背后的物料批次、供应商、设备和不合格品，以及用同样物料批次做出的其他批次。
        elsewhere: 请先追溯一个生产批次。
      - target: '[data-help="trace-delivered"]'
        text: 谁收到了它，读取自 ERPNext 的发货单。批号相同的行算匹配；没有批号的行列为“仅按物料”。
        elsewhere: 请先追溯一个生产批次。
  - id: trace-complaint
    text: 改从“投诉”开始，选择关于 M8 螺栓滑丝的那条投诉。
    to: /quality/trace
    expect: 提示“该投诉没有同时写明物料和批次：无法匹配”。
  - id: start
    text: 以 **周静**（质量）登录。再次追溯已放行的 KIT-M8 批次，选择“对这些批次发起召回”。
    to: /quality/trace
    expect: 一份召回草稿，显示“待开启条件：”，以及开启时将从 ERPNext 取得的发货。
    tour:
      - target: '[data-help="trace-start-recall"]'
        text: 对本次追溯中的批次发起一份召回草稿。
        elsewhere: 请先追溯一个生产批次。
  - id: open
    demo: /quality/recalls/1
    text: 写明原因，选择分级，把 **孙明** 设为负责人，并写下召回策略和监管决定。选择“保存”，然后选择“开启召回”。
    expect: 显示“已开启：收货方名单现已固定。”以及收货方名单。
    tour:
      - target: '[data-help="recall-what"]'
        text: 原因、分级和监管决定由人来决定。WenQuest Ops 不替您做这些决定。
        elsewhere: 请先打开您的召回草稿。
  - id: consignees
    demo: /quality/recalls/1
    text: 为每个收货方填写通知日期和通知方式、对方确认的日期，并在该行选择“保存”。然后写下有效性结论，选择“保存”。
    expect: 已通知和已确认的比例上升；“关闭前需要”只列出仍缺少的内容。
    tour:
      - target: '[data-help="recall-consignees"]'
        text: 每次发货一行。退回和纠正的数量合计不超过发货数量。可以在这里把名单下载为 CSV。
        elsewhere: 请先打开这次召回。
  - id: close
    text: 退出登录，以 **王丹**（负责人）登录，打开这次召回，输入您的密码，选择“关闭（签字）”。
    expect: 状态变为“已关闭”。发起并开启它的周静，以及作为负责人的孙明，都不能关闭它。
    tour:
      - target: '[data-help="recall-steps"]'
        text: 在没有任何缺项时，由不是负责人、也没有发起或开启它的人关闭。
        elsewhere: 请先以王丹的身份打开这次召回。
blocks:
  - text: 没有原因和分级，召回不能开启；只有负责人或质量人员能开启它。
    test: tests/test_recall.py::test_trace_and_recall
  - text: 召回一旦开启，收货方名单就固定下来，涉及的批次也不能再变，即使在数据库里也不行。
    test: tests/test_recall.py::test_trace_and_recall
  - text: 一条通知必须同时有日期和方式，日期在开启日和今天之间；退回和纠正的数量合计不超过发货数量。
    test: tests/test_recall.py::test_trace_and_recall
  - text: 召回的负责人、发起人或开启人都不能关闭它。
    test: tests/test_recall.py::test_trace_and_recall
  - text: 在每个收货方都已通知，并写好有效性结论、对未确认者的说明和监管决定之前，召回不能关闭。
    test: tests/test_recall.py::test_trace_and_recall
  - text: 已关闭的召回不能修改，召回永远不会被删除。
    test: tests/test_recall.py::test_trace_and_recall
questions:
  - q: 发货上的“仅按物料”是什么意思？
    a: 这一行发货单有这个物料，但没有批号，所以其中可能有这个批次。请在 ERPNext 的发货单上记录批号，以缩小范围。
  - q: 追溯会改动什么吗？
    a: 不会。追溯只读取数据；只有当您选择“对这些批次发起召回”时，才会发起召回。
  - q: 召回开启后，这个批次又发货了怎么办？
    a: 收货方名单保持固定，召回页面会提醒您召回开启后在 ERPNext 中又发出的这些批次。
---

侧栏中的“追溯与召回”列出所有召回。在那里选择“追溯批次”，或在生产记录上选择“追溯”，可以双向追踪一个批次。
从生产批次出发：它背后的来料批次、供应商、设备和不合格品报告，用同样来料批次做出的其他批次，谁收到了它，以及关于它的投诉。
从来料批次出发：用过它的每个生产批次，并继续向下追溯。从投诉出发：投诉中写明的生产批次（物料和批号相同；不区分大小写和空格）。
谁收到了某个批次，是从 ERPNext 的发货单读取的：该物料批号相同的行算匹配；该物料没有批号的行也可能包含这个批次，
所以列为“仅按物料”（请在 ERPNext 的发货单上记录批号，以缩小范围）。追溯不会改动任何内容。

召回从一次追溯开始（“对这些批次发起召回”）。在草稿中，由人写明原因、选择分级，并写下召回策略和监管决定；
WenQuest Ops 显示召回将涉及哪些发货。由负责人或质量人员开启召回：收货方名单从 ERPNext 取得后即固定。
对每个收货方，记录何时、以何种方式通知（两者都要填）、何时确认，以及退回或纠正了多少（不超过发货数量）；
页面会统计已通知、已确认和已收回的比例，并提醒召回开启后在 ERPNext 中又发出的这些批次。名单可以下载为 CSV。
在每个收货方都已通知，并写好有效性结论、对未确认者的说明和监管决定之后，由质量人员用密码关闭召回，
关闭人不能是负责人，也不能是发起或开启它的人。草稿可以写明原因后取消；任何内容都不会被删除。
