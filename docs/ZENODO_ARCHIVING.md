# How to archive this release on Zenodo

Everything on the Zenodo side needs your account. I cannot create the record
without a token, and I would not use your credentials even if they were sitting
in the environment. Below is the exact path, with the two choices you have to
make stated up front.

## Option A — let Zenodo pull from GitHub (recommended)

One-time setup, then every future release is automatic.

1. Create a Zenodo account and verify it by email.
2. Go to https://zenodo.org/account/settings/applications/
3. Click "New personal access token".
4. Under **Repository permissions**, tick `zenodo:zenodo.github_repo_access`
   (`repo:read` and `public:read` are ticked by default).
5. On your repository's GitHub page, go to **Settings → Integrations →
   Zenodo**, and paste the token. Save. GitHub will immediately show a banner
   with a **Enable** button. Click it.
6. Return to https://zenodo.org/account/settings/applications/. Zenodo will
   show `Nortaq-PlayNexus/COSMOS-TEST-SUITE` as enabled.

7. Create the archive. On Zenodo, **New upload → GitHub Zenodo integration**,
   pick the repository and the `v0.1.0` release tag, then complete the metadata
   form.

After this, `git push --tags` archives each new tag automatically.

## Option B — upload the tarball by hand

1. Create a token with the `zenodo:zenodo_deposit` scope at the same settings
   page.
2. Build and upload:

```bash
# from the repository root
git archive --format=tar.gz --prefix=COSMOS-TEST-SUITE-0.1.0/ -o ../cosmos-test-suite-0.1.0.tar.gz v0.1.0
```

3. Upload at https://zenodo.org/upload/new. The tarball is roughly a few MB;
   `git archive` excludes `.git` and any untracked files, so it contains only
   what was committed at the tag.

## Metadata to paste

Fill these in rather than accepting the defaults. The title and description are
where a reader decides whether this is a results paper or a platform.

**Title**

> COSMOS Test Suite v0.1.0: a platform for attempting to falsify cosmological hypotheses

**Description**

> A research platform for testing cosmological and fundamental-physics
> hypotheses by attempting to falsify them rather than confirm them. Provides
> pre-registered analysis plans, adversarial review stages, look-elsewhere
> correction, provenance chains, and reproducibility packages.
>
> **No scientific findings are claimed.** At the time of this release none of
> the 35 registered research questions has been answered, and the single
> implemented experiment (EXP-001) has only ever consumed synthetic data. One
> external validation was performed, of baryon acoustic oscillation distance
> measures against real DESI DR2 vectors; it identified one error in this
> codebase and one unresolved labelling problem in a third-party data mirror.
>
> The platform is released so that others can find the same bugs, and so that
> future results have a pre-registered, falsifiable framework to be produced in.

**Keywords**

> cosmology, large-scale structure, baryon acoustic oscillations, scientific
> methodology, falsification, reproducibility, open science

**License** — GPL-3.0-only (GitHub already detects it; confirm it carries over).

**Upload type** — Software.

**Creators** — your own name, with ORCID if you have one. Note that the creator
you enter is the person Zenodo credits permanently, and it cannot be changed
after publication.

## What will be permanent

A Zenodo DOI is a permanent, citable public act. Concretely:

- The DOI never breaks and always resolves to the archived tarball.
- The metadata is versioned permanently; a mistake becomes a new version rather
  than an edit.
- Your name is attached to it as author, publicly and permanently.

I think that is worth doing now: the release is honest about having no results,
and archiving it establishes the citable platform the spec asks for before any
findings exist to attach to it. That ordering is better than the reverse.

## Do not do this yet

Do not mint a DOI for a version that claims to answer a research question. None
of the 35 questions is answered, and the release notes say so. If a DOI is
attached to this and someone cites it later as evidence for or against a
cosmological claim, the DOI makes that miscitation harder to spot.
