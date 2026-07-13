# Big Real-World JSON Transform Samples

Full-size `input → transform → output` triples using the kind of nested API
payloads you actually mediate in production — not one-liners. Each input is a
realistic, complete payload (multiple items, nested arrays, the incidental
fields real APIs include). IDs and values are representative, but the
*structure* mirrors the real APIs.

> **Provenance.** Payloads are constructed to match the documented schemas of
> each real API (AWS EC2, Stripe, GitHub). The **Where to get the raw payloads**
> section at the bottom links the authoritative sources and shows how to capture
> your own live samples.
>
> **Reconciliation with AD-023 (added 2026-07-13).** This doc is the original
> brainstorm; the **normative** policy is AD-023 / FR-033 / §11.8 in
> `docs/SPEC.md`. Two consequences for anything committed from it:
> (1) The pinned `transon==0.1.7` is a **structural** transformer — four
> operations sketched below are **not engine-expressible** and ship as
> `expect: "refuse"` fixtures, never matched: epoch → ISO date, currency
> uppercasing, `refs/heads/` prefix stripping, and separator-aware (bulleted)
> joining. The matched fixtures simply drop those fields.
> (2) Expected outputs are **engine-frozen** — produced by re-executing an
> author-written seed template through the pinned engine (seed in `evals/seeds/`,
> re-checked by `check_evals --lint`), **never hand-written**. Live-captured API
> payloads are **out of scope for v1 and must not be committed** (the FR-018 /
> NFR-011 real-use path needs redaction + recorded consent first).

Contents:
1. AWS EC2 `describe-instances` → flat instance inventory
2. Stripe `checkout.session.completed` webhook → internal order record
3. GitHub `push` webhook → internal deploy event + Slack message

---

## 1. AWS EC2 `describe-instances` → flat instance inventory

Classic "wall of JSON" mediation: the API nests instances two levels deep
(`Reservations[].Instances[]`), tags are an array of `{Key,Value}` you have to
pivot, and you want a flat, downstream-friendly inventory row per instance.

### Input (real-shape `describe-instances` response)

```json
{
  "Reservations": [
    {
      "ReservationId": "r-0a1b2c3d4e5f60718",
      "OwnerId": "123456789012",
      "Groups": [],
      "Instances": [
        {
          "InstanceId": "i-0abcd1234efgh5678",
          "ImageId": "ami-0c55b159cbfafe1f0",
          "InstanceType": "t3.large",
          "LaunchTime": "2026-05-02T14:22:10.000Z",
          "State": { "Code": 16, "Name": "running" },
          "PrivateIpAddress": "10.0.3.14",
          "PublicIpAddress": "54.221.10.99",
          "SubnetId": "subnet-0f1e2d3c4b5a69788",
          "VpcId": "vpc-0123456789abcdef0",
          "Architecture": "x86_64",
          "Placement": {
            "AvailabilityZone": "us-east-1a",
            "GroupName": "",
            "Tenancy": "default"
          },
          "Monitoring": { "State": "enabled" },
          "SecurityGroups": [
            { "GroupName": "web-sg", "GroupId": "sg-0a1b2c3d4e5f60718" },
            { "GroupName": "ssh-sg", "GroupId": "sg-08192a3b4c5d6e7f8" }
          ],
          "BlockDeviceMappings": [
            {
              "DeviceName": "/dev/xvda",
              "Ebs": {
                "VolumeId": "vol-0a1b2c3d4e5f60718",
                "Status": "attached",
                "DeleteOnTermination": true,
                "AttachTime": "2026-05-02T14:22:12.000Z"
              }
            },
            {
              "DeviceName": "/dev/xvdb",
              "Ebs": {
                "VolumeId": "vol-08192a3b4c5d6e7f8",
                "Status": "attached",
                "DeleteOnTermination": false,
                "AttachTime": "2026-05-02T14:22:12.000Z"
              }
            }
          ],
          "Tags": [
            { "Key": "Name", "Value": "web-prod-01" },
            { "Key": "Environment", "Value": "production" },
            { "Key": "Team", "Value": "platform" }
          ]
        },
        {
          "InstanceId": "i-0ffff1111eeee2222",
          "ImageId": "ami-0c55b159cbfafe1f0",
          "InstanceType": "t3.micro",
          "LaunchTime": "2026-06-11T09:05:44.000Z",
          "State": { "Code": 80, "Name": "stopped" },
          "PrivateIpAddress": "10.0.3.51",
          "SubnetId": "subnet-0f1e2d3c4b5a69788",
          "VpcId": "vpc-0123456789abcdef0",
          "Architecture": "x86_64",
          "Placement": {
            "AvailabilityZone": "us-east-1a",
            "GroupName": "",
            "Tenancy": "default"
          },
          "Monitoring": { "State": "disabled" },
          "SecurityGroups": [
            { "GroupName": "ssh-sg", "GroupId": "sg-08192a3b4c5d6e7f8" }
          ],
          "BlockDeviceMappings": [
            {
              "DeviceName": "/dev/xvda",
              "Ebs": {
                "VolumeId": "vol-0aaa1bbb2ccc3ddd4",
                "Status": "attached",
                "DeleteOnTermination": true,
                "AttachTime": "2026-06-11T09:05:46.000Z"
              }
            }
          ],
          "Tags": [
            { "Key": "Name", "Value": "batch-worker-07" },
            { "Key": "Environment", "Value": "staging" }
          ]
        }
      ]
    },
    {
      "ReservationId": "r-0999888877776666",
      "OwnerId": "123456789012",
      "Groups": [],
      "Instances": [
        {
          "InstanceId": "i-0c0c0c0c0c0c0c0c0",
          "ImageId": "ami-0d0d0d0d0d0d0d0d0",
          "InstanceType": "m5.xlarge",
          "LaunchTime": "2026-01-20T18:40:00.000Z",
          "State": { "Code": 16, "Name": "running" },
          "PrivateIpAddress": "10.0.9.7",
          "PublicIpAddress": "3.88.200.14",
          "SubnetId": "subnet-0aaaa1111bbbb2222",
          "VpcId": "vpc-0123456789abcdef0",
          "Architecture": "arm64",
          "Placement": {
            "AvailabilityZone": "us-east-1b",
            "GroupName": "",
            "Tenancy": "default"
          },
          "Monitoring": { "State": "enabled" },
          "SecurityGroups": [
            { "GroupName": "db-sg", "GroupId": "sg-0d0d0d0d0d0d0d0d0" }
          ],
          "BlockDeviceMappings": [
            {
              "DeviceName": "/dev/xvda",
              "Ebs": {
                "VolumeId": "vol-0eeee1111ffff2222",
                "Status": "attached",
                "DeleteOnTermination": true,
                "AttachTime": "2026-01-20T18:40:03.000Z"
              }
            }
          ],
          "Tags": [
            { "Key": "Name", "Value": "postgres-primary" },
            { "Key": "Environment", "Value": "production" },
            { "Key": "Team", "Value": "data" }
          ]
        }
      ]
    }
  ]
}
```

### Transform intent

Flatten to one row per instance; pivot the `Tags` array so `Name`/`Environment`/`Team`
become fields; pluck the volume IDs; pick only the fields downstream needs.

JMESPath equivalent (what your engine reproduces):

```
Reservations[].Instances[].{
  id: InstanceId,
  name: Tags[?Key=='Name'] | [0].Value,
  env:  Tags[?Key=='Environment'] | [0].Value,
  team: Tags[?Key=='Team'] | [0].Value,
  type: InstanceType,
  state: State.Name,
  az: Placement.AvailabilityZone,
  vpc: VpcId,
  privateIp: PrivateIpAddress,
  publicIp: PublicIpAddress,
  volumes: BlockDeviceMappings[].Ebs.VolumeId
}
```

### Output

```json
[
  {
    "id": "i-0abcd1234efgh5678",
    "name": "web-prod-01",
    "env": "production",
    "team": "platform",
    "type": "t3.large",
    "state": "running",
    "az": "us-east-1a",
    "vpc": "vpc-0123456789abcdef0",
    "privateIp": "10.0.3.14",
    "publicIp": "54.221.10.99",
    "volumes": ["vol-0a1b2c3d4e5f60718", "vol-08192a3b4c5d6e7f8"]
  },
  {
    "id": "i-0ffff1111eeee2222",
    "name": "batch-worker-07",
    "env": "staging",
    "team": null,
    "type": "t3.micro",
    "state": "stopped",
    "az": "us-east-1a",
    "vpc": "vpc-0123456789abcdef0",
    "privateIp": "10.0.3.51",
    "publicIp": null,
    "volumes": ["vol-0aaa1bbb2ccc3ddd4"]
  },
  {
    "id": "i-0c0c0c0c0c0c0c0c0",
    "name": "postgres-primary",
    "env": "production",
    "team": "data",
    "type": "m5.xlarge",
    "state": "running",
    "az": "us-east-1b",
    "vpc": "vpc-0123456789abcdef0",
    "privateIp": "10.0.9.7",
    "publicIp": "3.88.200.14",
    "volumes": ["vol-0eeee1111ffff2222"]
  }
]
```

**Engine features exercised:** nested flatten across two array levels, filtered
tag pivot with missing-key → `null`, scalar pluck from a sub-array, projection.

---

## 2. Stripe `checkout.session.completed` webhook → internal order record

The full Stripe event is an envelope (`{id, type, data:{object:{...}}}`) wrapping
a large Checkout Session with nested `customer_details`, `total_details`, and
`metadata`. You mediate it into a compact order record for your fulfillment
service.

### Input (real-shape Stripe event)

```json
{
  "id": "evt_1PabcXYZ0000abcd1234efgh",
  "object": "event",
  "api_version": "2026-03-31",
  "created": 1752364800,
  "livemode": false,
  "type": "checkout.session.completed",
  "pending_webhooks": 1,
  "request": { "id": "req_ABCdef123456", "idempotency_key": null },
  "data": {
    "object": {
      "id": "cs_test_a1B2c3D4e5F6g7H8i9J0kLmNoPqRsTuVwXyZ",
      "object": "checkout.session",
      "amount_subtotal": 8900,
      "amount_total": 9612,
      "currency": "usd",
      "customer": "cus_ABC123def456",
      "customer_details": {
        "email": "ada.lovelace@example.com",
        "name": "Ada Lovelace",
        "phone": null,
        "address": {
          "city": "Kyiv",
          "country": "UA",
          "line1": "12 Analytical Engine St",
          "line2": null,
          "postal_code": "01001",
          "state": null
        },
        "tax_exempt": "none"
      },
      "payment_intent": "pi_3PabcXYZ0000abcd1234",
      "payment_status": "paid",
      "mode": "payment",
      "status": "complete",
      "created": 1752364700,
      "expires_at": 1752451100,
      "metadata": {
        "cart_id": "cart_98765",
        "internal_customer_id": "usr_42",
        "channel": "web"
      },
      "shipping_cost": { "amount_total": 500 },
      "total_details": {
        "amount_discount": 0,
        "amount_shipping": 500,
        "amount_tax": 712
      },
      "line_items": {
        "object": "list",
        "has_more": false,
        "data": [
          {
            "id": "li_1PabcAAA",
            "object": "item",
            "quantity": 2,
            "amount_subtotal": 5000,
            "amount_total": 5000,
            "currency": "usd",
            "description": "Mechanical Keyboard",
            "price": {
              "id": "price_1PabcK1",
              "unit_amount": 2500,
              "currency": "usd",
              "product": "prod_KEYB01"
            }
          },
          {
            "id": "li_1PabcBBB",
            "object": "item",
            "quantity": 1,
            "amount_subtotal": 3900,
            "amount_total": 3900,
            "currency": "usd",
            "description": "USB-C Hub",
            "price": {
              "id": "price_1PabcK2",
              "unit_amount": 3900,
              "currency": "usd",
              "product": "prod_HUB07"
            }
          }
        ]
      }
    }
  }
}
```

### Transform intent

Unwrap the envelope; lift `data.object` fields; rename to your vocabulary;
convert Stripe minor units (cents) to a decimal `amount`; reshape line items;
promote `metadata` fields to first-class; keep the event id for idempotency.

### Output (internal order record)

> The `placedAt` line below is illustrative only: `created` (`1752364700`) →
> ISO-8601 needs a date function the pinned engine does not have, so this field
> is **not** produced by any matched fixture (it is `refuse`-only per AD-023);
> the shipped `stripe-*` fixtures omit `placedAt`.

```json
{
  "orderId": "cs_test_a1B2c3D4e5F6g7H8i9J0kLmNoPqRsTuVwXyZ",
  "source": "stripe",
  "eventId": "evt_1PabcXYZ0000abcd1234efgh",
  "eventType": "checkout.session.completed",
  "placedAt": "2026-07-13T00:00:00Z",
  "status": "paid",
  "cartId": "cart_98765",
  "channel": "web",
  "customer": {
    "internalId": "usr_42",
    "stripeId": "cus_ABC123def456",
    "name": "Ada Lovelace",
    "email": "ada.lovelace@example.com",
    "address": {
      "line1": "12 Analytical Engine St",
      "city": "Kyiv",
      "postalCode": "01001",
      "country": "UA"
    }
  },
  "currency": "USD",
  "amounts": {
    "subtotal": 89.00,
    "shipping": 5.00,
    "tax": 7.12,
    "discount": 0.00,
    "total": 96.12
  },
  "items": [
    { "product": "prod_KEYB01", "description": "Mechanical Keyboard", "quantity": 2, "unitPrice": 25.00, "lineTotal": 50.00 },
    { "product": "prod_HUB07",  "description": "USB-C Hub",          "quantity": 1, "unitPrice": 39.00, "lineTotal": 39.00 }
  ]
}
```

**Engine features exercised (structural → matched):** envelope unwrap (deep path
`data.object`), minor-unit → decimal derivation (`amount / 100`), metadata
promotion, per-element array reshape. **Not engine-expressible (→ `refuse`
fixtures per AD-023):** `epoch → ISO date` (the `placedAt` field) and `uppercase`
coercion of `currency` — the shipped `stripe-*` matched fixtures drop those two.

---

## 3. GitHub `push` webhook → internal deploy event + Slack message

The GitHub `push` payload is large: a full `repository` object, `pusher`,
`sender`, and a `commits` array where each commit carries `added` / `removed` /
`modified` file lists. Two common downstream targets: a compact deploy-trigger
event, and a human-readable Slack message.

### Input (real-shape `push` payload, trimmed of a few always-present noise fields)

```json
{
  "ref": "refs/heads/main",
  "before": "9d8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f",
  "after": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
  "created": false,
  "deleted": false,
  "forced": false,
  "compare": "https://github.com/acme/payments-api/compare/9d8f7a6b5c4d...1a2b3c4d5e6f",
  "repository": {
    "id": 555000111,
    "node_id": "R_kgDOICEXYZ",
    "name": "payments-api",
    "full_name": "acme/payments-api",
    "private": true,
    "owner": {
      "name": "acme",
      "login": "acme",
      "id": 900112233,
      "type": "Organization"
    },
    "html_url": "https://github.com/acme/payments-api",
    "default_branch": "main",
    "visibility": "private",
    "pushed_at": 1752364800,
    "language": "Go"
  },
  "pusher": { "name": "ada", "email": "ada@acme.io" },
  "sender": {
    "login": "ada",
    "id": 700334455,
    "type": "User",
    "html_url": "https://github.com/ada"
  },
  "commits": [
    {
      "id": "0f1e2d3c4b5a69788a9b0c1d2e3f4a5b6c7d8e9f",
      "message": "Add idempotency keys to refund endpoint",
      "timestamp": "2026-07-12T22:14:03+03:00",
      "url": "https://github.com/acme/payments-api/commit/0f1e2d3c",
      "author": { "name": "Ada Lovelace", "email": "ada@acme.io", "username": "ada" },
      "committer": { "name": "Ada Lovelace", "email": "ada@acme.io", "username": "ada" },
      "added": ["internal/refund/idempotency.go"],
      "removed": [],
      "modified": ["internal/refund/handler.go", "internal/refund/handler_test.go"]
    },
    {
      "id": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
      "message": "Fix nil deref when card country is missing",
      "timestamp": "2026-07-12T22:31:40+03:00",
      "url": "https://github.com/acme/payments-api/commit/1a2b3c4d",
      "author": { "name": "Ada Lovelace", "email": "ada@acme.io", "username": "ada" },
      "committer": { "name": "Ada Lovelace", "email": "ada@acme.io", "username": "ada" },
      "added": [],
      "removed": [],
      "modified": ["internal/checkout/validate.go"]
    }
  ],
  "head_commit": {
    "id": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
    "message": "Fix nil deref when card country is missing",
    "timestamp": "2026-07-12T22:31:40+03:00",
    "author": { "name": "Ada Lovelace", "email": "ada@acme.io", "username": "ada" }
  }
}
```

### Transform intent A — compact deploy-trigger event

Derive `branch` from `ref` (strip `refs/heads/`); count commits; aggregate all
touched files across commits; set `deploy` true only for `main`; carry the head
SHA.

### Output A

```json
{
  "event": "push",
  "repo": "acme/payments-api",
  "branch": "main",
  "headSha": "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b",
  "pusher": "ada",
  "commitCount": 2,
  "filesChanged": [
    "internal/refund/idempotency.go",
    "internal/refund/handler.go",
    "internal/refund/handler_test.go",
    "internal/checkout/validate.go"
  ],
  "deploy": true
}
```

### Transform intent B — Slack message (envelope for a different downstream)

Same input, different target contract: build Slack's `{text, blocks}` shape,
joining commit subjects into a bulleted string.

### Output B

```json
{
  "channel": "#deploys",
  "text": "ada pushed 2 commits to acme/payments-api (main)",
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*<https://github.com/acme/payments-api|acme/payments-api>* — 2 new commits on `main` by ada"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "• Add idempotency keys to refund endpoint\n• Fix nil deref when card country is missing"
      }
    }
  ]
}
```

**Engine features exercised (structural → matched):** aggregate/flatten
`added|removed|modified` across an array of commits, count (map→`1` then `expr`
`+` reduce), conditional boolean (`deploy` via `ref == "refs/heads/main"` — a
full-string compare, no strip), two output envelopes from one input, `format`
interpolation for the Slack text. **Not engine-expressible (→ `refuse` fixtures
per AD-023):** deriving `branch` by stripping the `refs/heads/` prefix, and the
separator-aware bulleted join of commit subjects.

---

## Where to get the raw big payloads (capture your own)

The realest fixtures come from capturing live traffic. Sources and how to pull them:

- **AWS EC2** — run `aws ec2 describe-instances` (or `describe-volumes`,
  `describe-security-groups`) against a real account for genuinely huge nested
  output; the docs also embed full sample responses:
  https://docs.aws.amazon.com/cli/latest/userguide/cli-usage-filter.html and the
  command reference with full output samples:
  https://awscli.amazonaws.com/v2/documentation/api/2.9.6/reference/ec2/describe-instances.html
- **Stripe** — the Stripe CLI generates real event payloads on demand:
  `stripe trigger checkout.session.completed` (also `payment_intent.succeeded`,
  `invoice.paid`, `customer.subscription.updated`). Event schema + envelope:
  https://docs.stripe.com/webhooks — capture the JSON your listener receives.
- **GitHub** — official "webhook events and payloads" reference documents every
  event's full JSON; the Octokit project also publishes payload example
  fixtures. Repo: https://github.com/octokit/webhooks — and you can redeliver
  real deliveries from a repo's Settings → Webhooks → Recent Deliveries.
- **JOLT larger fixtures** — some `shiftr` test files are sizeable, real-shape
  documents with paired `expected` output:
  https://github.com/bazaarvoice/jolt/tree/master/jolt-core/src/test/resources/json/shiftr
- **JMESPath compliance data** — the `given` documents in the test suite include
  non-trivial nested inputs with expected results:
  https://github.com/jmespath/jmespath.test

### Practical tip for your library

Under the AD-023 constructed-fixture rule the workflow is **author → engine-freeze**,
never hand-write: construct a realistic input, author a Transon template, and take
each case `output` from **re-executing that template through the pinned engine**
(the seed template lives in `evals/seeds/` as provenance only; `check_evals --lint`
re-freezes it against every case — FR-033 / AC-035). Never hand-write an
`expected.json`. **Live-captured API / webhook payloads are out of scope for v1 and
must not be committed** — the only real-use capture path is FR-018 / NFR-011, which
requires privacy redaction and recorded consent first. The JOLT / JMESPath suites
are cited as structural inspiration for the input *shapes* only, not as an
expected-output workflow.
