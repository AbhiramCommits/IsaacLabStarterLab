# ISSUE-003: Dataset hash looked like a universal constant

- **Status:** fixed
- **Severity:** minor — misleading expected value, no failed check
- **Guide step:** Exercise 4, "seeded domain randomisation and evaluation"
- **Track:** Docker versus native
- **Found in:** `0871aa8`

## Symptom

The guide printed the native dataset hash
`9f14c0388aafd557c4325ebbc47319198c3fd1dac8786c9b9f106723b3b90c96`. Running
`make dr` inside the Docker image printed a different hash while every
perception metric was identical and `labcheck ex4` passed.

## Exact message

```text
dataset: datasets/dr
count: 200
dataset_hash: f868fa8b7403e44fcb42e5dc4b5dee6542e9eabd43c716c34025571471d0f490
```

## Cause

The manifest hashes raw PNG bytes and full-precision label JSON. PNG compressor
output and libm float spelling differ between macOS/arm64 and Linux/x86_64 even
when the decoded pixels and every measured metric are identical. The guide
presented the build-machine value without scope.

## Fix

The guide now states that the dataset hash is a **self-consistency** hash, not a
cross-platform constant, gives both measured values, and explains that
`labcheck ex4` recomputes the hash from the manifest in the learner's
environment. `README.md` labels the results as build-machine measurements and
`docs/VERIFICATION.md` records the scope. No code change was needed: the scene
hash is the cross-machine pin, and it is now portable (ISSUE-001).
