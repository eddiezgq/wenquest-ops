---
title: Machines and an MES
group: Quality
order: 5
summary: Let an MES, a test bench or a gauge station send measurements and step results, and read events.
needs: quality:view
try:
  - id: token
    text: 'Sign in as **Dana** (Owner). Open *Machines and systems*, name it **Test bench**, tick *Send measurements* and make a token.'
    to: /integrations
    expect: the token shown once, starting with wqo_, and the bench in the list with no calls yet.
    tour:
      - target: '[data-help="token-new"]'
        text: One token per machine or system, allowed only what you tick.
        elsewhere: Only the owner manages tokens.
      - target: '[data-help="token-list"]'
        text: Every token with its last call. Revoke one and the machine is shut out at once.
  - id: send
    text: 'From the bench (or a terminal), send a reading for an inspection in progress, as in the example below.'
    expect: '"status": "pending". Nothing is in the inspection yet.'
  - id: accept
    text: Sign in as **Jordan** (Quality), open *From machines*, open the reading and accept it with your password.
    to: /quality/inbox
    expect: the reading in the inspection with a machine mark, entered by Jordan; the history says which machine sent it.
    tour:
      - target: '[data-help="inbox-list"]'
        text: What machines sent, waiting for a person. Open one to see it, and the readings it would replace.
blocks:
  - text: Only a hash of a token is kept; a revoked token, or one used for something it may not do, is refused, and every call is logged.
    test: tests/test_integration_api.py::test_machine_interface
  - text: What a machine sends is checked when it arrives and written only when a person accepts it with their password; a rejection needs a reason.
    test: tests/test_integration_api.py::test_measurements_wait_for_a_person
  - text: Production steps sent by a machine are recorded in order, as the person who accepts them, with the training check.
    test: tests/test_integration_api.py::test_production_steps_and_events
  - text: Events are written by the database when lots are decided and reports opened, and cannot be changed.
    test: tests/test_integration_api.py::test_production_steps_and_events
questions:
  - q: Why does a person have to accept what a machine sends?
    a: A record is signed by the person responsible for it. The machine's data is kept as it came, and the record says who accepted it and from which machine.
  - q: Does WenQuest Ops send data to our MES?
    a: No call goes out. The MES reads events (lots released or rejected, reports opened) from where it stopped last time, as often as it likes.
  - q: Where is the full description of the calls?
    a: docs/integration-api.md in the WenQuest Ops source, with an example client in docs/examples/mes_client.py.
---

An MES, a test bench, a gauge station or another system talks to WenQuest Ops with its own access token. It may send
measurements for an incoming inspection in progress, send the result of a production step, and read events, as you
allow. Example (a reading for sample 1):

```
curl -X POST https://<your address>/api/integration/v1/measurements \
  -H "Authorization: Bearer wqo_..." -H "content-type: application/json" \
  -d '{"inspection": "IQC-00005", "readings": [{"sample": 1, "characteristic": "Board thickness", "value": 4.02}], "equipment": "CAL-01"}'
```

What it sends waits under *From machines*. Accepting it writes it into the record, signed by you; the machine is named
in the history. Events come from `GET /api/integration/v1/events?after=<the last id you saw>`.
