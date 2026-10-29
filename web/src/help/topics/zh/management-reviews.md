---
title: 管理评审
group: Regulated modules
order: 7
summary: 输入从您的记录中统计，召开会议，由主持人签字。
video: management-reviews
needs: quality:view
try:
  - id: open-signed
    text: 打开 **MR-00001**，这是已签字的演示评审。读一读统计出的输入，以及会议针对它们写下的内容。
    to: /quality/reviews
    expect: 状态为“已签字”，输入下方有内容指纹，页面底部有王丹的签字。
    tour:
      - target: '[data-help="reviews-list"]'
        text: 每次评审都列出期间、会议日期、主持人和状态。打开 MR-00001。
  - id: start
    text: 以 **周静**（质量）登录。选择“新建评审”，期间保持为今年，然后选择“开始”。
    to: /quality/reviews
    expect: 一个新的评审草稿页面。
    tour:
      - target: '[data-help="new-review"]'
        text: 发起一次评审。只有负责人和质量人员可以。
      - target: '[data-help="review-period"]'
        click: '[data-help="new-review"]'
        text: 统计输入所依据的期间。收集输入后即固定。
  - id: collect
    text: 选择“收集输入”。
    expect: 十三个数字框，没有记录可统计的地方显示“未知”，还有一个内容指纹。
    tour:
      - target: '[data-help="review-collect"]'
        text: 从该期间的记录中统计每项输入并冻结。在签字之前随时可以重新统计；旧的指纹保留在历史中。
        elsewhere: 请先打开您的新评审（管理评审，然后点它的编号）。
      - target: '[data-help="review-inputs"]'
        text: 各项输入，每项一个框。会议在每个框下方写下评价。
  - id: meeting
    demo: /quality/reviews/1
    text: 填写会议日期（今天）、出席人员、主持人（**王丹**）、至少一项输入下的评价以及结论。选择“保存”。
    expect: 显示“已保存。”，页面底部列出签字前还缺什么。
    tour:
      - target: '[data-help="review-meeting"]'
        text: 会议日期、签字的主持人以及出席人员。
        elsewhere: 请先打开您的新评审。
      - target: '[data-help="review-conclusion"]'
        text: 质量体系是否适宜、充分和有效？然后保存。
  - id: action
    demo: /quality/reviews/1
    text: 添加一项措施，指定负责人（例如潘悦）和几周后的到期日期。
    tour:
      - target: '[data-help="review-actions"]'
        text: 会议决定的事项，每项都有负责人和日期。负责人之后凭证据把它们标为完成。
        elsewhere: 请先打开您的新评审。
  - id: chair-signs
    text: 退出登录，以 **王丹** 登录，打开这次评审，用您的密码签字。
    expect: 状态变为“已签字”；评审不能再修改。
    tour:
      - target: '[data-help="review-sign"]'
        text: 只有主持人能看到密码框，而且只在没有缺项时显示。
        elsewhere: 请先以王丹的身份打开这次评审。
  - id: iso
    text: 打开“质量体系”，查看管理评审这一控制点。
    to: /system
    expect: 已满足，证据是您的这次评审（附有链接）。
blocks:
  - text: 收集输入、写评价或结论、或添加措施的人，不能作为主持人签字。
    test: tests/test_review.py::test_whoever_prepared_it_does_not_sign
  - text: 只有主持人能用自己的密码签字，而且必须先写好会议日期、出席人员、评价和结论。
    test: tests/test_review.py::test_review_from_inputs_to_signature
  - text: 会议日期在将来，或早于期间开始，会被拒绝。
    test: tests/test_review.py::test_review_from_inputs_to_signature
  - text: 收集输入后期间不能再改；在评审不知情的情况下被改动的输入不会被签字。
    test: tests/test_review.py::test_review_from_inputs_to_signature
  - text: 已签字的评审及其决定的措施不能修改或删除，即使在数据库里也不行。
    test: tests/test_review.py::test_review_from_inputs_to_signature
  - text: 措施只能由其负责人或质量人员标为完成，而且必须附上证明已完成的内容。
    test: tests/test_review.py::test_review_from_inputs_to_signature
questions:
  - q: 为什么某个数字显示“未知”？
    a: 这个期间没有可以统计它的记录，例如没有检验过任何批次。WenQuest Ops 绝不会为此显示 0。
  - q: 我收集了输入之后又有新记录进来了，怎么办？
    a: 在签字之前选择“重新统计”。新的指纹取代旧的，旧的保留在历史中。
  - q: 我还能用管理评审登记表吗？
    a: 可以。在 WenQuest Ops 之外召开的评审仍可以录入那里；在本页面签字的评审会自动出现在登记表中。
---

侧栏中的“管理评审”是最高管理者按计划的时间间隔评审质量体系的地方。用标题和所覆盖的期间发起一次评审，
然后选择“收集输入”。WenQuest Ops 从该期间的记录中统计这些输入：来料检验、不合格品、纠正措施、供应商、文件与阅读、
投诉、测量设备、变更、风险、生产、召回、交付绩效，以及以往评审中仍未完成的措施。无法统计的数字显示“未知”，而不是 0。
随后这些输入连同内容指纹一起冻结；之后产生的记录不会改变它们，除非有人重新统计，而旧的指纹保留在历史中。

开会时，写下日期、出席人员、会议对每项输入的评价，以及结论：体系是否适宜、充分和有效？添加会议决定的措施，
每项都有负责人和到期日期。这些都写好后，由主持人用密码签字。主持人不能是收集输入、或写下评价或措施的人。
签字后评审即固定，并进入 GB/T 19001-2016 / ISO 9001 检查所读取的管理评审登记表。负责人凭证明已完成的内容把各自的措施标为完成；
下一次评审会列出仍未完成的措施。“打印报告”可以把评审打印成纸质文件。
