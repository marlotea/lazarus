# CEBRA control analyses: data and comparison plan (draft)

All data come from the IBL Brain-Wide Map, release `2023_12_bwm_release`. We use BWM good units
(`label == 1`, spike sorting revision `2024-05-06`), Beryl region labels, and BWM-masked trials
(`load_trials_and_mask`: reaction time 0.08–2 s, no NaN events). Unit counts below are good units
per (session, Beryl region), taken from `bwm_units`.

## What a "representation" is

A **recording** is (session, Beryl region, trial subset). Its binned spike counts
(20 ms bins, units of that region only, every probe in the session pooled) go into one independently
trained **CEBRA-Time** model. The **representation of (region, phase)** is the set of trial-averaged
embedding trajectories inside that phase's event-aligned window, one trajectory per trial condition.

| phase      | aligned to            | window        |
|------------|-----------------------|---------------|
| `pre_stim` | `stimOn_times`        | −300 → 0 ms   |
| `stim`     | `stimOn_times`        | 0 → 300 ms    |
| `move`     | `firstMovement_times` | −100 → 200 ms |
| `feedback` | `feedback_times`      | 0 → 300 ms    |

Conditions are stimulus side × choice (4 conditions, error trials are the 2 off-diagonal ones). A
condition is kept only if it has ≥ 5 trials on both sides of the comparison. All windows are the same
length (15 bins), so phases can also be compared with each other; those cross-phase pairs act as
nulls. On fast trials `stim` and `move` overlap. That raises cross-phase similarity, so it can only
make the result harder to pass.

### Why CEBRA-Time (no labels)

CEBRA-Behavior with phase or condition labels would force embeddings of the same phase together,
which would make "same phase looks similar" true by construction. CEBRA-Time only uses temporal
contrast (positive pairs are 10 bins = 200 ms apart), so any phase or condition structure in the
embedding comes from the neural data. A hybrid or behavior-labelled variant can be added later as a
separate condition (`CebraConfig.conditional`).

### Default hyperparameters (`src/lazarus/embed.py`)

`offset10-model`, `time_offsets=10`, output dim 8, 32 hidden units, cosine distance, temperature 1,
batch 512, lr 3e-4, 5000 iterations, raw counts. Each fit records its InfoNCE goodness-of-fit (bits)
as a QC value.

## How two representations are compared (`src/lazarus/compare.py`)

The two sides give matched point clouds P, Q (shared conditions × 15 time bins, 8-d). Rows correspond
to each other. The models were trained independently, so each embedding is only defined up to a
transformation, and every metric is at least rotation-invariant:

| metric         | what it measures |
|----------------|------------------|
| `procrustes`   | 1 − Procrustes disparity (translation, scale, orthogonal). **Primary metric**, because the identifiability class of a cosine-CEBRA model is orthogonal. |
| `linear_r2_cv` | R² of an affine map Q→P and P→Q, fit leave-one-condition-out. This is CEBRA's consistency score, but cross-validated so an 8-d affine map can't fit noise. |
| `cka`          | Linear CKA. |
| `rsa`          | Spearman correlation between the two pairwise-distance matrices. Needs no alignment. |

Planned addition: a **Gromov–Wasserstein distance** (POT `ot.gromov`) between the two point clouds
(or between single-trial clouds). It needs no point correspondence, so it also works where conditions
or timing differ, for example across animals with different reaction-time distributions.

Every control reports four categories of pairs: same region and same phase (the hypothesis),
same region with a different phase, a different region with the same phase, and both different.
The test is one-sided Mann–Whitney: the "same region, same phase" pairs against all other pairs.
The controls are nested, so we expect C1 ≥ C2 ≥ C3 > nulls. Each control's similarity is the
ceiling for the next.

---

## Control 1: within-session split (implemented: `scripts/control1.py`)

**Question:** do two halves of one session give the same representation for each region and phase?

**Data:** ZM_2241 (mainenlab), 2020-01-30, eid `ee40aece-cffd-4edb-a4b6-155f158c666a`, 2 probes.
Regions with ≥ 15 units: MD 107, SMT 58, Eth 51, PO 46, VISa 44, LP 24, DG 21, PCN 19, CA1 15.

We chose this session because it has the most regions of any session whose mouse also has repeat
recordings (for C2), and because it includes the IBL repeated-site regions VISa, LP, PO, DG and CA1,
which are recorded in many mice (for C3).

**Split:** consecutive trials are cut into chunks of 10 and assigned alternately to A and B. The
chunks tile the session's time from the start of the first trial to the end of the last, so A and B
are disjoint and each contains its ITIs. Alternating chunks balance slow drift, engagement and the
probabilityLeft blocks across the two halves. `--split halves` (first half vs second half) is a
harder variant that leaves drift in as a confound.

**Models:** each region gets one model on A and one on B (seed 0). A second seed on A is a ceiling:
same data, different initialisation.

**Comparisons:** every (region, phase) in A is compared against every (region, phase) in B, which
gives the full matrix and its four categories.

**Expected result:** the diagonal (same region, same phase) beats the off-diagonal pairs and
approaches the seed ceiling.

**Outputs** go to `results/control1/<eid>_<split>_cfg-<hash>/`: `pairwise.csv`, `seed_ceiling.csv`,
`summary.json`, `matrix_procrustes.png`, `categories.png`, and `traj_<region>.png` (A and B
trajectories after Procrustes alignment).

**First result** (5000 iterations, config hash `66ad43d3`, 9 regions × 4 phases):

| category                | procrustes | linear_r2_cv | cka  | rsa  | n pairs |
|-------------------------|-----------:|-------------:|-----:|-----:|--------:|
| same region, same phase | **0.80**   | **0.85**     | **0.83** | **0.84** | 36 |
| same region, diff phase | 0.66       | 0.73         | 0.74 | 0.75 | 108 |
| diff region, same phase | 0.67       | 0.73         | 0.72 | 0.74 | 288 |
| diff region, diff phase | 0.62       | 0.66         | 0.69 | 0.71 | 864 |

The values are medians. The same-region-same-phase pairs beat the off-diagonal pairs on every metric
(one-sided Mann–Whitney p < 1e-6). The seed ceiling is about 0.98, so most of the gap from 1 comes
from trial-to-trial noise in each half, not from model nondeterminism. The weakest regions are the
ones with few units: DG (21) at 0.52–0.64 and CA1 (15) at `pre_stim` 0.47.

Caveats:
- PO, Eth, MD, VISa and SMT cross-match at high values, especially in `pre_stim` and `feedback`.
  With only 4 condition means per phase, part of the similarity is the shared layout of the
  conditions rather than anything region-specific.
- PO looks alike across all of its phases.
- Unit-matched subsampling and GW (planned for C2/C3) should be checked on C1 as well.

## Control 2: same animal, different sessions (planned)

**Question:** is the representation of (region, phase) stable across days in one mouse? The neurons
are different on each day.

**Data:** (subject, region) pairs recorded in ≥ 2 BWM sessions with ≥ 20 units each. There are 114
such pairs across 59 mice. Start with the pairs that have ≥ 3 sessions:

| subject       | region | sessions | units per session |
|---------------|--------|---------:|-------------------|
| CSH_ZAD_026   | CP     | 5 | 110/136/57/55/109 |
| PL037         | MRN    | 5 | 24/26/56/53/40 |
| DY_014        | CP     | 4 | 47/42/67/107 |
| DY_020        | MRN    | 4 | 76/55/28/28 |
| ibl_witten_29 | CP     | 4 | 67/51/48/21 |
| KS023         | LSr    | 4 | 36/37/30/44 |
| ZM_2241       | CP     | 3 | 94/28/79 (MD: 107/61 over 2 sessions, links to C1) |
| CSH_ZAD_026   | MOp    | 3 | 67/139/33 |
| NR_0020       | CA1    | 3 | 20/39/26 |
| CSH_ZAD_019   | APN    | 3 | 37/53/48 |
| KS014         | SCm    | 3 | 90/46/26 |

The full list comes from `lazarus.ibl.region_unit_counts(20)`, grouped by (subject, Beryl) with
nunique(eid) ≥ 2.

**Recordings:** (session, region, all trials) via `recording.all_trials`, one model per session.
CEBRA multi-session training is deliberately **not** used: it would align the sessions through shared
labels, which is circular for this question.

**Confound control:** unit counts differ between sessions. Subsample every recording to the minimum
N of the pair (or a fixed N = 20) with K = 5 random draws and average the metrics. Apply the same
subsampling to a C1 rerun so the two controls can be compared.

**Comparisons:** same subject and region across sessions, against nulls (a different region in the
other session, or the same region in a different phase). Report against the C1 diagonal for the same
region and N, and report as a function of days between sessions.

## Control 3: across animals (planned)

**Question:** is the representation of (region, phase) shared across mice?

**Data:** one session per (subject, region), choosing the session with the most units. Use the
repeated-site regions first, since they were targeted with the same coordinates in every lab:

| region | mice | labs | median units |
|--------|-----:|-----:|-------------:|
| LP     | 37 | 11 | 34 |
| PO     | 35 | 11 | 56 |
| VISa   | 24 |  9 | 29 |
| CA1    | 21 |  8 | 31 |
| DG     | 12 |  8 | 32 |

Broadly sampled regions can follow: MRN (45 mice), APN (31), CP (25), SCm (24), VPM (23). Counts are
mice with ≥ 20 units in the region.

**Recordings and confounds:** the same as C2: all trials, units subsampled to a fixed N. Mice also
differ in behaviour, especially reaction time. The event-aligned windows absorb part of this, and GW
needs no correspondence. Also stratify by lab and report within-lab vs between-lab pairs, since lab
was a known source of variance in the IBL reproducibility paper.

**Comparisons:** all pairs of mice for the same region and phase, against a different region (from
the same or another mouse) with the same phase. This gives a region × region similarity matrix
averaged over mouse pairs. If representations are region-specific, the diagonal dominates.

---

## Reusable pipeline

```
lazarus.ibl          load_session(eid) -> Session (good units + Beryl, BWM-masked trials);
                     region_unit_counts() is the planning table for every control
lazarus.recording    split_trials / all_trials -> chunks; build_recording(session, region, split, chunks)
lazarus.embed        CebraConfig, fit_cebra (cached per recording/config/seed)
lazarus.phases       PHASES, compute_trajectories -> Trajectories (condition means + single trials)
lazarus.pipeline     embed_recording(rec, cfg, seed) -> Trajectories, cached under results/embeddings/
lazarus.compare      compare_trajectories(a, b), compare_all(trajs, pair_filter), label_comparison
lazarus.plots        similarity matrix, category summary, aligned trajectories
scripts/controlN.py  chooses the recordings and the pair_filter for one control
```

Controls 2 and 3 only need a new script. It builds `all_trials` recordings for the chosen sessions,
calls `embed_recording`, then `compare_all` with a `pair_filter` (for C2, same subject with a
different eid; for C3, a different subject). The remaining work is unit subsampling, the GW metric,
and the C2/C3 scripts.
