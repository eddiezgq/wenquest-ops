# Machine and system interface (ADR-0020, 20d)

WenQuest Ops answers calls from machines and other systems (an MES, a test bench, a gauge station, an ERP bridge). It
never makes calls of its own. Every call carries the access token the owner made under *Machines and systems*:

    Authorization: Bearer wqo_...

A token is allowed only what was ticked when it was made (`measurements:send`, `production:send`, `events:read`),
can be revoked at any time, and is stored only as a SHA-256 hash. Every call is logged with its status. Bodies are JSON,
at most 1 MB.

## Status codes

| Code | Meaning |
|------|---------|
| 200 / 202 | Done / received and waiting for a person |
| 400 | The request is not JSON, or a parameter is out of range |
| 401 | No token, a wrong one or a revoked one |
| 403 | The token may not do this |
| 413 | Larger than 1 MB |
| 422 | Checked and refused; `detail` says why (nothing is kept) |

## GET /api/integration/v1/whoami

`{"name": "Line 1 MES", "scopes": ["events:read"]}`

## POST /api/integration/v1/measurements (`measurements:send`)

```json
{"inspection": "IQC-00005",
 "readings": [{"sample": 1, "characteristic": "Board thickness", "value": 4.02}],
 "equipment": "CAL-01",
 "note": "optional"}
```

- The inspection must be in progress; samples are 1 to its sample size; characteristics are the measured ones of its
  plan, named exactly; each sample and characteristic once; at most 2000 readings.
- `equipment` is the code of registered measuring equipment; it must be in calibration when the reading is accepted.
- Answer 202: `{"id": 12, "status": "pending", ...}`. A person accepts it (signed) or rejects it with a reason under
  *From machines*. Accepted readings replace what was entered before for the same sample and characteristic.

## POST /api/integration/v1/production-steps (`production:send`)

```json
{"record": "DHR-00002", "step": 2, "value": 10.01, "equipment": "CAL-01"}
```

`value` for a measurement, `"result": "pass" | "fail"` for a check, `"text"` for a record step. Steps are recorded in
order, by the person who accepts them (their training is checked), and judged by WenQuest Ops against the template.

## GET /api/integration/v1/events?after=0&limit=100 (`events:read`)

```json
{"events": [{"id": 41, "kind": "production_lot.released", "ref_kind": "production_record", "ref_id": 3,
             "ref_name": "DHR-00003", "data": {"item_code": "HX-BOLT-M8", "lot_no": "KIT-2610-03", ...},
             "at": "2026-10-17T14:02:11+00:00"}],
 "next": 41, "more": false}
```

Kinds: `incoming_lot.released`, `incoming_lot.rejected`, `production_lot.released`, `production_lot.rejected`,
`ncr.opened`. Keep `next` and pass it as `after` on the next call; events never change and are never deleted.

An example client with the Python standard library is in `docs/examples/mes_client.py`.
