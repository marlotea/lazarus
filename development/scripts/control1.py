"""Control 1: within-session split-half consistency of CEBRA representations.

One session is split into two interleaved halves (alternating 10-trial chunks). For every region with
enough units, an independent CEBRA-Time model is trained on each half. Each half's embedding is
summarised as condition-averaged trajectories per task phase, and every (region, phase) of half A is
compared with every (region, phase) of half B. The control passes if "same region, same phase" pairs
are more similar than the off-diagonal pairs. A second seed on half A gives a ceiling (same data,
different model initialisation).

    uv run python scripts/control1.py                              # default session, all regions
    uv run python scripts/control1.py --regions MD PO --iters 1000 # quick run
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from lazarus.compare import METRICS, compare_all, compare_trajectories, label_comparison
from lazarus.embed import CebraConfig
from lazarus.ibl import load_session
from lazarus.phases import PHASES
from lazarus.pipeline import RESULTS_DIR, embed_recording
from lazarus.plots import aligned_trajectories, category_summary, similarity_matrix
from lazarus.recording import build_recording, split_trials

# ZM_2241, 2020-01-30: 9 Beryl regions with >= 15 good units (MD, SMT, Eth, PO, VISa, LP, DG, PCN,
# CA1). The same mouse has MD/CA1/CP in other sessions (control 2) and VISa/LP/PO/DG/CA1 are IBL
# repeated-site regions recorded in many mice (control 3).
DEFAULT_EID = "ee40aece-cffd-4edb-a4b6-155f158c666a"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eid", default=DEFAULT_EID)
    ap.add_argument("--regions", nargs="*", help="Beryl acronyms (default: all with >= --min-units)")
    ap.add_argument("--min-units", type=int, default=15)
    ap.add_argument("--split", choices=["interleaved", "halves"], default="interleaved")
    ap.add_argument("--chunk-trials", type=int, default=10)
    ap.add_argument("--bin-size", type=float, default=0.02)
    ap.add_argument("--iters", type=int, default=CebraConfig.max_iterations)
    ap.add_argument("--dim", type=int, default=CebraConfig.output_dimension)
    ap.add_argument("--preprocess", default=CebraConfig.preprocess, choices=["none", "sqrt", "zscore"])
    ap.add_argument("--min-trials", type=int, default=5, help="min trials per condition per half")
    ap.add_argument("--no-ceiling", action="store_true", help="skip the second-seed ceiling model")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = CebraConfig(max_iterations=args.iters, output_dimension=args.dim, preprocess=args.preprocess)
    session = load_session(args.eid)
    regions = args.regions or session.regions(args.min_units).index.tolist()
    print(f"{session.subject} {session.date} {args.eid}: {len(session.trials)} trials "
          f"({session.mask.sum()} pass BWM mask); regions: "
          + ", ".join(f"{r} ({(session.units.Beryl == r).sum()})" for r in regions))

    out = RESULTS_DIR / "control1" / f"{args.eid}_{args.split}_cfg-{cfg.short_hash()}"
    out.mkdir(parents=True, exist_ok=True)
    splits = split_trials(len(session.trials), args.split, args.chunk_trials)

    trajs, ceilings = [], []
    for region in regions:
        recs = {name: build_recording(session, region, name, chunks, args.bin_size)
                for name, chunks in splits.items()}
        for name, rec in recs.items():
            t = embed_recording(rec, cfg, seed=0, verbose=args.verbose)
            trajs.append(t)
            print(f"  {rec.key}: {rec.n_units} units, {len(rec.X)} bins, {len(rec.trials)} trials, "
                  f"GoF {t.meta['goodness_of_fit_bits']:.2f} bits, {t.meta['fit_seconds']:.0f}s")
        if not args.no_ceiling:
            a0 = next(t for t in trajs if t.key == f"{recs['A'].key}/seed0")
            a1 = embed_recording(recs["A"], cfg, seed=1, verbose=args.verbose)
            c = compare_trajectories(a0, a1, min_trials=args.min_trials, cross_phase=False)
            ceilings.append(c.assign(region=region))

    # A vs B only (not A vs A of another region): pair_filter keeps cross-split pairs
    df = compare_all(trajs, pair_filter=lambda ma, mb: ma["split"] != mb["split"], min_trials=args.min_trials)
    # orient every row as (A, B)
    flip = df.split_a == "B"
    for col in ("key", "phase", "eid", "subject", "region", "split", "seed", "n_units"):
        df.loc[flip, [f"{col}_a", f"{col}_b"]] = df.loc[flip, [f"{col}_b", f"{col}_a"]].values
    df["category"] = label_comparison(df)
    df.to_csv(out / "pairwise.csv", index=False)
    ceiling = pd.concat(ceilings, ignore_index=True) if ceilings else pd.DataFrame()
    if len(ceiling):
        ceiling.to_csv(out / "seed_ceiling.csv", index=False)

    summary = df.groupby("category")[list(METRICS)].agg(["median", "mean", "count"])
    print("\n", summary.round(3).to_string())
    diag = df[df.category == "same region, same phase"]
    print("\nsame region, same phase (A vs B):")
    print(diag.pivot_table(index="region_a", columns="phase_a", values="procrustes").round(3).to_string())
    if len(ceiling):
        print("\nseed ceiling (A seed0 vs A seed1), procrustes:")
        print(ceiling.pivot_table(index="region", columns="phase_a", values="procrustes").round(3).to_string())

    # one-sided test per metric: same-region-same-phase vs all off-diagonal pairs
    from scipy.stats import mannwhitneyu
    stats = {}
    for m in METRICS:
        x, y = diag[m].dropna(), df.loc[df.category != "same region, same phase", m].dropna()
        stats[m] = {"median_diag": float(x.median()), "median_off": float(y.median()),
                    "mannwhitney_p": float(mannwhitneyu(x, y, alternative="greater").pvalue)}
    print("\n", pd.DataFrame(stats).T.round(4).to_string())
    (out / "summary.json").write_text(json.dumps({"eid": args.eid, "subject": session.subject,
                                                  "regions": regions, "config": cfg.__dict__,
                                                  "split": args.split, "tests": stats}, indent=2))

    title = f"Control 1 · {session.subject} {session.date} · {args.split} split"
    similarity_matrix(df, "procrustes", path=out / "matrix_procrustes.png", title=title)
    category_summary(df, METRICS, path=out / "categories.png", title=title, ceiling=ceiling)
    by_key = {t.key: t for t in trajs}
    for region in regions:
        a, b = by_key[f"{args.eid}/{region}/A/seed0"], by_key[f"{args.eid}/{region}/B/seed0"]
        aligned_trajectories(a, b, [p.name for p in PHASES], path=out / f"traj_{region}.png",
                             title=f"{region}", min_trials=args.min_trials)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
