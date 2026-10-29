---
title: 纠正和预防措施
group: Quality
order: 2
summary: 找到原因，计划措施，检查是否有效。
video: corrective-actions
needs: quality:view
try:
  - id: open-list
    text: 以 **周静**（质量）登录。打开“质量”，选择“纠正措施”标签页。
    to: /quality?tab=capas
    expect: CAPA-00001“供应商滚丝超差”，处于实施阶段。
    tour:
      - target: '[data-help="quality-tabs"]'
        text: 在这里选择“纠正措施”。
      - target: '[data-help="quality-list"]'
        text: 未关闭的纠正和预防措施，以及它们的类型、状态和负责人。
  - id: read
    demo: /quality/capa/1
    text: 打开 **CAPA-00001**。阅读根本原因，以及分配给 **潘悦** 的行动。
    expect: 阶段“实施”高亮显示，有一个指向 NCR-00001 的链接，行动“供应商提交 8D 报告和首件数据”标记为逾期。
    tour:
      - target: '[data-help="capa-stages"]'
        text: 草稿、调查、实施、有效性验证、已关闭。当前阶段以深色显示。
        elsewhere: 请先打开 CAPA-00001（质量 → 纠正措施）。
      - target: '[data-help="capa-actions"]'
        text: 每项行动及其负责人和到期日。超过到期日的行动标记为逾期。
  - id: too-early
    demo: /quality/capa/1
    text: 选择“措施全部完成 — 检查有效性”。
    expect: “尚未完成的行动：供应商提交 8D 报告和首件数据”。阶段没有变化。
    tour:
      - target: '[data-help="capa-next-step"]'
        text: 本阶段的字段，以及填好后推进到下一阶段的按钮。
        elsewhere: 请先打开 CAPA-00001。
  - id: owner-done
    text: 退出登录，以 **潘悦**（采购）登录。打开 CAPA-00001，在该行动旁写上证据（例如 **已收到 8D 报告和首件检验报告**），选择“已完成”。
    expect: 一个勾、潘悦的名字和证据。潘悦不在质量部门工作，但潘悦是这项行动的负责人。
  - id: check
    text: 再次以 **周静** 登录，打开 CAPA-00001，选择“措施全部完成 — 检查有效性”。
    expect: 阶段“有效性验证”和一个“有效性检查”框。
  - id: close
    text: 写下有效性检查的证据（例如 **后续 3 批螺栓均验收合格**），输入您的密码，选择“有效 — 关闭（签字）”。
    expect: 阶段“已关闭”和周静的签字。潘悦是行动的负责人，所以潘悦不可能关闭它。
    tour:
      - target: '[data-help="capa-effectiveness"]'
        text: 选“有效”即关闭，由负责人以外的人签字。选“无效”则写明原因，退回实施阶段。
        elsewhere: 请先把 CAPA-00001 推进到有效性检查。
  - id: close-ncr
    text: 打开 **NCR-00001**，写一条备注并用您的密码关闭它。
    to: /quality?tab=ncrs
    expect: 状态“已关闭”。严重报告在其纠正措施关闭后才能关闭。
blocks:
  - text: 没有问题描述和风险等级，调查不能开始；没有隔离措施、根本原因和至少一项行动，实施不能开始。
    test: tests/test_quality.py::test_capa_stages
  - text: 行动的到期日不能是过去的日期。只有行动的负责人或质量部门可以标记完成，并且必须附上证据。
    test: tests/test_quality.py::test_capa_stages
  - text: 还有未完成的行动时，有效性检查不能开始。
    test: tests/test_quality.py::test_capa_stages
  - text: 负责人不能以“有效”关闭自己的纠正措施。
    test: tests/test_workflow.py::test_messages_and_order_as_in_phase_one
  - text: 一份不合格品报告同一时间只能有一项未关闭的纠正措施。
    test: tests/test_quality.py::test_capa_stages
  - text: 取消纠正措施需要写原因。
    test: tests/test_quality.py::test_capa_cancel_and_multiple_ncrs
questions:
  - q: 一项纠正措施能覆盖多份报告吗？
    a: 能。它可以关联多份不合格品报告，只要其中没有一份已经有另一项未关闭的纠正措施。
  - q: 检查发现措施无效时怎么办？
    a: 写上证据，选择“无效 — 退回实施”。它会回到实施阶段；增加行动后再检查一次。
  - q: 行动的负责人不在质量部门，他能标记完成吗？
    a: 能。在调查或实施阶段，行动的负责人可以附上证据标记完成，即使他没有质量记录的编辑权限。
---

在不合格品报告上用“创建纠正措施”来建立一项纠正措施。所有纠正措施都在“质量”的“纠正措施”标签页中。

**草稿 → 调查 → 实施 → 有效性验证 → 已关闭。**

- 开始调查需要：问题描述、负责人和风险等级。
- 开始实施需要：隔离措施、根本原因和至少一项行动。
- 每项行动都有负责人和到期日；由负责人附上证据标记完成，即使他不在质量部门。
- 有效性检查：选“*有效*”即关闭，由**负责人以外**的人签字；选“*无效*”则写明原因，退回实施阶段。
