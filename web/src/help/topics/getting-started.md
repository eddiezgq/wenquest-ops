---
title: Getting started
group: Start here
order: 1
summary: What WenQuest Ops does next to ERPNext, and the three rules it keeps.
video: getting-started
try:
  - id: sign-in
    text: Sign in as **Dana** (Owner) with dana@demo.example and the password you were given.
    to: /
    expect: the dashboard of Harbor Lane Supply (Demo). On the first visit in this browser the guided tour starts by itself.
  - id: guided-tour
    text: Follow the guided tour to the end, or choose *Skip the tour*. To see it again, choose *Take the guided tour* on the *Help* page or in the menu under the company name at the top of the sidebar.
    expect: a few steps across the dashboard, the assistant, drafts, quality, documents, objects and help.
  - id: sidebar
    text: Look at the sidebar. *Dashboard*, *Assistant*, *Anomalies* and *Drafts* come first, then the records from *Quality* to *Objects*, then *People* and *Help*.
    expect: Dana, as the owner, sees every item. Under the company name it says "Fictional demo".
  - id: dashboard
    text: On the *Dashboard*, find the chain *From purchase order to payment* and the row of lights under it.
    to: /
    expect: a step of the chain in red where something is stuck, and one light for each part of the business.
    tour:
      - target: '[data-help="dashboard-chain"]'
        text: The business from purchase order to payment. A red step has something stuck. Click a step to open it.
      - target: '[data-help="dashboard-lights"]'
        text: One light for each part of the business. Hover the number to see how it is judged.
  - id: needs-attention
    text: Scroll down to *Needs attention* and open the first problem.
    to: /
    expect: the anomaly page, with a suggested action, its causes and what it affects.
    tour:
      - target: '[data-help="dashboard-attention"]'
        text: Problems the rules found, most serious first. Open one to see why it happened.
  - id: other-role
    text: Sign out and sign in as **Alex** (Sales). Compare the sidebar and the dashboard.
    to: /
    expect: no quality records and no *People* in the sidebar; only the Sales, Delivery and Inventory lights.
  - id: checklist
    text: Open *Help* and choose *Test checklist*.
    to: /help/checklist
    expect: every "Try it" step of the topics you can see, on one page, with the ones you have ticked.
blocks:
  - text: Without signing in, no page or figure opens; you are sent to the sign-in page.
    test: tests/test_hub.py::test_sign_in_flow
  - text: A figure with no records behind it shows "unknown", never 0 and never green.
    test: tests/test_overview.py::test_overview_for_the_owner
  - text: Each role sees only its part. Sales does not see purchasing, quality or finance figures.
    test: tests/test_overview.py::test_what_each_role_sees
  - text: A draft prepared by the assistant writes nothing to ERPNext until a person confirms it.
    test: tests/test_drafts.py::test_ai_drafts_wait_for_a_person
questions:
  - q: How do I see the guided tour again?
    a: Choose *Take the guided tour* on the *Help* page, or in the menu under the company name at the top of the sidebar.
  - q: Where is ERPNext?
    a: "*ERPNext* at the bottom of the sidebar's list opens it in a new tab, when WenQuest Ops knows its address."
  - q: A colleague mentions a page I cannot find. Why?
    a: Your role decides which pages and figures you see. Ask the owner if you need more.
---

WenQuest Ops sits next to ERPNext. ERPNext keeps your orders, stock, purchasing and accounts; WenQuest Ops reads
them every few minutes, connects them into one picture of the business, and shows what needs attention.

**What you can do here**

- **Dashboard**: the chain from purchase order to payment, a light for each part of the business, weekly curves,
  what waits for you, a daily brief, and the problems found today. Each role sees the parts it may.
- **Assistant**: ask questions in plain English; it answers from your data and prepares drafts.
- **Anomalies**: problems found by rules, each with its causes and what it affects.
- **Drafts**: purchase orders, messages and reports prepared for you; nothing happens until someone confirms.
- **Records**: *Quality* (nonconformance reports, 8D, corrective actions, control charts), *Complaints*,
  *Incoming inspection*, *Approved suppliers*, *Measuring equipment*, *Changes*, *Risk*, *Production*,
  *Trace and recalls*, *Management reviews* and *Quality system*, each with its own item in the sidebar for those
  who see quality records.
- **Documents** and **My reading**: the document library, and the documents waiting for you to read.
- **Objects**: browse and search everything: orders, items, suppliers, receipts, inspections.

**Three rules the system keeps**

1. Numbers come from your records and say how they are counted. Missing data shows as *unknown*, never as 0.
2. The assistant only prepares drafts. Writing to ERPNext or sending anything needs a person to confirm.
3. Quality decisions are signed with your password and cannot be changed afterwards. They can only be cancelled with a reason.

**Your role decides what you see.** A sales person sees orders and stock, not supplier details; Quality sees
inspections and suppliers. Ask the owner if you need more.

**Take the tour.** The [guided tour](#tour) walks you through the pages for your role in two minutes.
