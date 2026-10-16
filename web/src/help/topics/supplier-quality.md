---
title: Supplier quality and control charts
group: Quality
order: 5
summary: Supplier scores and control charts of your measurements.
needs: quality:view
---

Facts per supplier: lots inspected and rejected, rejection rate, on-time rate, NCRs, concessions and open
corrective actions. No made-up score.

## Control charts (SPC)

![Control chart of a drifting parameter](img/quality-spc.webp)

Numeric readings on ERPNext inspections become control charts per item and parameter: X-bar and R when every
inspection has the same number of readings (2–10), otherwise individuals. Points that break a Western Electric rule
are marked. With spec limits you also get Cp, Cpk, Pp and Ppk.
