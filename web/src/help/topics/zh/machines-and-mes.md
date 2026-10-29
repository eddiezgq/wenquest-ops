---
title: 设备与 MES
group: Quality
order: 5
summary: 让 MES、测试台或量具工位发送测量数据和工序结果，并读取事件。
video: machines-and-mes
needs: quality:view
try:
  - id: token
    text: 以 **王丹**（老板）的身份登录。打开 *设备与系统*，名称填 **测试台**，勾选 *为进行中的来料检验发送测量数据*，然后点击 *生成令牌*。
    to: /integrations
    expect: 令牌只显示一次，以 wqo_ 开头；测试台出现在列表中，尚无调用记录。
    tour:
      - target: '[data-help="token-new"]'
        text: 每台设备或每个系统一个令牌，只允许做您勾选的事。
        elsewhere: 只有老板可以管理令牌。
      - target: '[data-help="token-list"]'
        text: 每个令牌及其最近一次调用。吊销一个令牌，该设备立即被拒之门外。
  - id: send
    text: 从测试台（或终端）为一次进行中的检验发送一个读数，参见下面的示例。
    expect: '"status": "pending"。检验中还没有任何内容。'
  - id: accept
    text: 以 **周静**（质量）的身份登录，打开 *设备来件*，打开这个读数，用密码接收它。演示中，有两个来自“收货量具工位（演示）”的读数在等待 IQC-00005。
    to: /quality/inbox
    demo: /quality/inbox
    expect: 读数已进入检验，带有设备标记，录入人为周静；历史记录中注明是哪台设备发送的。
    tour:
      - target: '[data-help="inbox-list"]'
        text: 设备发来、等待人来处理的内容。打开一条即可查看它，以及它将替换的读数。
blocks:
  - text: 系统只保存令牌的哈希值；已吊销的令牌，或用于其无权做的事的令牌，都会被拒绝，每次调用都会记录。
    test: tests/test_integration_api.py::test_machine_interface
  - text: 设备发送的内容在到达时即被检查，只有在有人用密码接收后才写入；拒收需要写明理由。
    test: tests/test_integration_api.py::test_measurements_wait_for_a_person
  - text: 设备发送的生产工序按顺序记录，记在接收人名下，并进行培训检查。
    test: tests/test_integration_api.py::test_production_steps_and_events
  - text: 批次被判定和报告被开立时，事件由数据库写入，不能修改。
    test: tests/test_integration_api.py::test_production_steps_and_events
questions:
  - q: 为什么设备发送的内容必须由人来接收？
    a: 记录由对它负责的人签字。设备的数据按原样保存，记录上注明是谁接收的、来自哪台设备。
  - q: WenQuest Ops 会向我们的 MES 发送数据吗？
    a: 不会主动发出任何调用。MES 从上次停下的位置读取事件（批次放行或拒收、报告开立），读取频率由它自己决定。
  - q: 这些调用的完整说明在哪里？
    a: 在 WenQuest Ops 源代码的 docs/integration-api.md 中，示例客户端见 docs/examples/mes_client.py。
---

MES、测试台、量具工位或其他系统用自己的访问令牌与 WenQuest Ops 通信。按您的授权，它可以为进行中的来料检验发送测量数据、
发送生产工序的结果，以及读取事件。示例（样本 1 的一个读数）：

```
curl -X POST https://<您的地址>/api/integration/v1/measurements \
  -H "Authorization: Bearer wqo_..." -H "content-type: application/json" \
  -d '{"inspection": "IQC-00005", "readings": [{"sample": 1, "characteristic": "纸板厚度", "value": 4.02}], "equipment": "CAL-01"}'
```

发送的内容在 *设备来件* 中等待。接收后，它会以您的签字写入记录；历史记录中会注明是哪台设备。
事件从 `GET /api/integration/v1/events?after=<您看到的最后一个 id>` 读取。
