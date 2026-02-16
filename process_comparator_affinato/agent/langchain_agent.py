"""
LangChain Agent for Process Comparison Analysis

Supports multiple LLM providers through LangChain's abstraction.
Initial implementation targets Google AI (Gemini).
"""

import os
from pathlib import Path
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


class ProcessAnalysisAgent:
    """
    Agent that analyzes process differences using an LLM.
    
    The agent receives structured diff data and metrics (calculated by Python),
    and produces qualitative analysis in Italian.
    """
    
    def __init__(
        self,
        provider: str = "google",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        prompts_dir: Optional[Path] = None
    ):
        """
        Initialize the agent.
        
        Args:
            provider: LLM provider ("google", "openai", "anthropic")
            model: Model name (defaults based on provider)
            api_key: API key (or set via environment variable)
            prompts_dir: Directory containing prompt files
        """
        self.provider = provider
        self.model_name = model or self._default_model(provider)
        self.api_key = api_key
        
        # Load prompts
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent / "prompts"
        self.prompts_dir = Path(prompts_dir)
        
        self.system_prompt = self._load_prompt("system_prompt.md")
        self.analysis_instructions = self._load_prompt("analysis_instructions.md")
        
        # Initialize LLM
        self.llm = self._create_llm()
        
        # Create chain
        self.chain = self._create_chain()
    
    def _default_model(self, provider: str) -> str:
        """Get default model for provider."""
        defaults = {
            "google": "gemini-2.5-flash",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-sonnet-20241022",
        }
        return defaults.get(provider, "gemini-2.5-flash")
    
    def _load_prompt(self, filename: str) -> str:
        """Load a prompt file."""
        prompt_path = self.prompts_dir / filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")
    
    def _create_llm(self):
        """Create LLM instance based on provider."""
        if self.provider == "google":
            return self._create_google_llm()
        elif self.provider == "openai":
            return self._create_openai_llm()
        elif self.provider == "anthropic":
            return self._create_anthropic_llm()
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _create_google_llm(self):
        """Create Google Gemini LLM."""
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError:
            raise ImportError(
                "Install langchain-google-genai: pip install langchain-google-genai"
            )
        
        api_key = self.api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "Google API key required. Set GOOGLE_API_KEY env var or pass api_key parameter."
            )
        
        return ChatGoogleGenerativeAI(
            model=self.model_name,
            google_api_key=api_key,
            temperature=0.3,
            convert_system_message_to_human=True,
        )
    
    def _create_openai_llm(self):
        """Create OpenAI LLM."""
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            raise ImportError(
                "Install langchain-openai: pip install langchain-openai"
            )
        
        api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OpenAI API key required. Set OPENAI_API_KEY env var or pass api_key parameter."
            )
        
        return ChatOpenAI(
            model=self.model_name,
            api_key=api_key,
            temperature=0.3,
        )
    
    def _create_anthropic_llm(self):
        """Create Anthropic LLM."""
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError:
            raise ImportError(
                "Install langchain-anthropic: pip install langchain-anthropic"
            )
        
        api_key = self.api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY env var or pass api_key parameter."
            )
        
        return ChatAnthropic(
            model=self.model_name,
            api_key=api_key,
            temperature=0.3,
        )
    
    def _create_chain(self):
        """Create the LangChain processing chain."""
        
        # Build the prompt template
        template = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("human", """
{analysis_instructions}

---

## Process Information

**As-Is Process:** {as_is_name}
**To-Be Process:** {to_be_name}

---

## Structured Diff Data

{diff_data}

---

## Pre-Calculated Metrics

{metrics_data}

{diagram_section}

---

## Your Task

Based on the structured diff data and metrics provided above, produce a complete analysis report following the structure in the instructions. Write in Italian.

Remember:
- Do NOT recalculate the metrics - use the values provided
- Focus on interpretation and business impact
- Be concise but thorough
- Skip sections that have no relevant content
- If diagram analysis is provided, USE the events to enrich your descriptions of activities
"""),
        ])
        
        # Create the chain
        chain = template | self.llm | StrOutputParser()
        
        return chain
    
    def analyze(
        self,
        diff_data: dict,
        metrics_data: dict,
        as_is_name: str,
        to_be_name: str,
        diagram_analysis: dict = None
    ) -> str:
        """
        Analyze process differences and produce a report (synchronous).
        
        Args:
            diff_data: Dictionary from ProcessDiff.to_dict()
            metrics_data: Dictionary from ProcessMetrics.to_dict()
            as_is_name: Name of the As-Is process
            to_be_name: Name of the To-Be process
            diagram_analysis: Optional dictionary with diagram events/gateways/flow
            
        Returns:
            Analysis report as a string (markdown formatted)
        """
        import json
        
        # Build diagram section if available
        diagram_section = ""
        if diagram_analysis:
            events_list = diagram_analysis.get("events", [])
            gateways_list = diagram_analysis.get("gateways", [])
            
            diagram_section = """
---

## Diagram Analysis (from flow diagram image)

⚠️ **YOU MUST USE THESE EVENTS** in your activity descriptions in section 3.1.
For each activity, check if an event triggers it or follows it.

**Events identified ({num_events} found):**
{events}

**Gateways (decision points):**
{gateways}

**Flow description:**
{flow}

EXAMPLE of how to use events:
"[055] Notifica esito - Attivata dall'evento 'Valutazione completata', questa attività invia..."
""".format(
                num_events=len(events_list),
                events="\n".join(f"- {e}" for e in events_list) or "None identified",
                gateways="\n".join(f"- {g}" for g in gateways_list) or "None identified",
                flow=diagram_analysis.get("flow_description", "Not available")
            )
        
        result = self.chain.invoke({
            "analysis_instructions": self.analysis_instructions,
            "diff_data": json.dumps(diff_data, indent=2, ensure_ascii=False),
            "metrics_data": json.dumps(metrics_data, indent=2, ensure_ascii=False),
            "as_is_name": as_is_name,
            "to_be_name": to_be_name,
            "diagram_section": diagram_section,
        })
        
        return result
    
    async def analyze_async(
        self,
        diff_data: dict,
        metrics_data: dict,
        as_is_name: str,
        to_be_name: str
    ) -> str:
        """
        Analyze process differences and produce a report (asynchronous).
        
        Use this method for batch processing to parallelize LLM calls.
        
        Args:
            diff_data: Dictionary from ProcessDiff.to_dict()
            metrics_data: Dictionary from ProcessMetrics.to_dict()
            as_is_name: Name of the As-Is process
            to_be_name: Name of the To-Be process
            
        Returns:
            Analysis report as a string (markdown formatted)
        """
        import json
        
        result = await self.chain.ainvoke({
            "analysis_instructions": self.analysis_instructions,
            "diff_data": json.dumps(diff_data, indent=2, ensure_ascii=False),
            "metrics_data": json.dumps(metrics_data, indent=2, ensure_ascii=False),
            "as_is_name": as_is_name,
            "to_be_name": to_be_name,
        })
        
        return result


def create_agent(
    provider: str = "google",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    prompts_dir: Optional[Path] = None
) -> ProcessAnalysisAgent:
    """
    Factory function to create a ProcessAnalysisAgent.
    
    Args:
        provider: LLM provider ("google", "openai", "anthropic")
        model: Model name (optional, uses provider default)
        api_key: API key (optional, can use environment variables)
        prompts_dir: Directory containing prompt files
        
    Returns:
        Configured ProcessAnalysisAgent instance
    """
    return ProcessAnalysisAgent(
        provider=provider,
        model=model,
        api_key=api_key,
        prompts_dir=prompts_dir
    )