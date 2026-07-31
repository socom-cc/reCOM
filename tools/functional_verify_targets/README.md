# Functional verification targets

Each `*.json` file is a deterministic behavioral smoke target. Its filename
stem and `id` must match. Required field `command` is a non-empty string array.
Optional fields are `summary`, `cwd`, `timeout_seconds` (1–600),
`expected_exit_code`, string-to-string `environment`, and a descriptive
`contract` object with inputs, outputs, limitations, and owner relationships.

Targets may write only to their declared disposable build/output area. Passing
a functional target proves its stated behavior contract only; it does not prove
source identity, ABI, order, provider closure, or byte equivalence.
