# Zenodo deposit 23204768

**Status: DRAFT. Not published. No DOI minted.**

| | |
|---|---|
| Deposit id | `23204768` |
| Edit URL | https://zenodo.org/deposit/23204768 |
| State | `unsubmitted` |
| Title | COSMOS Test Suite v0.1.0: a platform for attempting to falsify cosmological hypotheses |
| Version | 0.1.0 |
| Upload type | software |
| Licence | GPL-3.0-only |
| Creator | Nortaq-PlayNexus (independent) |
| Keywords | 8 |
| Archive | `cosmos-test-suite-0.1.0.tar.gz` |
| Archive bytes | 217,663 |
| Archive SHA-256 | `e73a4acd34c64974e3de33ea891e084976b194c1ce2fc3ecede20446f9ca6e4e` |
| Zenodo MD5 | `3337c7ff7ca3273a4e29977b51284bae` |

The archive is `git archive` of tag `v0.1.0` (commit `fca791d`), so it contains
exactly what was committed at that tag and nothing else — no `.git`, no
untracked files, no local artifacts.

## Why this is still a draft

Publishing mints an immutable DOI. It cannot be edited afterwards; a correction
requires a new version, and a new version cannot be created through the
deposition API (`conceptrecid` is accepted and then ignored, so a new version
lands on a different concept).

Two things should be settled on the review page first:

1. **Read the description top to bottom.** It opens with "No scientific findings
   are claimed." That sentence is the load-bearing part of the record, because a
   DOI is what someone will find when they go looking for evidence about a
   cosmological question.
2. **Check the metadata fields the API silently drops.** An earlier deposit in
   this account supplied `subjects` and `references`; both were accepted, echoed
   nowhere, and had to be entered in the web form. `docs/ZENODO_METADATA.json`
   deliberately omits them rather than assume they persisted.

## To publish

Open https://zenodo.org/deposit/23204768, confirm the fields, and publish from
the web form. Or, having decided deliberately:

```powershell
python tools/upload_to_zenodo.py --metadata docs/ZENODO_METADATA.json `
    --description docs/ZENODO_DESCRIPTION.md `
    --archive ..\cosmos-test-suite-0.1.0.tar.gz --reuse 23204768 --publish
```

## After publishing

Paste the version DOI into `CITATION.cff` and into `docs/ZENODO_METADATA.json`,
then commit. Note that the next change to this deposit must be a **new version**,
not an edit.

## Related, and deliberately not linked

DOI `10.5281/zenodo.23109117` covers ScientificDiscoveryLab. That work shares no
data, no code and no conclusions with COSMOS Test Suite, so no
`related_identifiers` entry points at it. Linking them would suggest a shared
result that does not exist.
