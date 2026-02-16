#!/usr/bin/env python3
"""
Async Batch Processor - Parallel processing of multiple document pairs.

Usage: 
    python batch_async.py --as-is-dir ./as_is --to-be-dir ./to_be [--output-dir ./output]
    python batch_async.py --as-is-dir ./as_is --to-be-dir ./to_be --metrics-only

Features:
- Parallel LLM calls using asyncio
- Rate limiting to avoid API throttling
- Progress tracking
- JSON + Word output generation
"""

import argparse
import asyncio
import sys
import json
import re
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

# Load .env file
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from core import parse_aris_document
from core.diff_engine import DiffEngine, ProcessDiff
from core.metrics import MetricsCalculator, ProcessMetrics
from config import load_config_from_env


@dataclass
class ComparisonResult:
    """Result of a single comparison."""
    name: str
    as_is_path: Path
    to_be_path: Path
    diff: ProcessDiff
    metrics: ProcessMetrics
    analysis: Optional[str] = None
    error: Optional[str] = None


def find_pairs(as_is_dir: Path, to_be_dir: Path) -> list[tuple[Path, Path, str]]:
    """Find matching document pairs by normalized name."""
    valid_ext = {'.doc', '.docx', '.txt'}
    as_is_files = [f for f in as_is_dir.glob("*.*") if f.suffix.lower() in valid_ext]
    to_be_files = [f for f in to_be_dir.glob("*.*") if f.suffix.lower() in valid_ext]
    
    def normalize(name: str) -> str:
        name = Path(name).stem.lower()
        for suf in ['_as_is', '_as-is', '_to_be', '_to-be', '_anomalie']:
            name = name.replace(suf, '')
        return re.sub(r'_scenario\d+[a-z]?', '', name)
    
    pairs = []
    for tb in to_be_files:
        for ai in as_is_files:
            if normalize(ai.name) == normalize(tb.name):
                pairs.append((ai, tb, tb.stem))
                break
    return pairs


def process_pair_sync(as_is_path: Path, to_be_path: Path) -> tuple[ProcessDiff, ProcessMetrics]:
    """Process a document pair (synchronous - parsing and metrics only)."""
    as_is = parse_aris_document(as_is_path)
    to_be = parse_aris_document(to_be_path)
    diff = DiffEngine().compare(as_is, to_be)
    metrics = MetricsCalculator().calculate(diff)
    return diff, metrics


async def analyze_with_llm(
    agent,
    diff: ProcessDiff,
    metrics: ProcessMetrics,
    semaphore: asyncio.Semaphore
) -> str:
    """Run LLM analysis with rate limiting."""
    async with semaphore:
        return await agent.analyze_async(
            diff_data=diff.to_dict(),
            metrics_data=metrics.to_dict(),
            as_is_name=diff.as_is_doc.process_name,
            to_be_name=diff.to_be_doc.process_name
        )


async def process_batch_async(
    pairs: list[tuple[Path, Path, str]],
    include_llm: bool = True,
    max_concurrent: int = 5,
    progress_callback=None
) -> list[ComparisonResult]:
    """
    Process multiple document pairs in parallel.
    
    Args:
        pairs: List of (as_is_path, to_be_path, name) tuples
        include_llm: Whether to include LLM analysis
        max_concurrent: Max concurrent LLM calls (rate limiting)
        progress_callback: Optional callback(current, total, name) for progress
    
    Returns:
        List of ComparisonResult objects
    """
    results = []
    
    # Step 1: Parse all documents and calculate metrics (fast, synchronous)
    print(f"\n📊 Fase 1: Parsing e calcolo metriche ({len(pairs)} documenti)...")
    
    for i, (as_is_path, to_be_path, name) in enumerate(pairs, 1):
        try:
            diff, metrics = process_pair_sync(as_is_path, to_be_path)
            results.append(ComparisonResult(
                name=name,
                as_is_path=as_is_path,
                to_be_path=to_be_path,
                diff=diff,
                metrics=metrics
            ))
            print(f"  ✓ [{i}/{len(pairs)}] {name}")
        except Exception as e:
            results.append(ComparisonResult(
                name=name,
                as_is_path=as_is_path,
                to_be_path=to_be_path,
                diff=None,
                metrics=None,
                error=str(e)
            ))
            print(f"  ✗ [{i}/{len(pairs)}] {name}: {e}")
    
    if not include_llm:
        return results
    
    # Step 2: LLM analysis (parallel with rate limiting)
    valid_results = [r for r in results if r.error is None]
    
    if not valid_results:
        print("\n⚠️  Nessun documento valido per l'analisi LLM.")
        return results
    
    print(f"\n🤖 Fase 2: Analisi LLM ({len(valid_results)} documenti, max {max_concurrent} paralleli)...")
    
    # Create agent
    config = load_config_from_env()
    from agent import create_agent
    agent = create_agent(
        provider=config.llm_provider,
        api_key=config.get_api_key()
    )
    
    # Semaphore for rate limiting
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def analyze_one(result: ComparisonResult, index: int) -> None:
        try:
            analysis = await analyze_with_llm(
                agent, result.diff, result.metrics, semaphore
            )
            result.analysis = analysis
            print(f"  ✓ [{index}/{len(valid_results)}] {result.name}")
        except Exception as e:
            result.error = f"LLM error: {e}"
            print(f"  ✗ [{index}/{len(valid_results)}] {result.name}: {e}")
    
    # Run all LLM calls in parallel (with semaphore limiting)
    tasks = [
        analyze_one(result, i)
        for i, result in enumerate(valid_results, 1)
    ]
    await asyncio.gather(*tasks)
    
    return results


def save_results(results: list[ComparisonResult], output_dir: Path):
    """Save all results to JSON and Word files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Summary JSON
    summary = []
    for r in results:
        entry = {
            "name": r.name,
            "as_is": str(r.as_is_path),
            "to_be": str(r.to_be_path),
        }
        if r.error:
            entry["error"] = r.error
        else:
            entry["metrics"] = r.metrics.to_dict()
            entry["diff_summary"] = {
                "added": len(r.diff.activities_added),
                "removed": len(r.diff.activities_removed),
                "modified": len(r.diff.activities_modified),
            }
            entry["has_analysis"] = r.analysis is not None
        summary.append(entry)
    
    summary_path = output_dir / f"batch_summary_{datetime.now():%Y%m%d_%H%M%S}.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n💾 Riepilogo: {summary_path}")
    
    # Individual Word reports (only for results with analysis)
    from output import ReportGenerator
    report_gen = ReportGenerator()
    
    reports_created = 0
    for r in results:
        if r.analysis and r.error is None:
            try:
                report_path = output_dir / f"{r.name}_report.docx"
                report_gen.generate(
                    analysis_text=r.analysis,
                    as_is_name=r.diff.as_is_doc.process_name,
                    to_be_name=r.diff.to_be_doc.process_name,
                    metrics=r.metrics.to_dict(),
                    filename=f"{r.name}_report.docx"
                )
                reports_created += 1
            except Exception as e:
                print(f"  Errore report {r.name}: {e}")
    
    if reports_created:
        print(f"Report Word generati: {reports_created}")


def print_summary(results: list[ComparisonResult]):
    """Print summary table."""
    print(f"\n{'='*70}")
    print(f"{'RIEPILOGO':^70}")
    print(f"{'='*70}")
    print(f"{'Nome':<35} {'PCS':>8} {'Volat.':>8} {'HO Δ':>6} {'Stato':>10}")
    print(f"{'-'*70}")
    
    for r in results:
        if r.error:
            print(f"{r.name[:35]:<35} {'-':>8} {'-':>8} {'-':>6} {'❌ Errore':>10}")
        else:
            pcs = f"{r.metrics.pcs:.2f}"
            vol = f"{r.metrics.volatility_percentage:.0f}%"
            ho = f"{r.metrics.handover_delta:+d}"
            status = "⚠️ Audit" if r.metrics.requires_audit else "✓ OK"
            print(f"{r.name[:35]:<35} {pcs:>8} {vol:>8} {ho:>6} {status:>10}")
    
    print(f"{'='*70}")
    
    # Stats
    total = len(results)
    errors = sum(1 for r in results if r.error)
    audits = sum(1 for r in results if not r.error and r.metrics.requires_audit)
    
    print(f"\nTotale: {total} | Errori: {errors} | Richiedono audit: {audits}")


async def main_async():
    parser = argparse.ArgumentParser(
        description="Async batch processor for process comparison"
    )
    parser.add_argument("--as-is-dir", type=Path, required=True,
                        help="Directory with As-Is documents")
    parser.add_argument("--to-be-dir", type=Path, required=True,
                        help="Directory with To-Be documents")
    parser.add_argument("--output-dir", type=Path, default=Path("./output"),
                        help="Output directory for reports")
    parser.add_argument("--metrics-only", action="store_true",
                        help="Skip LLM analysis, only calculate metrics")
    parser.add_argument("--max-concurrent", type=int, default=3,
                        help="Max concurrent LLM calls (default: 3)")
    
    args = parser.parse_args()
    
    # Validate directories
    if not args.as_is_dir.exists():
        print(f"❌ Directory As-Is non trovata: {args.as_is_dir}")
        sys.exit(1)
    if not args.to_be_dir.exists():
        print(f"❌ Directory To-Be non trovata: {args.to_be_dir}")
        sys.exit(1)
    
    # Find pairs
    pairs = find_pairs(args.as_is_dir, args.to_be_dir)
    if not pairs:
        print("❌ Nessuna coppia di documenti trovata.")
        sys.exit(1)
    
    print(f"\n{'='*50}")
    print(f"PROCESS COMPARATOR - BATCH ASYNC")
    print(f"{'='*50}")
    print(f"As-Is: {args.as_is_dir}")
    print(f"To-Be: {args.to_be_dir}")
    print(f"Output: {args.output_dir}")
    print(f"Coppie trovate: {len(pairs)}")
    print(f"Modalità: {'Solo metriche' if args.metrics_only else 'Completa (con LLM)'}")
    
    # Process
    start_time = datetime.now()
    
    results = await process_batch_async(
        pairs=pairs,
        include_llm=not args.metrics_only,
        max_concurrent=args.max_concurrent
    )
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # Output
    print_summary(results)
    
    if not args.metrics_only:
        save_results(results, args.output_dir)
    
    print(f"\n⏱️  Tempo totale: {elapsed:.1f} secondi")
    
    if len(pairs) > 1 and not args.metrics_only:
        per_doc = elapsed / len(pairs)
        sequential_estimate = len(pairs) * 4  # ~4 sec per LLM call
        print(f"   Media per documento: {per_doc:.1f}s (sequenziale stimato: ~{sequential_estimate}s)")


def main():
    """Entry point."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()