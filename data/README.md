# data/

**Synthetic data only.** Never place real customer, policy, payment or personal data here.

Planned fixtures (not yet created):

| Dataset              | Total | Split (approved 2026-11-05)        |
|----------------------|-------|------------------------------------|
| Users                | 6     | 3 per tenant (one per role)        |
| Customers            | 20    | 10 Northstar, 10 Meridian          |
| Tickets              | 10    | 5 Northstar, 5 Meridian            |
| Knowledge documents  | 8     | 4 Northstar, 4 Meridian            |

Every record belongs to exactly one tenant. No KB document is shared across tenants.
Some KB documents and tickets will intentionally contain
injection-style text to support attack cases. That text is test content, not instructions.

Synthetic data conventions (to apply when fixtures are created):
- Emails use reserved domains, e.g. `@example.com` / `@example.org`.
- Phone numbers use clearly fictional ranges.
- No real names of public figures, real policy numbers or real card/bank numbers.
