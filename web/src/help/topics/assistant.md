---
title: Assistant
group: Daily work
order: 3
summary: Ask in plain English; answers cite your records.
video: assistant
try:
  - id: panel
    text: Open **NCR-00001** and choose *Ask AI* at the bottom right (or press Ctrl+J). Choose *Summarize this report*, then ask a follow-up question.
    demo: /quality/ncr/1
    expect: the panel slides out, knows you are looking at a nonconformance report, and answers with a link to it. The conversation stays open as you move between pages.
    tour:
      - target: '[data-help="chat-open"]'
        text: The assistant is on every page. It knows the page and the record you have open.
  - id: open
    text: Sign in as **Sam** (Operations manager) and open *Assistant*. Read the line under the title.
    to: /assistant
    expect: which engine answers, "Built-in rules" when no AI model key is set, and what the assistant may do.
    tour:
      - target: '[data-help="assistant-engine"]'
        text: Which engine answers. Without a model key, built-in rules answer common questions.
  - id: example
    text: Choose the example *Which orders are late, and why?*
    to: /assistant
    expect: the late sales orders, each a link, and on-time delivery over the last 30 days.
    tour:
      - target: '[data-help="assistant-examples"]'
        text: Ready-made questions. Choose one to ask it.
  - id: how
    text: Under the answer, open *How it found this*.
    expect: the steps the assistant took, each with what it found.
    tour:
      - target: '[data-help="assistant-steps"]'
        text: Every tool the assistant used for this answer, in order.
        elsewhere: Ask a question first.
  - id: named
    text: Ask **What is wrong with HX-BOLT-M8?**
    to: /assistant
    expect: the item, its open problems and their causes, with links.
    tour:
      - target: '[data-help="assistant-ask"]'
        text: Ask in plain English. Name an order, item, purchase order or supplier by its number to ask about it.
  - id: link
    text: Click **HX-BOLT-M8** in the answer.
    expect: the item's own page, with its details and open problems.
  - id: useful
    text: Go back to *Assistant* and choose *Yes* next to "Useful?" under an answer.
    to: /assistant
    expect: '"thanks" next to the buttons.'
    tour:
      - target: '[data-help="assistant-useful"]'
        text: Tell the assistant whether the answer helped. It is kept with the question.
        elsewhere: Ask a question first.
  - id: sales-role
    text: Sign in as **Alex** (Sales) and choose the example *How are our suppliers doing on time?*
    to: /assistant
    expect: an answer saying Alex's role cannot see supplier on-time figures.
blocks:
  - text: The panel shows only the records your role may see; asked about a quality record without quality access, it says so.
    test: tests/test_ai_chat.py::test_record_tool_and_rules
  - text: Someone else's conversation cannot be opened.
    test: tests/test_ai_chat.py::test_chat_api
  - text: The assistant reads only what your role may see, also when an AI model answers.
    test: tests/test_ai.py::test_model_cannot_read_past_the_role
  - text: A sentence with a number that is not in the data the assistant looked at is marked unverified.
    test: tests/test_ai.py::test_model_uses_tools_and_numbers_are_checked
  - text: The assistant cannot use a tool it was not given, such as one that changes the database.
    test: tests/test_ai.py::test_unknown_tool_and_bad_arguments
  - text: You cannot open someone else's questions; only the owner and the AI specialist see everyone's.
    test: tests/test_ai.py::test_ai_api
  - text: A draft the assistant prepares stays pending until a person confirms it.
    test: tests/test_ai_drafts.py::test_model_drafts_stay_pending
questions:
  - q: What can it answer without an AI model?
    a: Late orders, items short, on-time delivery, supplier on-time, inventory value, days of inventory, open anomalies, and what is wrong with an order, item, purchase order or supplier named by its number.
  - q: What happens if the AI model is not available?
    a: The built-in rules answer instead, and the answer is marked "rules (model unavailable)".
  - q: Can I see what the assistant did?
    a: Yes. Open *How it found this* under any answer. Every run is recorded with its steps.
---

Ask in plain English: *Which orders are late, and why?*, *What is short?*, *How is Gulf Fasteners doing?*,
*What is wrong with PO-0031?*

![The assistant answering from the records, with links](img/assistant.webp)

- The assistant reads only what your role can see, through the same tools the pages use. It cannot see the
  database or the internet.
- It cites what it used: click the order or item numbers in the answer.
- Every number must appear in the data it looked at. A sentence with a number it could not find is marked
  **unverified**.
- It can prepare drafts: a replenishment purchase order, a delay message to a customer, a nonconformance report.
  Drafts wait on the **Drafts** page for someone with the right role.
- Without an AI model key, built-in rules answer common questions. Whoever runs the system adds the company's own
  Anthropic key to use Claude.

Every question and answer is kept with the steps the assistant took. Tell it whether an answer was useful.
