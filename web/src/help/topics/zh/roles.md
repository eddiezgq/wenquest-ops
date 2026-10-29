---
title: 角色
group: Start here
order: 2
summary: 每个角色能看到什么、能做什么，您的密码，以及人员。
video: roles
try:
  - id: my-account
    text: 以 **李强**（仓库）身份登录，打开 *我的账号*（侧边栏底部您的名字）。
    to: /account
    expect: 角色“仓库”、部门 operations（运营部），以及您可以做的事情列表。
    tour:
      - target: '[data-help="account-roles"]'
        text: 您的角色及其允许的全部操作。角色来自公司清单。
  - id: weak-password
    text: 在 *修改密码* 中输入当前密码，再把 **short1** 作为新密码输入两次，然后选择 *保存密码*。
    to: /account
    expect: “密码至少需要 10 个字符”。您的密码保持不变。
    tour:
      - target: '[data-help="account-password"]'
        text: 您登录和签署质量记录所用的密码。至少 10 个字符，须同时包含字母和数字。
  - id: no-people
    text: 仍以 **李强** 身份，在侧边栏中找 *人员*，然后直接打开人员页面。
    to: /people
    expect: 侧边栏中没有 *人员*；页面提示“您的角色无权：查看谁有访问权限”。
  - id: ops-sees-people
    text: 以 **孙明**（运营经理）身份登录，打开 *人员*。
    to: /people
    expect: 全部七位演示人员，以及他们的角色、是否已设密码和上次登录时间，但没有设置密码的那一列。
    tour:
      - target: '[data-help="people-list"]'
        text: 谁可以登录，以及公司清单给他们的角色。被锁定的账号显示“已锁定”。
  - id: owner-sets-password
    text: 以 **王丹**（老板）身份登录，打开 *人员*，为 **林智**（AI 专员）设置新密码。告诉之后以林智身份测试的人。
    to: /people
    expect: “已为 林智 设置密码。请当面或电话告知，不要用电子邮件。”
    tour:
      - target: '[data-help="people-set-password"]'
        text: 只有老板能看到这一列。设置密码的同时会解锁账号，并让此人在所有地方退出登录。
  - id: riley-signs-in
    text: 退出登录，用新密码以 **林智** 身份登录。打开 *我的账号*。
    to: /account
    expect: 角色“AI 专员”；侧边栏有 *人员*，但页面上没有设置密码的那一列。
blocks:
  - text: 连续输错 5 次密码，账号会被锁定 10 分钟。
    test: tests/test_accounts.py::test_login_lockout_and_sessions
  - text: 少于 10 个字符、或没有同时包含字母和数字的密码会被拒绝。
    test: tests/test_accounts.py::test_login_lockout_and_sessions
  - text: 只有老板能设置他人的密码；修改自己的密码须输入当前密码。
    test: tests/test_hub.py::test_sign_in_flow
  - text: 设置新密码后，此人在所有地方都会退出登录。
    test: tests/test_hub.py::test_sign_in_flow
  - text: 角色不能做未授予它的事，例如销售不能起草采购订单，也不能编辑质量记录。
    test: tests/test_permissions.py::test_can_and_cannot
questions:
  - q: 怎样添加人员或更改角色？
    a: 由负责运维系统的人修改公司清单并运行升级。*人员* 页面只显示结果。
  - q: 我的账号被锁定了，怎么办？
    a: 等 10 分钟再试，或请老板在 *人员* 页面为您设置新密码，这样也会解锁账号。
  - q: 我用 Microsoft 或 Google 登录，还需要密码吗？
    a: 需要，质量签字要用它。请在 *我的账号* 中设置。
---

| 角色 | 能看到 | 能做 |
| --- | --- | --- |
| 老板 | 全部 | 全部，包括设置和人员 |
| 运营经理 | 看板、库存、销售、采购、质量 | 起草采购订单、编辑质量记录、查看人员 |
| 仓库 | 看板、库存、采购、质量 | 把自己负责的纠正措施步骤标记为完成 |
| 采购 | 看板、库存、采购、质量 | 起草采购订单 |
| 销售 | 看板、库存、销售 | 准备给客户的消息 |
| 质量 | 看板、库存、采购、质量 | 编辑并签署质量记录、更改工作流、采用标准 |
| AI 专员 | 看板、库存、销售、采购、质量 | 配置助手、查看所有助手运行记录 |

每个人都可以使用助手（只能看到自己角色范围内的数据），也都能阅读文件库。老板、运营经理、质量和 AI 专员还可以
上传文件、确认文件分类并批准文件。老板和质量可以在 *质量体系* 页面更改质量工作流、采用标准；能看到质量记录的
人都能看到这个页面。角色来自公司清单；如需更改您的角色，请找老板。

**您的密码。** 点击右上角您的名字（*我的账号*），可以查看您的角色允许做什么，并修改密码。如果您用 Microsoft 或
Google 登录，也请在那里设置一个密码：质量签字要用它。

**人员。** 老板、运营经理和 AI 专员可以看到谁能登录、上次何时登录、账号是否被锁定。老板在 *人员* 页面为他人
设置密码（同时会解锁账号）。添加人员或更改角色，由负责运维系统的人在公司清单中完成。
