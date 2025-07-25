"""
Conflict Resolver

Handles conflicts that arise when multiple harmonization rules match the same resource.
"""

from typing import List, Optional, Dict, Any
from django.utils import timezone
from arkumu.metadata.models.harmonization import HarmonizationConflict, HarmonizationRule
from .mapping_rules import RuleMatchResult


class ConflictResolutionStrategy:
    """Base class for conflict resolution strategies."""
    
    def resolve(self, conflict: HarmonizationConflict) -> Optional[HarmonizationRule]:
        """
        Resolve a conflict and return the selected rule.
        
        Args:
            conflict: HarmonizationConflict to resolve
            
        Returns:
            Selected HarmonizationRule or None if unresolvable
        """
        raise NotImplementedError


class PriorityBasedStrategy(ConflictResolutionStrategy):
    """Resolve conflicts by selecting the rule with highest priority."""
    
    def resolve(self, conflict: HarmonizationConflict) -> Optional[HarmonizationRule]:
        """Resolve by priority, then creation date."""
        rules = list(conflict.conflicting_rules.all().order_by('-priority', 'created_at'))
        return rules[0] if rules else None


class RecencyBasedStrategy(ConflictResolutionStrategy):
    """Resolve conflicts by selecting the most recently created rule."""
    
    def resolve(self, conflict: HarmonizationConflict) -> Optional[HarmonizationRule]:
        """Resolve by most recent creation date."""
        rules = list(conflict.conflicting_rules.all().order_by('-created_at'))
        return rules[0] if rules else None


class MostSpecificStrategy(ConflictResolutionStrategy):
    """Resolve conflicts by selecting the most specific pattern."""
    
    def resolve(self, conflict: HarmonizationConflict) -> Optional[HarmonizationRule]:
        """Resolve by pattern specificity (exact matches over regex)."""
        rules = list(conflict.conflicting_rules.all())
        
        if not rules:
            return None
        
        # Separate exact matches from regex patterns
        exact_matches = []
        regex_patterns = []
        
        for rule in rules:
            pattern = rule.source_property_pattern
            # Simple heuristic: if pattern contains regex metacharacters, treat as regex
            if any(char in pattern for char in ['*', '+', '?', '[', ']', '(', ')', '|', '^', '$', '\\.']):
                regex_patterns.append(rule)
            else:
                exact_matches.append(rule)
        
        # Prefer exact matches, then fall back to priority
        if exact_matches:
            return sorted(exact_matches, key=lambda r: (-r.priority, r.created_at))[0]
        else:
            return sorted(regex_patterns, key=lambda r: (-r.priority, r.created_at))[0]


class ConflictResolver:
    """
    Manages conflict resolution for harmonization rules.
    """
    
    STRATEGIES = {
        'priority': PriorityBasedStrategy,
        'recency': RecencyBasedStrategy,
        'specificity': MostSpecificStrategy
    }
    
    def __init__(self, default_strategy: str = 'priority'):
        """
        Initialize the conflict resolver.
        
        Args:
            default_strategy: Default resolution strategy to use
        """
        self.default_strategy = default_strategy
        self._strategy_instances = {}
    
    def resolve_conflict(self, 
                        conflict: HarmonizationConflict,
                        strategy: str = None,
                        resolved_by_user = None) -> bool:
        """
        Resolve a conflict using the specified strategy.
        
        Args:
            conflict: HarmonizationConflict to resolve
            strategy: Resolution strategy to use (defaults to default_strategy)
            resolved_by_user: User who resolved the conflict (for manual resolution)
            
        Returns:
            True if conflict was resolved successfully
        """
        try:
            strategy = strategy or self.default_strategy
            strategy_instance = self._get_strategy_instance(strategy)
            
            selected_rule = strategy_instance.resolve(conflict)
            
            if selected_rule:
                conflict.selected_rule = selected_rule
                conflict.resolution = 'manual' if resolved_by_user else 'priority'
                conflict.resolved_by = resolved_by_user
                conflict.resolved_at = timezone.now()
                conflict.save()
                
                return True
            else:
                conflict.resolution = 'skipped'
                conflict.resolution_notes = f"No rule could be selected using {strategy} strategy"
                conflict.resolved_at = timezone.now()
                conflict.save()
                
                return False
                
        except Exception as e:
            conflict.resolution_notes = f"Resolution failed: {str(e)}"
            conflict.save()
            return False
    
    def resolve_conflicts_bulk(self, 
                             conflicts: List[HarmonizationConflict],
                             strategy: str = None) -> Dict[str, int]:
        """
        Resolve multiple conflicts using the specified strategy.
        
        Args:
            conflicts: List of conflicts to resolve
            strategy: Resolution strategy to use
            
        Returns:
            Dictionary with resolution statistics
        """
        stats = {
            'resolved': 0,
            'failed': 0,
            'skipped': 0
        }
        
        for conflict in conflicts:
            if conflict.resolution == 'pending':
                success = self.resolve_conflict(conflict, strategy)
                if success:
                    if conflict.selected_rule:
                        stats['resolved'] += 1
                    else:
                        stats['skipped'] += 1
                else:
                    stats['failed'] += 1
        
        return stats
    
    def get_pending_conflicts(self, 
                            organization = None,
                            execution = None) -> List[HarmonizationConflict]:
        """
        Get conflicts that need resolution.
        
        Args:
            organization: Optional organization to filter by
            execution: Optional execution to filter by
            
        Returns:
            List of pending HarmonizationConflict instances
        """
        queryset = HarmonizationConflict.objects.filter(resolution='pending')
        
        if execution:
            queryset = queryset.filter(execution=execution)
        
        if organization:
            queryset = queryset.filter(
                conflicting_rules__source_organization=organization
            ).distinct()
        
        return list(queryset.select_related('execution').prefetch_related('conflicting_rules'))
    
    def analyze_conflict_patterns(self, 
                                organization = None) -> Dict[str, Any]:
        """
        Analyze conflict patterns to identify common issues.
        
        Args:
            organization: Optional organization to analyze
            
        Returns:
            Dictionary with conflict analysis results
        """
        queryset = HarmonizationConflict.objects.all()
        
        if organization:
            queryset = queryset.filter(
                conflicting_rules__source_organization=organization
            ).distinct()
        
        conflicts = list(queryset.prefetch_related('conflicting_rules'))
        
        analysis = {
            'total_conflicts': len(conflicts),
            'pending_conflicts': len([c for c in conflicts if c.resolution == 'pending']),
            'resolved_conflicts': len([c for c in conflicts if c.resolution != 'pending']),
            'most_common_resources': {},
            'rule_conflict_frequency': {},
            'resolution_methods': {}
        }
        
        # Analyze resource URIs that frequently have conflicts
        resource_conflicts = {}
        for conflict in conflicts:
            uri = conflict.source_resource_uri
            resource_conflicts[uri] = resource_conflicts.get(uri, 0) + 1
        
        # Sort by frequency and take top 10
        analysis['most_common_resources'] = dict(
            sorted(resource_conflicts.items(), key=lambda x: x[1], reverse=True)[:10]
        )
        
        # Analyze which rules are frequently in conflicts
        rule_conflicts = {}
        for conflict in conflicts:
            for rule in conflict.conflicting_rules.all():
                rule_id = str(rule.id)
                rule_conflicts[rule_id] = rule_conflicts.get(rule_id, 0) + 1
        
        analysis['rule_conflict_frequency'] = dict(
            sorted(rule_conflicts.items(), key=lambda x: x[1], reverse=True)[:10]
        )
        
        # Analyze resolution methods
        resolution_methods = {}
        for conflict in conflicts:
            method = conflict.resolution
            resolution_methods[method] = resolution_methods.get(method, 0) + 1
        
        analysis['resolution_methods'] = resolution_methods
        
        return analysis
    
    def suggest_rule_improvements(self, 
                                organization) -> List[Dict[str, Any]]:
        """
        Suggest improvements to rules based on conflict analysis.
        
        Args:
            organization: Organization to analyze
            
        Returns:
            List of improvement suggestions
        """
        suggestions = []
        
        # Get conflicts for this organization
        conflicts = self.get_pending_conflicts(organization)
        
        # Analyze patterns
        pattern_conflicts = {}
        for conflict in conflicts:
            for rule in conflict.conflicting_rules.all():
                pattern = rule.source_property_pattern
                if pattern not in pattern_conflicts:
                    pattern_conflicts[pattern] = []
                pattern_conflicts[pattern].append(rule)
        
        # Generate suggestions for frequently conflicting patterns
        for pattern, rules in pattern_conflicts.items():
            if len(rules) > 1:
                suggestions.append({
                    'type': 'conflicting_patterns',
                    'pattern': pattern,
                    'conflicting_rules': [str(rule) for rule in rules],
                    'suggestion': f"Consider making pattern '{pattern}' more specific or adjusting rule priorities",
                    'severity': 'high' if len(rules) > 2 else 'medium'
                })
        
        return suggestions
    
    def _get_strategy_instance(self, strategy_name: str) -> ConflictResolutionStrategy:
        """Get or create strategy instance."""
        if strategy_name not in self._strategy_instances:
            if strategy_name not in self.STRATEGIES:
                raise ValueError(f"Unknown strategy: {strategy_name}")
            
            strategy_class = self.STRATEGIES[strategy_name]
            self._strategy_instances[strategy_name] = strategy_class()
        
        return self._strategy_instances[strategy_name]