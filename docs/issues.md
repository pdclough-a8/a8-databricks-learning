# Issues and decisions

| ID | Status | Issue / decision |
|---|---|---|
| P01 | Preserved | New repo already had a tracked README deletion; use START_HERE instead |
| P02 | Resolved | Brand guide unavailable after context restore; user supplied full playbook |
| P03 | Open for release | Official logo files and exact visual tokens absent; provisional text/palette used |
| P04 | Open for teaching | Target-workspace acceptance remains unrun |
| P05 | Resolved | Python 3.14 dependency installation failed; use supported Python 3.12/3.13 |
| P06 | Deliberate boundary | App uses packaged fixture, not learner's catalog table |
| P07 | Resolved | Repo-local package target triggered Streamlit development mode; set explicit production mode |

## P03, branding

Apply the supplied voice and visual direction without reproducing internal strategy or inventing an
official wordmark. Get approved assets and brand review before public release.

## P04, live platform uncertainty

Workspace-source app deployment, per-app source read permissions, notebook `%run` widgets, SQL upload UI,
runtime packages and model parameter support require the [live acceptance matrix](validation.md).
Serving-endpoint integration is explicit; gateway-only policy needs an adapted, tested future route.

## P05, maintainer environment

Initial system Python 3.14 install tried to build unsupported PyArrow from source and failed.
Python 3.12.13 with a repo-local `.packages` target installed the pinned direct dependencies successfully.
The install reported a hardlink-to-copy fallback, with no effect on the course. No original-project
environment was modified.

Add new entries with: symptom, scope, cause/evidence, fix or blocker, checks run, and remaining uncertainty.
Do not include credentials, personal workspace paths, private URLs or raw service logs.

## P07, local preview

The first local server launch failed before accepting connections: Streamlit inferred development
mode from the nonstandard `.packages` install location, conflicting with an explicit port.
The app's `.streamlit/config.toml` now sets `global.developmentMode = false`.
No user-global configuration or CORS/XSRF protection was weakened.
