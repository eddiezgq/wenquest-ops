# Ontology (ADR-0007)

One file per domain. Objects are built from ERPNext events (`wqops/hub/ont/project.py`) and the company manifest.
Changing the ontology means changing these files; the hub checks them at start and can rebuild every object from the
event log.

```yaml
domain: sales               # unique id
order: 2                    # position on the map
label: Sales & delivery
view: sales:view            # permission needed to see this domain (ADR-0005)
types:
  SalesOrder:               # type name, UpperCamelCase, unique across files
    label: Sales order
    maturity: have          # have = synced; erp = in ERPNext, not synced yet
    source: ERPNext Sales Order
    key: ERPNext sales order number
    title: "{key} {customer_name}"
    props:
      delivery_date: {t: date, l: Delivery date}
      grand_total: {t: num, l: Total, u: currency}
    links:
      customer: {to: Customer, l: Customer, inv: Sales orders}   # inv names the reverse direction
```

Property types `t`: str, num, int, bool, date, json. Units `u`: currency (the company currency), %, days.
