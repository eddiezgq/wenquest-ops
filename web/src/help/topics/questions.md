---
title: Questions
group: Help
order: 1
summary: Answers to common questions.
try:
  - id: freshness
    text: Sign in as **Dana** (Owner) and open the *Dashboard*. In a wide window, read the line next to the page title.
    to: /
    expect: the time ERPNext was last read. It moves on about every 5 minutes.
    tour:
      - target: '[data-help="dashboard-asof"]'
        text: When WenQuest Ops last read ERPNext.
  - id: fictional
    text: Look under the company name at the top of the sidebar, then open *Objects* and search for **Gulf**.
    to: /objects
    expect: '"Fictional demo" under Harbor Lane Supply (Demo), and the supplier Gulf Fasteners (Demo).'
  - id: runs-kept
    text: Open *Assistant*, ask **What is short?**, then reload the page.
    to: /assistant
    expect: the question and its answer are still there, with *How it found this*.
    tour:
      - target: '[data-help="assistant-ask"]'
        text: Every question and answer is kept with the steps the assistant took.
  - id: own-runs
    text: Sign in as **Alex** (Sales) and open *Assistant*.
    to: /assistant
    expect: only Alex's own questions, not Dana's.
blocks:
  - text: A number with no records behind it shows "unknown", never 0.
    test: tests/test_overview.py::test_overview_for_the_owner
  - text: The assistant cannot change ERPNext; what it prepares waits for a person to confirm.
    test: tests/test_drafts.py::test_ai_drafts_wait_for_a_person
  - text: You cannot open another person's questions to the assistant unless you are the owner or the AI specialist.
    test: tests/test_ai.py::test_ai_api
questions:
  - q: I typed my password wrong several times and cannot sign in.
    a: Five wrong passwords lock the account for 10 minutes. Wait, or ask the owner to set a new password, which also unlocks it.
  - q: Where do I find every step to test?
    a: On the *Help* page, choose *Test checklist*. It lists every "Try it" step of the topics you can see.
  - q: Why does the big screen show no amounts of money?
    a: Visitor mode is on. It shows shares, counts and curves only, and no names of customers or suppliers. The owner can turn it off.
---

**Why does a number say "unknown"?** The records needed to count it are missing, for example no deliveries in the
period. The system never shows 0 for missing data.

**How fresh is the data?** WenQuest Ops reads ERPNext every 5 minutes. The owner can start a sync at once.

**I changed something in ERPNext and don't see it.** Wait for the next sync, or ask the owner to sync now.

**Can the assistant change ERPNext?** No. It prepares drafts; a person confirms; purchase orders are then submitted
in ERPNext by a person.

**Why can't I edit a closed report?** Signed quality records are locked so they can be trusted in an audit. Cancel
with a reason or open a new report.

**Where are the AI's answers kept?** Every run is recorded with its steps. You see your own; the owner and the AI
specialist see all.

**Is this demo data real?** No. Harbor Lane Supply (Demo) and every customer, supplier and item in it are fictional.
