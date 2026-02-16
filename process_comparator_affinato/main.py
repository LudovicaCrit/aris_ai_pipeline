#!/usr/bin/env python3
"""
Process Comparator - Main Entry Point

Compares As-Is and To-Be process documents and generates analysis reports.

Usage:
    python main.py <as_is_file> <to_be_file> [--output <output_path>] [--provider <provider>]

Example:
    python main.py processo_as_is.doc processo_to_be.doc --output report.docx
    
    # With specific provider
    python main.py file1.doc file2.doc --provider openai
    
    # Just print analysis (no Word output)
    python main.py file1.doc file2.doc --no-docx
"""

import argparse
import sys
import json
from pathlib import Path

# Load .env file
from dotenv import load_dotenv
load_dotenv()

from core import parse_aris_document, compare_processes, calculate_metrics
from core.document_parser import parse_document_with_track_changes
from core.diff_engine import DiffEngine
from core.metrics import MetricsCalculator
from agent import create_agent
from output import generate_report
from config import Config, load_config_from_env


def main():
    parser = argparse.ArgumentParser(
        description="Compare As-Is and To-Be process documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic usage (two files)
    python main.py as_is.doc to_be.doc
    
    # Single file with Track Changes (auto-detected)
    python main.py document_with_changes.doc
    
    # Specify output file
    python main.py as_is.doc to_be.doc -o comparison_report.docx
    
    # Use different LLM provider
    python main.py as_is.doc to_be.doc --provider openai
    
    # Just show metrics (no LLM analysis)
    python main.py as_is.doc to_be.doc --metrics-only
    
    # Print analysis to console (no Word output)
    python main.py as_is.doc to_be.doc --no-docx
        """
    )
    
    parser.add_argument("as_is_file", type=Path, help="Path to As-Is document (or single file with Track Changes)")
    parser.add_argument("to_be_file", type=Path, nargs='?', default=None, help="Path to To-Be document (optional if using Track Changes)")
    parser.add_argument("-o", "--output", type=Path, help="Output Word file path")
    parser.add_argument("--provider", choices=["google", "openai", "anthropic"],
                        default="google", help="LLM provider (default: google)")
    parser.add_argument("--model", type=str, help="Specific model to use")
    parser.add_argument("--api-key", type=str, help="API key (or use env var)")
    parser.add_argument("--no-docx", action="store_true", help="Don't generate Word doc, print to console")
    parser.add_argument("--metrics-only", action="store_true", help="Only show metrics, skip LLM analysis")
    parser.add_argument("--json", action="store_true", help="Output metrics and diff as JSON")
    parser.add_argument("--no-diagram", action="store_true", help="Skip diagram extraction and vision analysis")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Validate input files
    if not args.as_is_file.exists():
        print(f"Error: File not found: {args.as_is_file}", file=sys.stderr)
        sys.exit(1)
    if args.to_be_file and not args.to_be_file.exists():
        print(f"Error: To-Be file not found: {args.to_be_file}", file=sys.stderr)
        sys.exit(1)
    
    # Load configuration
    config = load_config_from_env()
    config.llm_provider = args.provider
    if args.model:
        config.llm_model = args.model
    if args.api_key:
        if args.provider == "google":
            config.google_api_key = args.api_key
        elif args.provider == "openai":
            config.openai_api_key = args.api_key
        elif args.provider == "anthropic":
            config.anthropic_api_key = args.api_key
    
    try:
        # Step 1: Parse documents
        # Check if single file mode (Track Changes) or two file mode
        if args.to_be_file is None:
            # Single file mode - try to extract Track Changes
            if args.verbose:
                print(f"Single file mode - checking for Track Changes: {args.as_is_file}")
            
            as_is_doc, to_be_doc, has_track_changes = parse_document_with_track_changes(args.as_is_file)
            
            if not has_track_changes:
                print(f"Error: No Track Changes detected in {args.as_is_file}", file=sys.stderr)
                print("For single file mode, the document must contain Track Changes.", file=sys.stderr)
                print("Otherwise, provide two files: python main.py as_is.doc to_be.doc", file=sys.stderr)
                sys.exit(1)
            
            if args.verbose:
                print(f"Track Changes detected!")
                print(f"As-Is (original): {as_is_doc.process_name} ({len(as_is_doc.activities)} activities)")
                print(f"To-Be (modified): {to_be_doc.process_name} ({len(to_be_doc.activities)} activities)")
        else:
            # Two file mode - parse separately
            if args.verbose:
                print(f"Parsing As-Is document: {args.as_is_file}")
            as_is_doc = parse_aris_document(args.as_is_file)
            
            if args.verbose:
                print(f"Parsing To-Be document: {args.to_be_file}")
            to_be_doc = parse_aris_document(args.to_be_file)
            
            if args.verbose:
                print(f"As-Is: {as_is_doc.process_name} ({len(as_is_doc.activities)} activities)")
                print(f"To-Be: {to_be_doc.process_name} ({len(to_be_doc.activities)} activities)")
        
        # Step 2: Compare documents
        if args.verbose:
            print("Comparing documents...")
        
        diff_engine = DiffEngine()
        diff = diff_engine.compare(as_is_doc, to_be_doc)
        
        # Step 3: Calculate metrics
        if args.verbose:
            print("Calculating metrics...")
        
        metrics_calculator = MetricsCalculator()
        metrics = metrics_calculator.calculate(diff)
        
        # Convert to dictionaries
        diff_data = diff.to_dict()
        metrics_data = metrics.to_dict()
        
        # JSON output mode
        if args.json:
            output = {
                "diff": diff_data,
                "metrics": metrics_data
            }
            print(json.dumps(output, indent=2, ensure_ascii=False))
            return
        
        # Metrics-only mode
        if args.metrics_only:
            print("\n" + "="*60)
            print("PROCESS CHANGE METRICS")
            print("="*60)
            print(f"\nAs-Is: {as_is_doc.process_name}")
            print(f"To-Be: {to_be_doc.process_name}")
            print("\n" + "-"*60)
            print(f"Volatility Index: {metrics.volatility_percentage:.1f}% ({metrics.volatility_level})")
            print(f"  - Tasks added: {metrics.tasks_added}")
            print(f"  - Tasks removed: {metrics.tasks_removed}")
            print(f"\nHandover Delta: {metrics.handover_delta:+d}")
            print(f"  - As-Is handovers: {metrics.handover_as_is}")
            print(f"  - To-Be handovers: {metrics.handover_to_be}")
            print(f"\nAutomation Rate: {metrics.automation_as_is_rate*100:.1f}% -> {metrics.automation_to_be_rate*100:.1f}%")
            print("\n" + "-"*60)
            print(f"PROCESS CHANGE SCORE: {metrics.pcs:.2f} ({metrics.pcs_level})")
            if metrics.requires_audit:
                print("HIGH IMPACT - Audit review recommended")
            print("="*60 + "\n")
            return
        
        # Step 4: Validate config for LLM
        errors = config.validate()
        if errors:
            print("Configuration errors:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(1)
        
        # Step 5: Generate LLM analysis
        if args.verbose:
            print(f"Generating analysis using {config.llm_provider}...")
        
        # Step 5a: Extract and analyze diagram (if available)
        diagram_analysis = None
        if not args.no_diagram and as_is_doc.has_diagram():
            if args.verbose:
                print("Analyzing process diagram with vision...")
            try:
                from core.diagram_analyzer import DiagramAnalyzer
                analyzer = DiagramAnalyzer(provider="google")
                
                # Analyze the As-Is diagram (it shows the baseline flow)
                if as_is_doc.diagram_image:
                    analysis = analyzer.analyze(as_is_doc.diagram_image)
                    diagram_analysis = {
                        "events": [e.name for e in analysis.events],
                        "gateways": [g.name for g in analysis.gateways],
                        "flow_description": analysis.flow_description,
                    }
                    if args.verbose:
                        print(f"  Found {len(analysis.events)} events, {len(analysis.gateways)} gateways")
            except Exception as e:
                if args.verbose:
                    print(f"  Warning: Diagram analysis failed: {e}")
                diagram_analysis = None
        
        agent = create_agent(
            provider=config.llm_provider,
            model=config.llm_model,
            api_key=config.get_api_key()
        )
        
        analysis_text = agent.analyze(
            diff_data=diff_data,
            metrics_data=metrics_data,
            as_is_name=as_is_doc.process_name,
            to_be_name=to_be_doc.process_name,
            diagram_analysis=diagram_analysis
        )
        
        # No-docx mode: print to console
        if args.no_docx:
            print("\n" + "="*60)
            print("PROCESS COMPARISON ANALYSIS")
            print("="*60 + "\n")
            print(analysis_text)
            return
        
        # Step 6: Generate Word report
        if args.verbose:
            print("Generating Word report...")
        
        output_path = args.output
        if output_path is None:
            output_path = Path.cwd() / f"comparison_{as_is_doc.process_code}_report.docx"
        
        report_path = generate_report(
            analysis_text=analysis_text,
            as_is_name=as_is_doc.process_name,
            to_be_name=to_be_doc.process_name,
            metrics=metrics_data,
            output_dir=output_path.parent,
            filename=output_path.name
        )
        
        print(f"\n✅ Report generated: {report_path}")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()