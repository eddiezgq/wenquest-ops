---
title: Dashboard
group: Daily work
order: 1
summary: The whole business at a glance, and the big screen for visitors.
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

**Waiting for people.** What waits for you: documents to read, drafts to confirm, lots to release, changes and risk
files to approve, and overdue quality actions in red.

**Daily brief.** Every morning at 7:30 (company time) the system writes a short brief; open it with *Daily brief*.

**Big screen.** *Big screen* shows the dashboard full screen for a TV in the office or on the shop floor: large type,
a new scene every 20 seconds (arrow keys to move, space to pause, F for full screen, Esc to leave). In visitor mode,
which is on unless the owner turns it off, it shows no amounts of money and no names of customers or suppliers:
only shares, counts and the shape of the curves.
