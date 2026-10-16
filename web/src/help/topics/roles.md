---
title: Roles
group: Start here
order: 2
summary: What each role sees and can do, your password, and people.
video: roles
try:
  - id: my-account
    text: Sign in as **Lee** (Warehouse) and open *My account* (your name at the bottom of the sidebar).
    to: /account
    expect: the role Warehouse, the department Operations and the list of what you may do.
    tour:
      - target: '[data-help="account-roles"]'
        text: Your roles and everything they allow. Roles come from the company manifest.
  - id: weak-password
    text: In *Change your password*, type your current password, then **short1** as the new password twice, and choose *Save password*.
    to: /account
    expect: '"password needs at least 10 characters". Your password stays as it was.'
    tour:
      - target: '[data-help="account-password"]'
        text: The password you sign in and sign quality records with. At least 10 characters, with letters and digits.
  - id: no-people
    text: Still as **Lee**, look for *People* in the sidebar, then open the People page directly.
    to: /people
    expect: no *People* item in the sidebar, and the page says your role does not allow seeing who has access.
  - id: ops-sees-people
    text: Sign in as **Sam** (Operations manager) and open *People*.
    to: /people
    expect: all seven demo people with their roles, whether a password is set and their last sign-in, but no column to set passwords.
    tour:
      - target: '[data-help="people-list"]'
        text: Who can sign in, with the roles the company manifest gives them. A locked account shows "locked".
  - id: owner-sets-password
    text: Sign in as **Dana** (Owner), open *People* and set a new password for **Riley** (AI specialist). Tell whoever else tests as Riley.
    to: /people
    expect: '"Password set for Riley AI. Tell them in person or by phone, not by email."'
    tour:
      - target: '[data-help="people-set-password"]'
        text: Only the owner sees this. Setting a password also unlocks the account and signs the person out everywhere.
  - id: riley-signs-in
    text: Sign out and sign in as **Riley** with the new password. Open *My account*.
    to: /account
    expect: the role AI specialist; the sidebar has *People* but the page has no column to set passwords.
blocks:
  - text: Five wrong passwords in a row lock the account for 10 minutes.
    test: tests/test_accounts.py::test_login_lockout_and_sessions
  - text: A password shorter than 10 characters, or without both letters and digits, is refused.
    test: tests/test_accounts.py::test_login_lockout_and_sessions
  - text: Only the owner sets other people's passwords; you change your own only with your current password.
    test: tests/test_hub.py::test_sign_in_flow
  - text: A new password signs the person out everywhere.
    test: tests/test_hub.py::test_sign_in_flow
  - text: A role cannot do what it is not given, for example Sales cannot draft purchase orders or edit quality records.
    test: tests/test_permissions.py::test_can_and_cannot
questions:
  - q: How do I add someone or change a role?
    a: Whoever runs the system changes the company manifest and runs the upgrade. The *People* page only shows the result.
  - q: My account is locked. What now?
    a: Wait 10 minutes and try again, or ask the owner to set a new password for you on the *People* page, which also unlocks it.
  - q: I sign in with Microsoft or Google. Do I need a password?
    a: Yes, for quality signatures. Set one on *My account*.
---

| Role | Sees | Can |
| --- | --- | --- |
| Owner | Everything | Everything, including settings and people |
| Operations manager | Dashboard, stock, sales, purchasing, quality | Draft purchase orders, edit quality records, see people |
| Warehouse | Dashboard, stock, purchasing, quality | Mark own corrective-action steps done |
| Purchasing | Dashboard, stock, purchasing, quality | Draft purchase orders |
| Sales | Dashboard, stock, sales | Prepare customer messages |
| Quality | Dashboard, stock, purchasing, quality | Edit and sign quality records, change workflows, adopt standards |
| AI specialist | Dashboard, stock, sales, purchasing, quality | Configure the assistant, see all assistant runs |

Everyone can use the assistant, with their own role's view, and read the document library. The owner, the
operations manager, Quality and the AI specialist can also upload documents, confirm their classification and approve
them. The owner and Quality change quality workflows and adopt standards on the *Quality system* page; everyone who
sees quality records sees that page. Roles come from the company manifest; ask the owner to
change yours.

**Your password.** Click your name at the top right (*My account*) to see what your role allows and to change your
password. If you sign in with Microsoft or Google, set a password there too: quality signatures use it.

**People.** The owner, the operations manager and the AI specialist see who can sign in, when they last did, and
whether an account is locked. The owner sets passwords for others on the *People* page (this also unlocks the
account). Adding people or changing roles is done in the company manifest by whoever runs the system.
