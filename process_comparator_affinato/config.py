"""
Configuration for Process Comparator

Set your API keys here or via environment variables.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """Application configuration."""
    
    # LLM Provider: "google", "openai", "anthropic"
    llm_provider: str = "google"
    
    # Model name (leave empty for default)
    llm_model: Optional[str] = None
    
    # API Keys (prefer environment variables)
    google_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    
    # Metrics thresholds
    volatility_high_threshold: float = 0.30  # > 30% = Alta
    volatility_low_threshold: float = 0.01   # < 1% = Bassa
    
    # PCS weights (must sum to 1.0)
    pcs_volatility_weight: float = 0.50
    pcs_handover_weight: float = 0.40
    pcs_automation_weight: float = 0.10
    
    # Output settings
    output_language: str = "italian"
    
    def __post_init__(self):
        """Load API keys from environment if not provided."""
        if self.google_api_key is None:
            # Support both GEMINI_API_KEY and GOOGLE_API_KEY
            self.google_api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if self.openai_api_key is None:
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
        if self.anthropic_api_key is None:
            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    
    def get_api_key(self) -> Optional[str]:
        """Get API key for the configured provider."""
        keys = {
            "google": self.google_api_key,
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
        }
        return keys.get(self.llm_provider)
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []
        
        # Check API key
        if not self.get_api_key():
            errors.append(f"No API key configured for provider '{self.llm_provider}'")
        
        # Check weights sum to 1.0
        total_weight = self.pcs_volatility_weight + self.pcs_handover_weight + self.pcs_automation_weight
        if abs(total_weight - 1.0) > 0.001:
            errors.append(f"PCS weights must sum to 1.0 (current: {total_weight})")
        
        return errors


# Default configuration instance
config = Config()


def load_config_from_env() -> Config:
    """Load configuration from environment variables."""
    return Config(
        llm_provider=os.getenv("LLM_PROVIDER", "google"),
        llm_model=os.getenv("LLM_MODEL"),
        google_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    )