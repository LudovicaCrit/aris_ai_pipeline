"""Metrics Calculator - Volatility, Handover, Automation, PCS."""

from dataclasses import dataclass
from .diff_engine import ProcessDiff

# Weights for PCS formula
VOLATILITY_WEIGHT = 0.50
HANDOVER_WEIGHT = 0.40
AUTOMATION_WEIGHT = 0.10

# Thresholds
VOLATILITY_HIGH = 0.30
VOLATILITY_MEDIUM = 0.10  # Below this is "Bassa"


@dataclass
class ProcessMetrics:
    """All metrics for a process comparison."""
    # Volatility
    volatility_index: float
    volatility_percentage: float
    volatility_level: str  # "Bassa", "Media", "Alta"
    tasks_added: int
    tasks_removed: int
    
    # Handover
    handover_as_is: int
    handover_to_be: int
    handover_delta: int
    
    # Automation
    automation_as_is_rate: float
    automation_to_be_rate: float
    
    # PCS
    pcs: float
    pcs_level: str  # "Basso", "Medio", "Alto", "Critico"
    
    @property
    def requires_audit(self) -> bool:
        return self.pcs >= 0.5
    
    def to_dict(self) -> dict:
        return {
            "volatility": {
                "percentage": self.volatility_percentage,
                "level": self.volatility_level,
                "tasks_added": self.tasks_added,
                "tasks_removed": self.tasks_removed,
            },
            "handover": {
                "as_is": self.handover_as_is,
                "to_be": self.handover_to_be,
                "delta": self.handover_delta,
            },
            "automation": {
                "as_is_rate": f"{self.automation_as_is_rate*100:.1f}%",
                "to_be_rate": f"{self.automation_to_be_rate*100:.1f}%",
            },
            "pcs": {
                "score": self.pcs,
                "level": self.pcs_level,
                "requires_audit": self.requires_audit,
            },
        }


class MetricsCalculator:
    """Calculates process change metrics."""
    
    def calculate(self, diff: ProcessDiff) -> ProcessMetrics:
        # Volatility
        added = len(diff.activities_added)
        removed = len(diff.activities_removed)
        original = len(diff.as_is_doc.activities)
        vol_index = (added + removed) / original if original > 0 else (1.0 if added else 0.0)
        
        if vol_index > VOLATILITY_HIGH:
            vol_level = "Alta"
        elif vol_index > VOLATILITY_MEDIUM:
            vol_level = "Media"
        else:
            vol_level = "Bassa"
        
        # Handover
        ho_as_is = self._count_handovers(diff.as_is_doc.activities)
        ho_to_be = self._count_handovers(diff.to_be_doc.activities)
        ho_delta = ho_to_be - ho_as_is
        
        # Normalize handover for PCS
        if ho_as_is == 0:
            ho_norm = 1.0 if ho_to_be > 0 else 0.0
        else:
            ho_norm = min(abs(ho_delta) / ho_as_is, 1.0)
        
        # Automation
        as_is_manual = diff.as_is_doc.count_manual_activities()
        as_is_total = len(diff.as_is_doc.activities)
        to_be_manual = diff.to_be_doc.count_manual_activities()
        to_be_total = len(diff.to_be_doc.activities)
        
        auto_as_is = (as_is_total - as_is_manual) / as_is_total if as_is_total else 0.0
        auto_to_be = (to_be_total - to_be_manual) / to_be_total if to_be_total else 0.0
        auto_delta = abs(auto_to_be - auto_as_is)
        
        # PCS
        pcs = (min(vol_index, 1.0) * VOLATILITY_WEIGHT + 
               ho_norm * HANDOVER_WEIGHT + 
               auto_delta * AUTOMATION_WEIGHT)
        
        if pcs >= 0.7:
            pcs_level = "Critico"
        elif pcs >= 0.5:
            pcs_level = "Alto"
        elif pcs >= 0.2:
            pcs_level = "Medio"
        else:
            pcs_level = "Basso"
        
        return ProcessMetrics(
            volatility_index=vol_index,
            volatility_percentage=vol_index * 100,
            volatility_level=vol_level,
            tasks_added=added,
            tasks_removed=removed,
            handover_as_is=ho_as_is,
            handover_to_be=ho_to_be,
            handover_delta=ho_delta,
            automation_as_is_rate=auto_as_is,
            automation_to_be_rate=auto_to_be,
            pcs=pcs,
            pcs_level=pcs_level,
        )
    
    def _count_handovers(self, activities: list) -> int:
        if len(activities) < 2:
            return 0
        count = 0
        prev = activities[0].executor
        for a in activities[1:]:
            if a.executor != prev:
                count += 1
            prev = a.executor
        return count


def calculate_metrics(diff: ProcessDiff) -> ProcessMetrics:
    return MetricsCalculator().calculate(diff)