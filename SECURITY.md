# Security policy

This repository is an interview-oriented reference implementation, not a production operations platform.

Please do not put real API keys, production logs, customer data, credentials, internal hostnames or incident records in issues or pull requests. Report a security concern privately through GitHub's security advisory feature when possible.

The V2 demo exposes read-only tools only. Authentication, RBAC, tenant isolation, rate limiting and audit logging are implemented so these boundaries can be tested, but the local HMAC identity provider and JSONL audit store must be replaced before production use. See `docs/security_threat_model.md` for current controls and known gaps.

