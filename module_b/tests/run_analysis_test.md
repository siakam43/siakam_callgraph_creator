# Module B: Analyze Indirect Call Tests

Validates `module_b/analyze_indirect.md` prompt against representative indirect call fixtures.

## Setup

Test fixtures and expected results are in:
- `module_b/tests/fixtures/` — 36 indirect_point JSON files (Module A format)
- `module_b/tests/expected/` — corresponding expected analysis results
- `module_b/tests/manifest.json` — fixture index with category/example metadata

Only fixtures whose `func` matches a test_bench ground_truth caller are included.
This ensures expected callee data is verified.

## Procedure

For each fixture `<uid>.json`:

1. Read the fixture to get the indirect call point (uid, func, file, line, expression)
2. Use the `analyze_indirect.md` prompt to analyze this single indirect call
3. The LLM should:
   - Read the source file at the given file path
   - Trace the function pointer assignment
   - Identify target callee functions
   - Write result to `.siakam_out/indirect/<uid>.json`
4. Compare output against `expected/<uid>_expected.json`

## Pass Criteria

For each fixture:
- [ ] `status` is `"completed"`
- [ ] All expected callees appear in `possible_targets` (recall)
- [ ] No callee in `possible_targets` is absent from expected (precision)
- [ ] `confidence` is reasonable (not all "high" for genuinely ambiguous cases)

## Fixture Coverage

| Category | Examples | Indirect Points |
|----------|----------|----------------|
| fnptr-only | example_1,4,10 | 4 |
| fnptr-struct | example_1,6,14 | 6 |
| fnptr-callback | example_1,8,15 | 6 |
| fnptr-global-struct | example_1,10 | 2 |
| fnptr-global-array | example_1,5 | 2 |
| fnptr-global-struct-array | example_1,10,12 | 3 |
| fnptr-cast | example_1,5 | 3 |
| fnptr-dynamic-call | example_1,4 | 3 |
| fnptr-library | example_1,14,20 | 5 |
| fnptr-varargs | example_1 | 1 |
| fnptr-virtual | example_1 | 1 |
| **Total** | **24 examples** | **36** |

## Notes

- Expected callee data is from test_bench ground_truth.json, cross-referenced by caller function name.
  Fixtures where the indirect point caller is not in test_bench's ground truth are excluded.
- The source files referenced by `"file": "fixture.c"` can be found at
  `module_a/tests/fixtures/<category>/<example>/fixture.c`.
