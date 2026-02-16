"""Diff Engine - Compares As-Is and To-Be ProcessDocuments."""

import re
from dataclasses import dataclass, field
from typing import Optional
from difflib import SequenceMatcher
from .document_parser import ProcessDocument, Activity


def normalize_text(text: str) -> str:
    """Normalize text for comparison - removes extra whitespace, newlines, etc."""
    if not text:
        return ""
    # Replace newlines, tabs, multiple spaces with single space
    text = re.sub(r'[\n\r\t\x07]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    # Strip and lowercase for comparison
    return text.strip().lower()


@dataclass
class ActivityChange:
    """Change to a single activity."""
    code: str
    change_type: str  # 'added', 'removed', 'modified'
    as_is: Optional[Activity] = None
    to_be: Optional[Activity] = None
    title_changed: bool = False
    description_changed: bool = False
    executor_changed: bool = False
    it_system_changed: bool = False
    old_executor: Optional[str] = None
    new_executor: Optional[str] = None
    old_it_system: Optional[str] = None
    new_it_system: Optional[str] = None


@dataclass
class ProcessDiff:
    """All differences between As-Is and To-Be."""
    as_is_doc: ProcessDocument
    to_be_doc: ProcessDocument
    process_name_changed: bool = False
    old_process_name: str = ""
    new_process_name: str = ""
    activities_added: list[ActivityChange] = field(default_factory=list)
    activities_removed: list[ActivityChange] = field(default_factory=list)
    activities_modified: list[ActivityChange] = field(default_factory=list)
    activities_reordered: list[tuple[str, int, int]] = field(default_factory=list)
    content_inheritance: dict[str, str] = field(default_factory=dict)  # removed_code -> added_code
    
    def get_new_executors(self) -> set[str]:
        return self.to_be_doc.get_executors() - self.as_is_doc.get_executors()
    
    def to_dict(self) -> dict:
        as_is_count = len(self.as_is_doc.activities)
        to_be_count = len(self.to_be_doc.activities)
        
        return {
            "process_name_changed": self.process_name_changed,
            "old_process_name": self.old_process_name,
            "new_process_name": self.new_process_name,
            "as_is_activity_count": as_is_count,
            "to_be_activity_count": to_be_count,
            "activities_added": [
                {
                    "code": c.code,
                    "title": c.to_be.title,
                    "description": c.to_be.description,
                    "executor": c.to_be.executor,
                    "it_system": c.to_be.it_system,
                    "inherits_from": self.content_inheritance.get(c.code),  # If this added activity inherited from a removed one
                }
                for c in self.activities_added
            ],
            "activities_removed": [
                {
                    "code": c.code,
                    "title": c.as_is.title,
                    "description": c.as_is.description,
                    "executor": c.as_is.executor,
                    "it_system": c.as_is.it_system,
                    "content_inherited_by": self.content_inheritance.get(c.code),  # Which added activity inherited this
                }
                for c in self.activities_removed
            ],
            "activities_modified": [
                {
                    "code": c.code,
                    "title_changed": c.title_changed,
                    "old_title": c.as_is.title if c.title_changed else None,
                    "new_title": c.to_be.title if c.title_changed else None,
                    "description_changed": c.description_changed,
                    "old_description": c.as_is.description if c.description_changed else None,
                    "new_description": c.to_be.description if c.description_changed else None,
                    "executor_changed": c.executor_changed,
                    "old_executor": c.old_executor,
                    "new_executor": c.new_executor,
                    "it_system_changed": c.it_system_changed,
                    "old_it_system": c.old_it_system,
                    "new_it_system": c.new_it_system,
                }
                for c in self.activities_modified
            ],
            "new_executors": list(self.get_new_executors()),
            "activities_reordered": [
                {
                    "code": code, 
                    "old_position": old + 1,  # 1-indexed for human readability
                    "new_position": new + 1,
                    "old_position_label": f"{old + 1}° su {as_is_count}",
                    "new_position_label": f"{new + 1}° su {to_be_count}",
                }
                for code, old, new in self.activities_reordered
            ],
            "content_inheritance": self.content_inheritance,
        }


class DiffEngine:
    """Compares two process documents."""
    
    def __init__(self, similarity_threshold: float = 0.8):
        self.similarity_threshold = similarity_threshold
    
    def compare(self, as_is: ProcessDocument, to_be: ProcessDocument) -> ProcessDiff:
        diff = ProcessDiff(as_is_doc=as_is, to_be_doc=to_be)
        
        # Process name
        if as_is.process_name != to_be.process_name:
            diff.process_name_changed = True
            diff.old_process_name = as_is.process_name
            diff.new_process_name = to_be.process_name
        
        # Activities
        as_is_acts = {a.code: a for a in as_is.activities}
        to_be_acts = {a.code: a for a in to_be.activities}
        
        for code in set(to_be_acts) - set(as_is_acts):
            diff.activities_added.append(ActivityChange(code=code, change_type='added', to_be=to_be_acts[code]))
        
        for code in set(as_is_acts) - set(to_be_acts):
            diff.activities_removed.append(ActivityChange(code=code, change_type='removed', as_is=as_is_acts[code]))
        
        for code in set(as_is_acts) & set(to_be_acts):
            change = self._compare_activity(as_is_acts[code], to_be_acts[code])
            if change:
                diff.activities_modified.append(change)
        
        # Reordering
        self._detect_reordering(diff)
        
        # Content inheritance (removed -> added)
        diff.content_inheritance = self._detect_content_inheritance(diff)
        
        return diff
    
    def _compare_activity(self, as_is: Activity, to_be: Activity) -> Optional[ActivityChange]:
        change = ActivityChange(code=as_is.code, change_type='modified', as_is=as_is, to_be=to_be)
        has_changes = False
        
        # Compare titles (normalized)
        if normalize_text(as_is.title) != normalize_text(to_be.title):
            change.title_changed = True
            has_changes = True
        
        # Compare descriptions (normalized, with similarity threshold)
        if normalize_text(as_is.description) != normalize_text(to_be.description):
            if SequenceMatcher(None, normalize_text(as_is.description), normalize_text(to_be.description)).ratio() < self.similarity_threshold:
                change.description_changed = True
                has_changes = True
        
        # Compare executors (normalized)
        if normalize_text(as_is.executor) != normalize_text(to_be.executor):
            change.executor_changed = True
            change.old_executor = as_is.executor
            change.new_executor = to_be.executor
            has_changes = True
        
        # Compare IT systems (normalized)
        if normalize_text(as_is.it_system) != normalize_text(to_be.it_system):
            change.it_system_changed = True
            change.old_it_system = as_is.it_system
            change.new_it_system = to_be.it_system
            has_changes = True
        
        return change if has_changes else None
    
    def _detect_reordering(self, diff: ProcessDiff):
        as_is_order = [a.code for a in diff.as_is_doc.activities]
        to_be_order = [a.code for a in diff.to_be_doc.activities]
        common = set(as_is_order) & set(to_be_order)
        
        as_is_pos = {c: i for i, c in enumerate([x for x in as_is_order if x in common])}
        to_be_pos = {c: i for i, c in enumerate([x for x in to_be_order if x in common])}
        
        for code in common:
            if as_is_pos[code] != to_be_pos[code]:
                diff.activities_reordered.append((code, as_is_pos[code], to_be_pos[code]))
    
    def _detect_content_inheritance(self, diff: ProcessDiff) -> dict[str, str]:
        """
        Detect if removed activities have content inherited by added activities.
        Returns dict mapping removed_code -> added_code if similarity > threshold.
        """
        inheritance = {}
        
        for removed in diff.activities_removed:
            removed_desc = normalize_text(removed.as_is.description)
            if not removed_desc:
                continue
                
            best_match = None
            best_score = 0.6  # Minimum threshold for inheritance
            
            for added in diff.activities_added:
                added_desc = normalize_text(added.to_be.description)
                if not added_desc:
                    continue
                    
                score = SequenceMatcher(None, removed_desc, added_desc).ratio()
                if score > best_score:
                    best_score = score
                    best_match = added.code
            
            if best_match:
                inheritance[removed.code] = best_match
        
        return inheritance


def compare_processes(as_is_path: str, to_be_path: str) -> ProcessDiff:
    from .document_parser import parse_aris_document
    return DiffEngine().compare(parse_aris_document(as_is_path), parse_aris_document(to_be_path))