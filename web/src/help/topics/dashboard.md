---
title: Dashboard
group: Daily work
order: 1
summary: The whole business at a glance, and the big screen for visitors.
video: dashboard
try:
  - id: as-of
    text: Sign in as **Dana** (Owner) and open the *Dashboard*. In a wide window, read the line next to the page title.
    to: /
    expect: '"As of" a date, and the time ERPNext was last read.'
    tour:
      - target: '[data-help="dashboard-asof"]'
        text: The day the figures are counted for and the last time WenQuest Ops read ERPNext.
  - id: chain
    text: In *From purchase order to payment*, click a step shown in red.
    to: /
    expect: the page with what is stuck there, for example purchase orders past their required-by date.
    tour:
      - target: '[data-help="dashboard-chain"]'
        text: Each step shows what is there now. Red means something is stuck. Complaints and recalls are shown above the end.
  - id: lights
    text: Go back to the dashboard. Hover the number on the *Purchasing* light, then click the light.
    to: /
    expect: the number it is judged on and its green and amber targets; then the page scrolls to the Purchasing panel.
    tour:
      - target: '[data-help="dashboard-lights"]'
        text: Green is on target, amber is to watch, red is to act on, grey is not enough data.
      - target: '[data-help="dashboard-panels"]'
        text: One panel for each part of the business, with its figures, curves and the records behind them.
  - id: waiting
    text: Find *Waiting for people* and click *Overdue quality actions*.
    to: /
    expect: '"Overdue quality actions" in red, because a step of the demo corrective action is past its date. The click opens *Quality*.'
    tour:
      - target: '[data-help="dashboard-waiting"]'
        text: What waits for you. Red items are overdue.
  - id: brief
    text: Choose *Daily brief*.
    to: /
    expect: the latest brief, with its date, written from the records.
    tour:
      - target: '[data-help="dashboard-brief"]'
        text: Written every morning at 7:30, company time. Each role sees its own part.
        elsewhere: The daily brief appears here once WenQuest Ops has written today's brief.
  - id: big-screen
    text: Choose *Big screen*. Press the right arrow, then space to pause, then Esc to leave.
    to: /
    expect: large type, a new scene each time, no amounts of money and no customer or supplier names.
    tour:
      - target: '[data-help="dashboard-wall"]'
        text: The dashboard for a TV in the office or on the shop floor.
  - id: targets
    text: At the bottom, open *Targets and big screen*.
    to: /
    expect: a green and an amber value for each light, and the visitor mode switch.
    tour:
      - target: '[data-help="dashboard-targets"]'
        text: Only the owner sees this. The values are starting points until you save your own.
  - id: sales-view
    text: Sign out and sign in as **Alex** (Sales). Open the *Dashboard*.
    to: /
    expect: only the Sales, Delivery and Inventory lights, no Finance panel and no *Targets and big screen*.
blocks:
  - text: Each role sees only its own lights and panels; finance is shown only to the owner by default.
    test: tests/test_overview.py::test_what_each_role_sees
  - text: A light with no data behind it is grey, never green.
    test: tests/test_overview.py::test_overview_for_the_owner
  - text: Only the owner changes the targets and visitor mode.
    test: tests/test_overview.py::test_overview_api
  - text: A target that is not a number is refused.
    test: tests/test_overview.py::test_review_fixes
  - text: In visitor mode the big screen shows no amounts of money, only shares, counts and the shape of the curves.
    test: tests/test_overview.py::test_wall_and_settings
questions:
  - q: Why is a light grey?
    a: There is not enough data to judge it, for example fewer than 8 weeks of orders for Sales, or no lots released for Production.
  - q: How fresh are the numbers?
    a: WenQuest Ops reads ERPNext every 5 minutes. The dashboard checks for new figures every minute and lights up the ones that changed.
  - q: Who sets the targets?
    a: The owner, in *Targets and big screen* at the bottom of the dashboard. Only values that differ from the starting points are kept.
---

The dashboard shows the whole business at once. Everything on it is counted by WenQuest Ops from ERPNext and its own
records; nothing is estimated, and a number with no data behind it says "unknown". It refreshes itself after each
ERPNext sync (every 5 minutes); numbers that changed light up for a moment.

![The dashboard of the demo company](img/dashboard.webp)

**From purchase order to payment.** The chain of the business: purchase orders, receiving, incoming inspection,
stock, production, release, delivery, invoicing and payment. Each step shows what is there now; a red step has
something stuck (a purchase order past its required-by date, a lot waiting too long, an order late, an invoice past
due). Click a step to open it. Complaints and recalls coming back from customers are shown above the end of the chain.

**The lights.** One for each part of the business. The colour comes from one number and your company's targets:

| Light | The number |
| --- | --- |
| Sales | Orders this week against the average of the weeks before |
| Delivery | Sales orders delivered on time in the last 30 days |
| Inventory | Items short for open orders |
| Purchasing | Purchase order lines received on time in the last 30 days |
| Production | Lots released in the last 30 days without a failed step |
| Quality | Overdue quality actions: CAPA steps, complaint report deadlines, calibrations |
| Finance | The share of receivables past their due date |

Green is on target, amber is to watch, red is to act on, grey means there is not enough data. The targets are starting
points: the owner sets the company's own. Hover a light to see its target.

**The panels.** Each part of the business has a panel with its key figures, a curve over 8, 13 or 26 weeks, and the
orders, items or customers behind it. Finance (invoices, receivables, payables) is shown only to people allowed to see
it (the owner by default).

**Waiting for people.** What waits for you: documents to read, drafts to confirm, incoming and production lots to
release, changes, risk files and calibrations to approve, and overdue quality actions in red.

**Daily brief.** Every morning at 7:30 (company time) the system writes a short brief; open it with *Daily brief*.

**Big screen.** *Big screen* shows the dashboard full screen for a TV in the office or on the shop floor: large type,
a new scene every 20 seconds (arrow keys to move, space to pause, F for full screen, Esc to leave). In visitor mode,
which is on unless the owner turns it off, it shows no amounts of money and no names of customers or suppliers:
only shares, counts and the shape of the curves.
