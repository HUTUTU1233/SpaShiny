# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import gc
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from metabolite_annotator import annotate_h5ad  # noqa: E402


def str_to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def setup_logging(out_path: Path):
    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = out_path.with_name("metabolite_annotation.log")

    logger = logging.getLogger("metabolite_annotation")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger, log_path


def write_failure_summary(args, log_path: Path, exc: Exception) -> None:
    summary_path = Path(args.summary_json).resolve()
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "success": False,
        "annotation_type": "putative metabolite annotation",
        "message": str(exc),
        "error_type": type(exc).__name__,
        "traceback": traceback.format_exc(),
        "input_h5ad": str(Path(args.h5ad).resolve()) if args.h5ad else "",
        "annotation_table": str(Path(args.anno).resolve()) if args.anno else "",
        "output_h5ad": str(Path(args.out).resolve()) if args.out else "",
        "all_candidates_csv": str(Path(args.all_candidates_csv).resolve()) if args.all_candidates_csv else "",
        "summary_json": str(summary_path),
        "log_path": str(log_path),
        "mode": args.mode,
        "tolerance_ppm": args.tolerance_ppm,
        "top_n": args.top_n,
        "only_sm_features": str_to_bool(args.only_sm_features),
    }
    summary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run putative metabolite annotation for SpaShiny h5ad files."
    )
    parser.add_argument("--h5ad", required=True, help="Input spatial metabolomics or joint omics h5ad file.")
    parser.add_argument("--anno", required=True, help="Metabolite annotation table (.csv/.tsv/.xlsx).")
    parser.add_argument("--out", required=True, help="Output annotated h5ad path.")
    parser.add_argument(
        "--mode",
        default="auto",
        choices=["auto", "feature_id", "observed_mz", "exact_mass"],
        help="Annotation mode.",
    )
    parser.add_argument("--tolerance_ppm", type=float, default=5.0, help="m/z tolerance in ppm.")
    parser.add_argument("--top_n", type=int, default=1, help="Top N candidate rank threshold.")
    parser.add_argument("--summary_json", required=True, help="Output summary JSON path.")
    parser.add_argument("--all_candidates_csv", required=True, help="Output candidate annotation CSV path.")
    parser.add_argument(
        "--only_sm_features",
        default="true",
        help="Whether to annotate only SM/metabolite features when var type metadata is available.",
    )
    parser.add_argument("--var_mz_col", default="", help="Optional AnnData var m/z column override.")
    parser.add_argument("--anno_mz_col", default="", help="Optional annotation table m/z column override.")
    parser.add_argument("--polarity_col", default="", help="Optional annotation table polarity/type column override.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    logger, log_path = setup_logging(Path(args.out))

    try:
        logger.info("Starting putative metabolite annotation.")
        logger.info("Input h5ad: %s", args.h5ad)
        logger.info("Annotation table: %s", args.anno)
        logger.info("Output h5ad: %s", args.out)
        logger.info(
            "Mode=%s, tolerance_ppm=%s, top_n=%s, only_sm_features=%s",
            args.mode,
            args.tolerance_ppm,
            args.top_n,
            str_to_bool(args.only_sm_features),
        )

        summary = annotate_h5ad(
            h5ad_path=args.h5ad,
            annotation_path=args.anno,
            output_h5ad=args.out,
            mode=args.mode,
            tolerance_ppm=args.tolerance_ppm,
            top_n=args.top_n,
            only_sm_features=str_to_bool(args.only_sm_features),
            var_mz_col=args.var_mz_col,
            anno_mz_col=args.anno_mz_col,
            polarity_col=args.polarity_col,
            summary_json=args.summary_json,
            all_candidates_csv=args.all_candidates_csv,
            logger=logger,
        )
        summary["log_path"] = str(log_path)
        Path(args.summary_json).write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Putative metabolite annotation completed successfully.")
        return 0

    except Exception as exc:
        logger.error("Putative metabolite annotation failed: %s", exc)
        logger.error(traceback.format_exc())
        write_failure_summary(args, log_path, exc)
        return 1

    finally:
        gc.collect()


if __name__ == "__main__":
    raise SystemExit(main())
