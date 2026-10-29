---
title: 签字与工作流
group: Quality
order: 6
summary: 签字如何进行，以及公司如何收紧自己的工作流。
video: signatures-and-workflows
needs: quality:view
try:
  - id: password
    text: 以 **周静**（质量）登录，打开“我的账号”。
    to: /account
    expect: 一个修改密码的框。这就是您签字时使用的密码。
    tour:
      - target: '[data-help="account-password"]'
        text: 您用这个密码签署质量记录。用 Microsoft 或 Google 登录的人需要先在这里设置一个密码。
  - id: workflows
    text: 打开“质量”，选择“工作流”标签页。
    to: /quality?tab=workflows
    expect: 不合格品报告和纠正措施两个工作流，各自显示“版本 1 使用中”、按顺序排列的状态以及每个步骤。
    tour:
      - target: '[data-help="workflow-card"]'
        text: 每个步骤从哪个状态开始、到哪个状态结束，需要什么，是否签字，谁不能做、谁可以做。
        elsewhere: 请先选择“工作流”标签页。
  - id: draft
    demo: /quality?tab=workflows
    text: 在不合格品报告下，选择“修改此工作流”。
    expect: 一个草稿页面：“不合格品报告工作流 · 版本 2”。
    tour:
      - target: '[data-help="workflow-change"]'
        text: 把正在使用的版本复制成一份草稿。只有老板和质量部门能看到这个按钮。
        elsewhere: 请先选择“工作流”标签页。
  - id: edit
    text: 在“步骤”下，把步骤 **隔离** 改名为 **封存隔离**，并把关闭签字的含义改为 **质量部关闭 NCR**。选择“保存草稿”。
    expect: “已保存。由未修改过它的人启用。”两处修改都列在“相对版本 1 的修改”下，检查结果显示“保留了所有不可关闭的规则。”
    tour:
      - target: '[data-help="workflow-steps"]'
        text: 可以给步骤改名、写明签字的含义、增加步骤需要的内容、让更多人不能做某一步、把某一步限定给部分角色。
        elsewhere: 请先打开草稿。
      - target: '[data-help="workflow-changes"]'
        text: 相对正在使用的版本所做的每一处修改。
      - target: '[data-help="workflow-check"]'
        text: 不可关闭的规则，每次保存时都会检查。
  - id: not-own
    text: 看页面底部的“启用”框。
    expect: “此草稿由您修改，因此需由另一位有权修改工作流的人来启用。”
    tour:
      - target: '[data-help="workflow-enable"]'
        text: 修改草稿的人不能启用它。
        elsewhere: 请先打开草稿。
  - id: enable
    text: 退出登录，以 **王丹**（老板）登录。打开“质量”、“工作流”，选择“打开草稿（版本 2）”，输入您的密码，选择“启用（签字）”。
    to: /quality?tab=workflows
    expect: “已启用。新记录将按此版本执行。”以及签字“流程版本已启用”。
    tour:
      - target: '[data-help="workflow-open-draft"]'
        text: 打开由别人修改的草稿。
        elsewhere: 请先选择“工作流”标签页。
  - id: kept
    text: 回到“工作流”标签页。
    to: /quality?tab=workflows
    expect: “版本 2 使用中”，其中有步骤“封存隔离”。之前开立的报告（例如 NCR-00001）仍按版本 1 执行。
blocks:
  - text: 密码错误时，什么也不会签署，什么也不会改变。
    test: tests/test_quality.py::test_ncr_without_approval
  - text: 只用 Microsoft 或 Google 登录的人，在设置 WenQuest Ops 密码之前不能签字。
    test: tests/test_quality.py::test_sso_only_people_need_a_password_to_sign
  - text: 签字和质量历史不能修改或删除，在数据库里也不行。
    test: tests/test_quality.py::test_logs_and_signatures_cannot_be_changed
  - text: 任何工作流版本都不能去掉签字、由他人批准、WenQuest Ops 必需的步骤或状态，也不能去掉“严重报告须在其纠正措施关闭后才能关闭”这条规则。
    test: tests/test_workflow.py::test_red_lines_cannot_be_configured_away
  - text: 草稿只能由未修改过它的人用自己的密码启用，并且只有检查通过时才能启用。已启用的版本不能再修改。
    test: tests/test_workflow_admin.py::test_draft_change_and_signed_enabling
  - text: 来自程序文件的建议，只有在该程序文件中确实找到了所引用的原文时，才能被接受。
    test: tests/test_workflow_proposals.py::test_proposal_is_checked_kept_and_decided
questions:
  - q: 谁可以修改工作流？
    a: 老板和质量部门。由未修改过草稿的人来启用它。
  - q: 启用新版本后，尚未关闭的报告会怎样？
    a: 它们继续按开立时的版本执行，版本号显示在各自页面的顶部。新的报告和措施按新版本执行。
  - q: AI 能修改工作流吗？
    a: 不能。有了公司的模型密钥，AI 可以根据您生效的程序文件提出修改建议，每条建议都附有引文。由人逐条接受或拒绝，再由未修改过草稿的人启用。
---

签字就是重新输入**您自己的 WenQuest Ops 密码**。如果您用 Microsoft 或 Google 登录，请先在“我的账号”中设置一个密码。签字和质量历史永远不能修改或删除。

## 工作流

“质量”下的“工作流”标签页显示不合格品报告和纠正措施如何流转：按顺序排列的状态，以及每个步骤由谁做、需要什么、是否签字、谁不能做（例如，提交处置的人不能批准该处置）。这些规则是一份配置，WenQuest Ops 在每一步之前都会检查；每份报告和每项措施都按开立时的版本执行，版本号显示在各自页面的顶部。签字、由他人批准以及记录历史，任何配置都无法关闭。

**修改工作流。** 有权修改工作流的人（老板和质量部门）选择“修改此工作流”。新版本一开始是正在使用版本的一份草稿副本。您可以给状态和步骤改名，写明签字的含义，增加步骤需要的内容，让更多人不能做某一步，把某一步限定给部分角色，添加您自己的字段（例如批次号，要求在隔离之前填写），增加额外的签字审批（例如“老板批准关闭严重不合格报告”），以及收紧规则。页面会列出相对正在使用版本的每一处修改，并检查不可关闭的规则。由未修改过草稿的人用自己的密码启用；之前开立的报告和措施保持原来的版本。

**来自程序文件的建议。** 有了公司的模型密钥，同样这些人可以让 AI 阅读文件库中生效的程序文件（在文件库中已批准；与不合格品或纠正措施有关的会预先勾选），并对工作流提出修改建议，例如“QP-08 要求在处置之前填写批次号”。每条建议都引用程序文件原文。WenQuest Ops 会核实引文确实出自该程序文件，并确认修改保留了不可关闭的规则。建议只能收紧工作流：不能让更多角色去做某一步，也不能让某一步要求一项到那时还没人能填写的内容。未通过检查的建议，或工作流已经做到的建议，不能被接受。您逐条接受或拒绝。接受的建议进入草稿（没有草稿时会新建一份），然后和上面一样，由未修改过草稿的人用自己的密码启用。AI 从不自行修改工作流。程序文件中提出、但工作流无法做到的要求会单独列出，交由人来处理。

![建议的修改，每条都附有程序文件中的引文](img/workflow-suggestions.webp)
