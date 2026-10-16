---
title: Setting up the quality system
group: Quality system
order: 4
summary: Answer a few questions; the system suggests the settings.
video: quality-system-setup
needs: quality:view
try:
  - id: open
    text: Sign in as **Jordan** (Quality). On *Quality system*, keep **ISO 9001** chosen and choose *Set up*.
    to: /system/setup
    expect: '"Set up for ISO 9001" with three parts. If the standard is not adopted yet, the page says to adopt it first.'
    tour:
      - target: '[data-help="qms-setup"]'
        path: /system
        text: Fits the standard you are looking at to your company.
      - target: '[data-help="setup-questions"]'
        path: /system/setup
        text: A few questions about the company. Nothing changes until you declare it with your password.
  - id: answer
    text: 'Answer for the demo company: what it provides, **fasteners, electrical and packaging supplies, distributed**; designs its own products, **no**; holds property of customers or suppliers, **no**; uses measuring equipment, **yes**. Choose *Save the answers*.'
    to: /system/setup
    expect: under *What the answers say*, design and development and customer property marked "does not apply", measuring marked "applies", each with its reason.
  - id: declare
    text: Type your password and choose *Declare (sign)*.
    to: /system/setup
    expect: the points marked "(already declared)"; on *Quality system* they show "does not apply" or are judged.
    tour:
      - target: '[data-help="setup-declare"]'
        path: /system/setup
        text: What your answers say about each requirement. One signature declares them all.
        elsewhere: Save the answers first.
  - id: procedures
    text: Look at *From your own procedures*. With the company's model key, tick **QP-11** Calibration of Measuring Equipment and choose *Read 1 and suggest*; accept or reject each suggestion.
    to: /system/setup
    expect: the procedures in effect (QP-05 and QP-11 in the demo), or a note that this needs the company's model key. Each suggestion quotes the procedure.
    tour:
      - target: '[data-help="setup-procedures"]'
        path: /system/setup
        text: The AI suggests; WenQuest Ops checks each quote is in the procedure; you accept or reject each one.
  - id: write
    text: Under *Procedures written from the workflow*, choose *Write the nonconformance procedure*.
    to: /system/setup
    expect: a link to *Control of Nonconforming Product*, "from the" workflow, "to review".
    tour:
      - target: '[data-help="setup-written"]'
        path: /system/setup
        text: The procedure says what the workflow in use does. Write it again after the workflow changes.
  - id: review-it
    text: Open the new procedure and choose *Confirm*.
    expect: a draft; it takes effect only when someone else approves it (see *Controlled documents and reading*).
blocks:
  - text: An answer must fit its question; a yes/no question takes only yes or no, and a question the standard does not ask is refused.
    test: tests/test_setup.py::test_questionnaire
  - text: Declaring what the answers say needs your password; answers already declared are not declared again.
    test: tests/test_setup.py::test_questionnaire
  - text: A suggestion that fails the checks, such as leaving out a requirement that always applies or a number outside its range, cannot be accepted.
    test: tests/test_setup.py::test_changes_proposed_from_procedures
  - text: Accepting a suggestion that a requirement does not apply needs your password.
    test: tests/test_setup.py::test_changes_proposed_from_procedures
  - text: A written procedure is a draft until someone else approves it, even if it is confirmed as another type.
    test: tests/test_setup.py::test_procedures_written_from_the_workflow
  - text: People who may only look cannot answer the questions or write procedures.
    test: tests/test_setup.py::test_setup_api
questions:
  - q: Does the AI change settings by itself?
    a: No. Each suggestion waits for you to accept or reject it. Accepting makes the change as you would by hand.
  - q: The workflow changed. Is the written procedure still right?
    a: 'The page marks it "the workflow changed since: write it again". Write it again; the new one goes through approval.'
---

*Set up* (on the *Quality system* page) helps fit the standard to your company:

1. **About the company.** A few questions: what you make or provide, whether you design products, hold customers'
   property, do anything after delivery, use measuring equipment. The answers say which requirements may not apply;
   you declare them with your password in one go.
2. **From your own procedures.** With the company's model key, the AI reads the procedures you choose (those in effect)
   and suggests settings (for example how often gauges are calibrated), what does not apply and which procedure shows a
   requirement. Each suggestion quotes the procedure and WenQuest Ops checks the quote is there. You accept or reject
   each one; accepting makes the change as you would by hand, and a declaration still needs your password. Changes to
   how nonconformances and corrective actions flow are suggested on *Quality → Workflows*.
3. **Procedures written from the workflow.** WenQuest Ops writes the nonconformance and corrective action procedures
   from the workflows in use, so the procedure says exactly what the system does. They go into *Documents* to review
   and take effect once someone else approves them. When a workflow changes, the page says so: write it again.
