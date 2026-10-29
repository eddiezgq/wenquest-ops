---
title: 受控文件与阅读
group: Documents
order: 2
summary: 批准、生效、阅读确认和定期评审。
video: document-control
try:
  - id: confirm-reading
    text: 以 **李强**（仓库）登录，在侧栏中打开“我的阅读”。在 **QP-05** 来料检验旁边输入您的密码，选择“我已阅读并理解”。
    to: /documents/control
    expect: QP-05 的状态从“待处理”变为“已确认阅读”。
    tour:
      - target: '[data-help="reading-mine"]'
        path: /documents/control
        text: 要求您阅读的文件及其到期日。打开文件读完后，用您自己的密码确认。
  - id: everyone
    text: 以 **周静**（质量）登录，打开“我的阅读”，选择“全员阅读”标签页。
    to: /documents/control
    expect: 周静和李强的 QP-05，都已确认阅读。
    tour:
      - target: '[data-help="reading-tabs"]'
        path: /documents/control
        text: 我的阅读、到期复审、全员阅读和设置。后三个供管理文件的人使用。
      - target: '[data-help="reading-everyone"]'
        text: 谁被要求阅读什么，以及到期日和状态。
        elsewhere: 请先选择“全员阅读”标签页。
  - id: readers
    text: 从“文件”中打开 **QP-08** 不合格品控制程序版本 C（在“待审核”标签页中；如果它还在等待审核，先选择“确认”）。在“谁必须阅读”下勾选 **仓库**，勾选“此版本需要阅读”，然后选择“保存”。
    to: /documents?tab=review
    expect: 显示“已保存。”，角色下方显示现在涉及多少人：仓库角色只有李强一人。
    tour:
      - target: '[data-help="doc-readers"]'
        text: 必须阅读此版本的角色和人员。请在批准前设置；这份名单会沿用到以后的版本。
        elsewhere: 请打开 QP-08 版本 C 并确认，使它成为草稿。
  - id: send
    text: 选择“送审”。
    expect: 状态变为“待批准”，并提示由其他人批准。
    tour:
      - target: '[data-help="doc-send"]'
        text: 请先保存所有修改。上传、确认或送审这份文件的人不能批准它。
        elsewhere: 请在 QP-08 处于草稿状态时打开它。
  - id: approve
    text: 以 **孙明**（运营经理）登录，打开 QP-08，“生效日期”留空，输入您的密码，选择“批准（签字）”。
    expect: 显示“已批准，文件已生效。”。文件已冻结，阅读表中列出李强，到期日在之后。
    tour:
      - target: '[data-help="doc-approve"]'
        text: 选一个以后的日期可以留出阅读时间；在那之前，现行版本继续有效。留空即为今天生效。
        elsewhere: 请在 QP-08 等待批准时打开它。
      - target: '[data-help="doc-reading"]'
        text: 此版本的阅读情况，每人一行，附到期日。
        elsewhere: 请在 QP-08 生效后打开它。
      - target: '[data-help="doc-revise"]'
        text: 文件生效后，在这里上传下一个版本，或写明原因将其作废。
        elsewhere: 请在 QP-08 生效后打开它。
  - id: lee-reads
    text: 以 **李强** 登录，在“我的阅读”下确认 QP-08。
    to: /documents/control
    expect: QP-08 已确认阅读，与 QP-05 并列。
  - id: periodic
    text: 以 **周静** 登录。打开“我的阅读”，然后打开“到期复审”，打开 **QP-11** 测量设备校准。
    to: /documents/control
    expect: 在“定期评审”下，有一条由周静做出、王丹批准的“无需更改”评审，下次评审在其后 36 个月到期。
    tour:
      - target: '[data-help="reading-reviews"]'
        text: 类型需要定期评审的现行文件，按下次评审到期日排列。请先选择“到期复审”标签页。
        elsewhere: 请在“我的阅读”中选择“到期复审”标签页。
      - target: '[data-help="doc-periodic-review"]'
        text: 在这里记录一次评审（无需更改、需要更改或推迟）；由评审人以外的人用密码批准。
        elsewhere: 请从“到期复审”中打开 QP-11。
      - target: '[data-help="reading-settings"]'
        path: /documents/control
        text: 每类文件多久评审一次，以及给大家多少天阅读。请选择“设置”标签页。
        elsewhere: 请在“我的阅读”中选择“设置”标签页。
blocks:
  - text: 文件只能由没有上传、确认或送审它的人用密码批准。
    test: tests/test_documents.py::test_controlled_document_approval_and_revision
  - text: 同一编号只有一个版本生效；旧版本不能与它并列获批。
    test: tests/test_documents.py::test_one_effective_revision_per_number
  - text: 版本的生效日期不能早于批准日期。
    test: tests/test_doc_control.py::test_planned_effect_and_reading
  - text: 只有本人能用自己的密码确认自己的阅读。豁免阅读需要写明原因，并由他人操作。
    test: tests/test_doc_control.py::test_planned_effect_and_reading
  - text: 定期评审由评审人以外的人批准；“需要更改”必须写明新版本，“推迟”必须写明原因。
    test: tests/test_doc_control.py::test_periodic_review
  - text: 作废文件需要写明原因。
    test: tests/test_documents.py::test_controlled_document_approval_and_revision
questions:
  - q: 为什么王丹不能批准演示程序文件？
    a: 演示文件夹是王丹上传的，而上传、确认或送审文件的人不能批准它。孙明可以。
  - q: 什么时候会有人在“我的阅读”下看到一份文件？
    a: 当这个版本生效、它勾选了“此版本需要阅读”并且名单中有此人时。到期天数按“设置”中为该类文件设定的天数计算。
  - q: 新版本生效时，旧版本还没完成的阅读怎么办？
    a: 不再要求阅读。新版本会再次要求同样这些人阅读。
---

- **记录、证书和外来文件**一经确认就保留。它们的文件被冻结：永远不能替换。
- **程序文件、作业指导书和表单**成为草稿。选择“送审”；然后由没有上传、确认或送审它的人用密码批准。
  文件随即**生效**，文件被冻结。
- **新版本**：在已生效的文件上上传下一个版本。新版本同样要经过批准；批准后，旧版本自动作废（仍可查阅）。
- “作废”需要写明原因。历史和签字不能修改或删除。

## 生效、阅读与评审

- **计划生效日。** 批准人可以设定版本的生效日期，给大家留出阅读时间。在那之前，它的状态是“已批准，尚未生效”，
  被替换的版本继续有效；到了那一天，新版本自动生效，旧版本作废。
- **谁必须阅读。** 在程序文件、作业指导书或表单上，选择必须阅读的角色和人员，并在生效前勾选“此版本需要阅读”
  （这份名单会沿用到以后的版本）。生效时，他们每个人都会在侧栏的**我的阅读**（“阅读与评审”页面）中看到这份文件，
  在规定天数内用自己的密码确认已阅读并理解。任何人都不能替别人确认。质量人员可以写明原因豁免某人的阅读（不能豁免自己的）。
  较新的版本生效后，旧版本尚未完成的阅读不再要求。逾期未读会显示在 GB/T 19001-2016 / ISO 9001 的培训检查中。
- **定期评审。** 每类文件可以设定每隔多少个月评审一次（程序文件、作业指导书和表单默认 36 个月；在“我的阅读 → 设置”中修改）。
  下次评审在文件生效或上次评审获批之后的这段时间到期。在文件页面上记录一次评审：无需更改、需要更改（写明由此开始的新版本），
  或推迟（写明原因和新日期）。由评审人以外的人用密码批准；只有批准后，下次到期日才会更新。
  “我的阅读 → 到期复审”列出已到期和逾期的文件。
