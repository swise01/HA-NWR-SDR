# Security Policy

## Supported versions

Pacefinder is a small project; only the latest tagged release on `main`
receives security fixes. If you're running an older version, please pull
the latest before reporting.

| Version | Supported |
| ------- | --------- |
| Latest tagged release | ✅ |
| Older releases        | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Use GitHub Security Advisories on this repo:

1. Go to the **Security** tab.
2. Click **Report a vulnerability**.
3. Fill in the form privately.

That keeps the report off the public issue tracker until a fix is ready.

You can expect:

- An acknowledgement within ~3 business days.
- A first assessment within 7 days.
- A fix or mitigation plan within 30 days for confirmed issues, faster
  for high-severity ones.
- Public disclosure coordinated with you after a fix is released.

## Out of scope

- Issues that require physical access to the machine running the
  listener.
- Issues that depend on a malicious local user already having shell
  access.
- The dashboard being publicly exposed on an untrusted network — the
  dashboard is designed for trusted home networks and binds to all
  interfaces by default. Don't expose it to the internet without a
  reverse proxy and auth in front.

## Hardening tips

- Run the listener as a non-root user (the systemd unit already does).
- Bind the dashboard to localhost (`127.0.0.1`) if you don't need LAN
  access from other devices.
- Don't commit your `simtelemetry.config.json` if it contains an
  Anthropic API key — the file is `.gitignore`'d by default.