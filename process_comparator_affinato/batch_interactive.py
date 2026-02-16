#!/usr/bin/env python3
"""
Interactive Batch Processor - Step-by-step As-Is/To-Be comparison.

Usage: python batch_interactive.py [--as-is-dir DIR] [--to-be-dir DIR]
"""

import argparse
import sys
import json
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from core import parse_aris_document
from core.diff_engine import DiffEngine
from core.metrics import MetricsCalculator


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


def print_metrics(m):
    """Print metrics summary."""
    print(f"\n--- METRICHE ---")
    print(f"Volatility:  {m.volatility_percentage:5.1f}% ({m.volatility_level})")
    print(f"Handover Δ:  {m.handover_delta:+d} ({m.handover_as_is} → {m.handover_to_be})")
    print(f"Automation:  {m.automation_as_is_rate*100:.1f}% → {m.automation_to_be_rate*100:.1f}%")
    print(f"PCS:         {m.pcs:.2f} ({m.pcs_level})")
    if m.requires_audit:
        print("⚠️  RICHIEDE AUDIT")


def print_changes(diff):
    """Print detected changes."""
    print(f"\n--- MODIFICHE ---")
    
    if diff.process_name_changed:
        print(f"Nome: {diff.old_process_name} → {diff.new_process_name}")
    
    if diff.activities_added:
        print(f"\n+ Aggiunte ({len(diff.activities_added)}):")
        for c in diff.activities_added:
            print(f"  [{c.code}] {c.to_be.title[:50]}")
    
    if diff.activities_removed:
        print(f"\n- Rimosse ({len(diff.activities_removed)}):")
        for c in diff.activities_removed:
            print(f"  [{c.code}] {c.as_is.title[:50]}")
    
    if diff.activities_modified:
        print(f"\n~ Modificate ({len(diff.activities_modified)}):")
        for c in diff.activities_modified:
            changes = []
            if c.title_changed: changes.append("titolo")
            if c.description_changed: changes.append("descrizione")
            if c.executor_changed: changes.append("esecutore")
            if c.it_system_changed: changes.append("sistema IT")
            print(f"  [{c.code}] {', '.join(changes)}")
            if c.executor_changed:
                print(f"       {c.old_executor} → {c.new_executor}")
    
    if diff.activities_reordered:
        print(f"\n↔ Riordinate ({len(diff.activities_reordered)}):")
        for code, old, new in diff.activities_reordered:
            print(f"  [{code}] pos {old+1} → {new+1}")
    
    new_exec = diff.get_new_executors()
    if new_exec:
        print(f"\nNuovi esecutori: {', '.join(new_exec)}")
    
    if not any([diff.process_name_changed, diff.activities_added, 
                diff.activities_removed, diff.activities_modified]):
        print("Nessuna modifica rilevata.")


def process_pair(as_is_path: Path, to_be_path: Path):
    """Process a document pair and return results."""
    as_is = parse_aris_document(as_is_path)
    to_be = parse_aris_document(to_be_path)
    diff = DiffEngine().compare(as_is, to_be)
    metrics = MetricsCalculator().calculate(diff)
    return as_is, to_be, diff, metrics


def main():
    parser = argparse.ArgumentParser(description="Interactive batch processor")
    parser.add_argument("--as-is-dir", type=Path, default=Path("./as_is"))
    parser.add_argument("--to-be-dir", type=Path, default=Path("./to_be"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    
    if not args.as_is_dir.exists() or not args.to_be_dir.exists():
        print(f"❌ Directory non trovate: {args.as_is_dir}, {args.to_be_dir}")
        sys.exit(1)
    
    pairs = find_pairs(args.as_is_dir, args.to_be_dir)
    if not pairs:
        print("❌ Nessuna coppia trovata.")
        sys.exit(1)
    
    results = []
    
    print(f"\n{'='*50}")
    print(f"PROCESS COMPARATOR")
    print(f"{'='*50}")
    print(f"As-Is: {args.as_is_dir}")
    print(f"To-Be: {args.to_be_dir}")
    print(f"\nCoppie trovate: {len(pairs)}")
    for i, (_, _, name) in enumerate(pairs, 1):
        print(f"  {i}. {name}")
    
    while True:
        print(f"\n[numero] Analizza | [a] Tutte | [s] Salva | [q] Esci")
        choice = input("Scelta: ").strip().lower()
        
        if choice == 'q':
            break
        
        elif choice == 's':
            if results:
                out = args.output or Path(f"results_{datetime.now():%Y%m%d_%H%M%S}.json")
                data = [{"name": n, "diff": d.to_dict(), "metrics": m.to_dict()} 
                        for n, _, _, d, m in results]
                out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
                print(f"💾 Salvato: {out}")
            else:
                print("Nulla da salvare.")
        
        elif choice == 'a':
            for i, (ai, tb, name) in enumerate(pairs, 1):
                print(f"\n{'='*50}")
                print(f"[{i}/{len(pairs)}] {name}")
                print(f"{'='*50}")
                try:
                    as_is, to_be, diff, metrics = process_pair(ai, tb)
                    print(f"As-Is: {as_is.process_name} ({len(as_is.activities)} att.)")
                    print(f"To-Be: {to_be.process_name} ({len(to_be.activities)} att.)")
                    print_changes(diff)
                    print_metrics(metrics)
                    results.append((name, as_is, to_be, diff, metrics))
                except Exception as e:
                    print(f"❌ Errore: {e}")
                
                if i < len(pairs):
                    if input("\n[Invio] continua | [q] stop: ").strip().lower() == 'q':
                        break
        
        elif choice.isdigit() and 0 < int(choice) <= len(pairs):
            ai, tb, name = pairs[int(choice) - 1]
            print(f"\n{'='*50}")
            print(f"ANALISI: {name}")
            print(f"{'='*50}")
            try:
                as_is, to_be, diff, metrics = process_pair(ai, tb)
                print(f"As-Is: {as_is.process_name} ({len(as_is.activities)} att.)")
                print(f"To-Be: {to_be.process_name} ({len(to_be.activities)} att.)")
                print_changes(diff)
                print_metrics(metrics)
                results.append((name, as_is, to_be, diff, metrics))
            except Exception as e:
                print(f"❌ Errore: {e}")
        else:
            print("Opzione non valida.")


if __name__ == "__main__":
    main()