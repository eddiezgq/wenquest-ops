---
title: Risk management
group: Regulated modules
order: 4
summary: Risk criteria, risk files, hazards and residual risk.
video: risk
needs: quality:view
try:
  - id: criteria
    text: Open *Risk* and look at the company's risk criteria under the list of files.
    to: /quality/risk
    expect: the example 5 × 5 matrix with the note "Example - replace with your company's criteria".
    tour:
      - target: '[data-help="risk-criteria"]'
        text: Your own severity and probability levels and the matrix that decides acceptability. Every change is logged.
  - id: approved
    text: Open the approved file for **M8 bolt kit (KIT-M8)**. Read the hazards, their initial and residual verdicts and the fingerprint.
    to: /quality/risk
    expect: the status "approved", two hazards with acceptable residual risk, and Dana's signature.
    tour:
      - target: '[data-help="risk-files"]'
        text: The current version of each risk file. Choose Drafts, Approved or All versions above the list.
  - id: draft
    text: Sign in as **Jordan** (Quality) and open the draft for **Packaging (BOX-12)**.
    to: /quality/risk
    expect: '"To approve:" with the overall residual risk conclusion, and the risk controls and residual risk of item 1.'
    tour:
      - target: '[data-help="risk-hazards"]'
        text: Each hazard with the hazardous situation and the harm. The matrix gives the verdict; nobody types it.
        elsewhere: Open the Packaging (BOX-12) draft first.
  - id: control
    text: Choose *Edit* on the hazard **Box too thin**. Fill in the risk controls, how they were verified, a residual severity of **2** and a residual probability of **1**. Choose *Save the hazard*.
    expect: a residual verdict "Acceptable".
    tour:
      - target: '[data-help="risk-hazard-form"]'
        text: A risk that is not acceptable needs controls, how they were verified, and the residual severity and probability.
        elsewhere: Open the Packaging (BOX-12) draft first.
  - id: conclusion
    demo: /quality/risk/2
    text: Write the overall residual risk and choose *Save*.
    expect: nothing left under "To approve".
    tour:
      - target: '[data-help="risk-conclusion"]'
        text: The file's overall residual risk conclusion. It is needed before approval.
        elsewhere: Open the Packaging (BOX-12) draft first.
  - id: approve
    demo: /quality/risk/2
    text: Sign out, sign in as **Dana** (Owner), open the draft and approve it with your password.
    expect: '"Approved: the file is fixed now." and a fingerprint.'
    tour:
      - target: '[data-help="risk-approve"]'
        text: Someone who does not own and did not edit the file approves it. Acceptability is looked up again and kept.
        elsewhere: Open the draft as Dana first.
  - id: new-version
    text: On the approved **M8 bolt kit (KIT-M8)** file, choose *Start a new version*.
    expect: version 2 as a draft with the same hazards. Approving it supersedes version 1.
blocks:
  - text: Whoever owns a risk file or edited it cannot approve it.
    test: tests/test_risk.py::test_file_from_draft_to_superseded
  - text: A file is not approved while a risk that is not acceptable lacks controls, their verification or a residual risk the matrix decides, or while an unacceptable residual risk has no benefit-risk note.
    test: tests/test_risk.py::test_file_from_draft_to_superseded
  - text: A severity or probability that is not one of your levels is refused.
    test: tests/test_risk.py::test_file_from_draft_to_superseded
  - text: An approved file and its hazards cannot be changed, not even in the database; changes go into a new version.
    test: tests/test_risk.py::test_file_from_draft_to_superseded
  - text: A level keeps its kind and rank, and levels are never deleted.
    test: tests/test_risk.py::test_criteria_are_the_companys
  - text: A draft is withdrawn only with a reason, and a withdrawn draft takes no more hazards.
    test: tests/test_risk.py::test_withdraw_a_draft
questions:
  - q: Are the example severity and probability levels a standard?
    a: No. They are an example to start from and must be replaced with the criteria from your own risk management procedure.
  - q: What does "not determined" mean?
    a: The matrix has no verdict for that severity and probability. It stops approval until the matrix decides it.
  - q: If we change the criteria later, do approved files change?
    a: No. An approved file keeps the verdicts and criteria it was approved with, and its fingerprint.
---

**Risk** keeps a risk management file per product or product family. First set the company's criteria on the same
page: severity levels and probability levels (rank, name, description), and in the matrix which combinations are
*acceptable*, to be *reduced as far as possible*, or *unacceptable*. These are your own criteria from your risk
management procedure, not standard values; an example 5 × 5 can be loaded to start from and must be replaced. Every
change to the criteria is logged.

In a file, each hazard names the hazardous situation and the harm, with a severity and a probability; the matrix
decides acceptability (a combination the matrix does not decide is *not determined* and stops approval). A risk that
is not acceptable needs risk controls, how they were verified, and the residual severity and probability; an
unacceptable residual risk needs a benefit-risk note. The file needs an overall residual risk conclusion. Someone
who does not own and did not edit the file approves it with a password: acceptability is looked up once more, and the
verdicts, the criteria used and a fingerprint are kept. An approved file is fixed; *Start a new version* copies it
into a draft, and approving that draft supersedes the old version. A draft is withdrawn with a reason; nothing is
deleted.
