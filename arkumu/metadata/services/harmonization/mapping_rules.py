"""
Mapping Rules and Rule Matcher

Handles matching of harmonization rules to archive resources and conflict resolution.
"""

import re
from typing import List, Optional, Dict, Tuple
from django.db.models import Q
from arkumu.metadata.models.resource import Resource
from arkumu.metadata.models.harmonization import HarmonizationRule, HarmonizationConflict


class RuleMatchResult:
    """Encapsulates the result of rule matching for a resource."""
    
    def __init__(self, resource: Resource, matching_rules: List[HarmonizationRule]):
        self.resource = resource
        self.matching_rules = matching_rules
        self.has_conflicts = len(matching_rules) > 1
        self.selected_rule = None
        
        if not self.has_conflicts and matching_rules:
            self.selected_rule = matching_rules[0]
    
    def resolve_by_priority(self) -> Optional[HarmonizationRule]:
        """Resolve conflicts by selecting the highest priority rule."""
        if not self.matching_rules:
            return None
        
        # Sort by priority (descending) and then by creation date for consistency
        sorted_rules = sorted(
            self.matching_rules,
            key=lambda r: (-r.priority, r.created_at)
        )
        
        self.selected_rule = sorted_rules[0]
        return self.selected_rule


class RuleMatcher:
    """
    Matches harmonization rules to resources and handles conflict resolution.
    """
    
    def __init__(self):
        self._rule_cache = {}
        self._pattern_cache = {}
    
    def find_matching_rules(self, resource: Resource) -> RuleMatchResult:
        """
        Find all harmonization rules that match a given resource.
        
        Args:
            resource: Resource to find matching rules for
            
        Returns:
            RuleMatchResult containing matching rules and conflict information
        """
        if not resource.source:
            return RuleMatchResult(resource, [])
        
        # Get active rules for the resource's organization
        organization_rules = self._get_rules_for_organization(resource.source)
        
        matching_rules = []
        
        for rule in organization_rules:
            if self._rule_matches_resource(rule, resource):
                matching_rules.append(rule)
        
        return RuleMatchResult(resource, matching_rules)
    
    def find_matching_rules_bulk(self, resources: List[Resource]) -> Dict[Resource, RuleMatchResult]:
        """
        Find matching rules for multiple resources efficiently.
        
        Args:
            resources: List of resources to find rules for
            
        Returns:
            Dictionary mapping resources to their RuleMatchResult
        """
        results = {}
        
        # Group resources by organization for efficient querying
        resources_by_org = {}
        for resource in resources:
            if resource.source:
                if resource.source not in resources_by_org:
                    resources_by_org[resource.source] = []
                resources_by_org[resource.source].append(resource)
        
        # Process each organization's resources
        for organization, org_resources in resources_by_org.items():
            org_rules = self._get_rules_for_organization(organization)
            
            for resource in org_resources:
                matching_rules = []
                for rule in org_rules:
                    if self._rule_matches_resource(rule, resource):
                        matching_rules.append(rule)
                
                results[resource] = RuleMatchResult(resource, matching_rules)
        
        return results
    
    def create_conflict_record(self, 
                             match_result: RuleMatchResult,
                             execution) -> Optional[HarmonizationConflict]:
        """
        Create a conflict record for manual resolution.
        
        Args:
            match_result: RuleMatchResult with conflicts
            execution: HarmonizationExecution instance
            
        Returns:
            Created HarmonizationConflict instance or None
        """
        if not match_result.has_conflicts:
            return None
        
        conflict = HarmonizationConflict.objects.create(
            execution=execution,
            source_resource_uri=match_result.resource.uri,
            resolution='pending'
        )
        
        # Add all conflicting rules
        conflict.conflicting_rules.set(match_result.matching_rules)
        
        return conflict
    
    def resolve_conflicts_by_priority(self, 
                                    match_results: List[RuleMatchResult]) -> List[RuleMatchResult]:
        """
        Resolve conflicts in match results using priority-based resolution.
        
        Args:
            match_results: List of RuleMatchResult instances
            
        Returns:
            List of resolved RuleMatchResult instances
        """
        resolved_results = []
        
        for result in match_results:
            if result.has_conflicts:
                result.resolve_by_priority()
            resolved_results.append(result)
        
        return resolved_results
    
    def get_conflicting_results(self, match_results: List[RuleMatchResult]) -> List[RuleMatchResult]:
        """
        Filter match results to only those with conflicts.
        
        Args:
            match_results: List of RuleMatchResult instances
            
        Returns:
            List of RuleMatchResult instances that have conflicts
        """
        return [result for result in match_results if result.has_conflicts]
    
    def _get_rules_for_organization(self, organization) -> List[HarmonizationRule]:
        """Get active rules for an organization with caching."""
        if organization.id not in self._rule_cache:
            rules = list(
                HarmonizationRule.objects.filter(
                    source_organization=organization,
                    is_active=True
                ).order_by('-priority', 'created_at')
            )
            self._rule_cache[organization.id] = rules
        
        return self._rule_cache[organization.id]
    
    def _rule_matches_resource(self, rule: HarmonizationRule, resource: Resource) -> bool:
        """
        Check if a rule matches a resource based on the pattern.
        
        Args:
            rule: HarmonizationRule to check
            resource: Resource to match against
            
        Returns:
            bool: True if rule matches resource
        """
        # Use resource name/label for matching
        resource_name = resource.name or resource.uri.split('/')[-1]
        
        return self._pattern_matches_string(rule.source_property_pattern, resource_name)
    
    def _pattern_matches_string(self, pattern: str, text: str) -> bool:
        """
        Check if a pattern matches a string (exact match or regex).
        
        Args:
            pattern: Pattern to match (can be regex or exact string)
            text: Text to match against
            
        Returns:
            bool: True if pattern matches text
        """
        # Cache compiled regex patterns for performance
        if pattern not in self._pattern_cache:
            try:
                # Try to compile as regex first
                compiled_pattern = re.compile(pattern, re.IGNORECASE)
                self._pattern_cache[pattern] = ('regex', compiled_pattern)
            except re.error:
                # If regex compilation fails, treat as exact match
                self._pattern_cache[pattern] = ('exact', pattern.lower())
        
        pattern_type, compiled_pattern = self._pattern_cache[pattern]
        
        if pattern_type == 'regex':
            return bool(compiled_pattern.search(text))
        else:
            return compiled_pattern == text.lower()
    
    def clear_cache(self):
        """Clear internal caches."""
        self._rule_cache.clear()
        self._pattern_cache.clear()
    
    def validate_rule_pattern(self, pattern: str) -> Tuple[bool, str]:
        """
        Validate a rule pattern.
        
        Args:
            pattern: Pattern to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not pattern or not pattern.strip():
            return False, "Pattern cannot be empty"
        
        try:
            # Try to compile as regex
            re.compile(pattern, re.IGNORECASE)
            return True, ""
        except re.error as e:
            # Still valid as exact match, but provide warning
            return True, f"Pattern will be treated as exact match (regex error: {e})"
    
    def test_rule_against_resources(self, 
                                  rule: HarmonizationRule,
                                  resources: List[Resource]) -> List[Resource]:
        """
        Test a rule against a list of resources to see which would match.
        
        Args:
            rule: Rule to test
            resources: List of resources to test against
            
        Returns:
            List of resources that match the rule
        """
        matching_resources = []
        
        for resource in resources:
            if (resource.source == rule.source_organization and 
                self._rule_matches_resource(rule, resource)):
                matching_resources.append(resource)
        
        return matching_resources