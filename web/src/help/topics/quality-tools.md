---
title: Quality tools
group: Quality
order: 7
summary: Pareto charts, histograms and scatter plots from your own records, and check sheets for counting defects.
needs: quality:view
try:
  - id: pareto
    text: 'Sign in as **Jordan** (Quality). Open *Quality tools*. On the *Pareto* tab, count **Check sheets** by **Category** with the form **Packing bench defects (Demo)**.'
    to: /quality/tools?tab=pareto
    expect: the categories from largest to smallest with the running total; Crushed box comes first and the first few make up 80% or more.
    tour:
      - target: '[data-help="pareto-pick"]'
        text: Count nonconformance reports, failed incoming readings, complaints or check sheet tallies, by item, supplier, customer, characteristic or category.
        elsewhere: Open the Pareto tab first.
      - target: '[data-help="pareto-chart"]'
        text: Click a bar to list the records behind it.
  - id: histogram
    text: On the *Histogram* tab, pick **BOX-12 · Board thickness (incoming)**.
    to: /quality/tools?tab=histogram
    expect: the distribution of every signed reading with the plan's limits and the mean, and beside it how many fell outside and the capability.
    tour:
      - target: '[data-help="hist-capability"]'
        text: Computed by code. Without both limits, capability says unknown.
        elsewhere: Open the Histogram tab and pick a characteristic first.
  - id: sheet
    text: On the *Check sheets* tab, count what you see at the bench with + and −, type your password and press *Record and sign*.
    to: /quality/tools?tab=sheets
    expect: a new tally named CS-… at the top of the list; the Pareto of the form includes it.
    tour:
      - target: '[data-help="sheets-record"]'
        text: Every category of the form gets a whole count; the tally is signed and cannot be changed afterwards.
        elsewhere: Open the Check sheets tab first.
blocks:
  - text: A record with no value for the chosen category is its own bar, “not recorded”, never left out.
    test: tests/test_quality_tools.py::test_pareto_from_records
  - text: A tally is signed with your password, counts only the form's categories in whole numbers, and is never changed or deleted; a retired form takes no new tallies.
    test: tests/test_quality_tools.py::test_check_sheets
  - text: A correlation needs at least three pairs that vary; otherwise it is unknown. It never says which value causes the other.
    test: tests/test_quality_tools.py::test_rules
questions:
  - q: Where does the data come from?
    a: From records already signed in WenQuest Ops - incoming inspections, nonconformance reports, complaints, production measurements and check sheets. Nothing is typed twice.
  - q: Can we count our own defect types on nonconformance reports?
    a: Yes. Add a choice field such as Defect type to the nonconformance workflow (Quality, Workflows); it appears as a Pareto category.
  - q: How do I change a check sheet's categories?
    a: Make a new form and retire the old one. A form is kept as it was made, so earlier tallies keep their meaning.
---

The *Quality tools* page answers three questions from records you already keep. **Where are most of our problems?**
A Pareto chart counts nonconformance reports, failed incoming readings, complaints or check sheet tallies by item,
supplier, customer, characteristic or category, largest first, with the running share; the first bars that reach
80% are the place to start. **How spread out is a dimension?** A histogram shows every signed reading of one
characteristic against its limits, next to the capability the control chart computes. **Do two dimensions move
together?** A scatter plot pairs two characteristics measured on the same piece and gives the correlation; it shows
that they move together, not why.

A check sheet is a form of your own categories for counting what people see, such as defects at a packing bench.
Each tally is signed and kept; its Pareto shows which category to work on first.
