"""
Diagram Analyzer - Extract structured information from ARIS flow diagrams using vision models.
"""

import base64
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class DiagramElement:
    """Single element from a flow diagram."""
    element_type: str  # 'event', 'activity', 'gateway', 'executor', 'it_system'
    code: Optional[str] = None  # Activity code like '010', '020'
    name: str = ""
    description: str = ""


@dataclass
class DiagramAnalysis:
    """Structured analysis of a flow diagram."""
    events: list[DiagramElement] = field(default_factory=list)
    activities: list[DiagramElement] = field(default_factory=list)
    gateways: list[DiagramElement] = field(default_factory=list)
    executors: list[DiagramElement] = field(default_factory=list)
    it_systems: list[DiagramElement] = field(default_factory=list)
    flow_description: str = ""
    raw_analysis: str = ""


class DiagramAnalyzer:
    """Analyzes ARIS flow diagrams using vision-capable LLMs."""
    
    ANALYSIS_PROMPT = """Analizza questo diagramma di flusso di processo ARIS e identifica TUTTI gli elementi.

IMPORTANTE: Rispondi ESATTAMENTE in questo formato, una riga per elemento:

EVENTI:
- [inizio] Nome dell'evento di inizio
- [fine] Nome dell'evento di fine
- [intermedio] Nome di eventuali eventi intermedi

ATTIVITA:
- [010] Nome attività
- [020] Nome attività
(elenca tutte le attività con il loro codice a 3 cifre)

GATEWAY:
- Descrizione del punto di decisione e le sue diramazioni

ESECUTORI:
- Nome unità organizzativa

SISTEMI_IT:
- Nome applicativo

FLUSSO:
Una breve descrizione della sequenza del processo.

Legenda per identificare gli elementi nel diagramma:
- EVENTI: forme esagonali viola/rosa (inizio, fine, intermedi)
- ATTIVITÀ: rettangoli verdi con codice numerico (010, 020, 030...)
- GATEWAY: simboli X gialli (punti di decisione)
- ESECUTORI: rettangoli gialli sul lato sinistro
- SISTEMI IT: rettangoli arancioni

Elenca TUTTI gli eventi che vedi, specialmente quelli di inizio e fine processo."""

    def __init__(self, provider: str = "google", api_key: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key
    
    def _image_to_base64(self, image_path: Path) -> str:
        """Convert image file to base64 string."""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')
    
    def _image_bytes_to_base64(self, image_bytes: bytes) -> str:
        """Convert image bytes to base64 string."""
        return base64.b64encode(image_bytes).decode('utf-8')
    
    def analyze(self, image_source: Path | bytes) -> DiagramAnalysis:
        """
        Analyze a flow diagram image.
        
        Args:
            image_source: Either a Path to an image file or raw image bytes
            
        Returns:
            DiagramAnalysis with extracted elements
        """
        if isinstance(image_source, Path):
            image_b64 = self._image_to_base64(image_source)
        else:
            image_b64 = self._image_bytes_to_base64(image_source)
        
        # Call vision model
        raw_response = self._call_vision_model(image_b64)
        
        # Parse response into structured format
        analysis = self._parse_response(raw_response)
        analysis.raw_analysis = raw_response
        
        return analysis
    
    def _call_vision_model(self, image_b64: str) -> str:
        """Call the vision-capable LLM with the image."""
        import os
        
        if self.provider == "google":
            return self._call_gemini_vision(image_b64)
        else:
            raise ValueError(f"Unsupported provider for vision: {self.provider}")
    
    def _call_gemini_vision(self, image_b64: str) -> str:
        """Call Gemini with vision capabilities."""
        import os
        
        try:
            import google.generativeai as genai
        except ImportError:
            raise ImportError("Install google-generativeai: pip install google-generativeai")
        
        api_key = self.api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("Google API key required")
        
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Create image part
        image_part = {
            "mime_type": "image/png",
            "data": image_b64
        }
        
        response = model.generate_content([self.ANALYSIS_PROMPT, image_part])
        return response.text
    
    def _parse_response(self, response: str) -> DiagramAnalysis:
        """Parse the LLM response into structured DiagramAnalysis."""
        import re
        
        analysis = DiagramAnalysis()
        
        current_section = None
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Detect section headers - must be standalone headers, not content lines
            # Section headers typically are just the section name (possibly with colon)
            # and don't start with list markers like - or •
            is_list_item = line.startswith('-') or line.startswith('•') or line.startswith('*') or \
                           line.startswith('–') or line.startswith('—') or line.startswith('−')
            
            if not is_list_item:
                line_upper = line.upper().replace(':', '').replace('*', '').strip()
                
                # Check for section headers - they should be short and match the section name closely
                if line_upper == 'EVENTI' or line_upper.startswith('EVENTI'):
                    current_section = 'events'
                    continue
                elif line_upper == 'ATTIVITA' or line_upper == 'ATTIVITÀ' or \
                     line_upper.startswith('ATTIVITA') and len(line_upper) < 20:
                    current_section = 'activities'
                    continue
                elif line_upper == 'GATEWAY' or line_upper == 'GATEWAYS' or \
                     line_upper.startswith('GATEWAY') and len(line_upper) < 20:
                    current_section = 'gateways'
                    continue
                elif line_upper == 'ESECUTORI' or line_upper.startswith('ESECUTORI'):
                    current_section = 'executors'
                    continue
                elif line_upper == 'SISTEMI_IT' or line_upper == 'SISTEMI IT' or \
                     line_upper.startswith('SISTEMI'):
                    current_section = 'it_systems'
                    continue
                elif line_upper == 'FLUSSO' or line_upper.startswith('FLUSSO'):
                    current_section = 'flow'
                    continue
            
            # Parse items based on current section
            # Handle various bullet/dash characters (including unicode dashes)
            if is_list_item:
                item_text = line.lstrip('-•*–—−').strip()
                
                if current_section == 'events' and item_text:
                    # Extract event type if present [inizio], [fine], etc.
                    match = re.match(r'\[([^\]]+)\]\s*(.+)', item_text)
                    if match:
                        event_type = match.group(1)
                        event_name = match.group(2)
                        element = DiagramElement(element_type='event', name=f"[{event_type}] {event_name}")
                    else:
                        element = DiagramElement(element_type='event', name=item_text)
                    analysis.events.append(element)
                    
                elif current_section == 'activities' and item_text:
                    # Try to extract code like [010] or 010
                    match = re.match(r'\[?(\d{3})\]?\s*(.+)', item_text)
                    if match:
                        element = DiagramElement(
                            element_type='activity',
                            code=match.group(1),
                            name=match.group(2).strip()
                        )
                    else:
                        element = DiagramElement(element_type='activity', name=item_text)
                    analysis.activities.append(element)
                    
                elif current_section == 'gateways' and item_text:
                    element = DiagramElement(element_type='gateway', name=item_text)
                    analysis.gateways.append(element)
                    
                elif current_section == 'executors' and item_text:
                    element = DiagramElement(element_type='executor', name=item_text)
                    analysis.executors.append(element)
                    
                elif current_section == 'it_systems' and item_text:
                    element = DiagramElement(element_type='it_system', name=item_text)
                    analysis.it_systems.append(element)
            
            elif current_section == 'flow' and line:
                analysis.flow_description += line + " "
        
        analysis.flow_description = analysis.flow_description.strip()
        return analysis


def analyze_diagram(image_source: Path | bytes, provider: str = "google") -> DiagramAnalysis:
    """Convenience function to analyze a diagram."""
    analyzer = DiagramAnalyzer(provider=provider)
    return analyzer.analyze(image_source)