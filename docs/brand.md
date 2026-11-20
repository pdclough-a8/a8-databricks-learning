# A8 brand application

The course applies the supplied **Brand Foundations Playbook, V4, 1 April 2026**, as a voice
and positioning reference. The internal playbook itself is not included or reproduced here.

## What that changes in the learning

- **Business first:** open with the operations decision and the evidence needed to make it.
- **Strategy, execution, enablement:** keep the purpose, working implementation and handover connected.
- **Pragmatic by design:** one connected Events scenario and explicit boundaries, not a platform framework.
- **Talk like a human:** plain UK English, direct steps, useful recovery guidance.
- **Back it up:** give expected facts and validation limits. Don't invent ROI or imply production readiness.
- **Build capability:** supplied code supports learners, then hints fade into independent transfer.

This is education, not a sales pitch. Competitor commentary, client lists, testimonials, market statistics
and internal targeting material are deliberately absent.

## Visual implementation

Plain **A8** text branding identifies the learning experience in the notebooks. The Analytics8 logo
(`docs/assets/a8-logo.png`, 798 x 286 px) was supplied by the course owner and is used unaltered on the
documentation site header and overview, `README.md` and `START_HERE.md`. It is not redrawn or recoloured.
The logo is dark on white, so the site header is white with the orange rule beneath it.
Databricks notebooks do not show the logo: image rendering from a Git folder is unverified, so notebooks keep text branding.
Charcoal, white, light grey, simple rules and an orange highlight echo the supplied visual examples.
System sans-serif typography avoids inventing a licensed brand-font requirement or loading external fonts.

| Provisional token | Value | Use |
|---|---|---|
| Ink | `#1d2225` | Headings, header, app text |
| Paper | `#ffffff` | Reading surface |
| Soft surface | `#f2f2f2` | App secondary areas |
| Highlight | `#ff5b35` | Decorative orange rule, not body text |
| Readable accent | `#a93614` | Links, controls and focus |

These are **course implementation choices**, not official A8 colour specifications.
Dark orange is used for small text/control contrast rather than copying bright-orange body copy.
Links remain underlined; status is communicated with words, not colour alone.
The stylesheet retains visible keyboard focus and responsive Material navigation.

Before public release, confirm the supplied logo file is the approved master, and obtain exact colour/font
tokens, usage rules (clear space, minimum size) and brand-owner review. Replace tokens in `docs/stylesheets/a8.css`,
`lib/a8learn/__init__.py` (notebook cards).
Do not extract or redraw a logo from a slide.
