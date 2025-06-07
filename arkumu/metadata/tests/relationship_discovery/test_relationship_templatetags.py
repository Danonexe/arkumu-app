"""
Tests for Relationship Template Tags

Tests the template tag functions used for visualizing cross-dataset relationships
in the UI, including matrix visualization and relationship rendering.
"""

import pytest
from django.template import Context, Template
from django.test import TestCase

from arkumu.metadata.templatetags.relationship_tags import (
    confidence_to_color,
    relationship_type_color,
    relationship_summary,
    confidence_level,
    format_evidence,
    relationship_icon,
    cluster_color,
    high_confidence_count,
    matrix_lookup,
    slugify_matrix_key,
    to_json,
    get_relationships_for_pair,
    relationship_matrix_cell
)


class TestRelationshipTemplateTagsUnit:
    """Unit tests for individual template tag functions"""
    
    def test_confidence_to_color(self):
        """Test confidence score to color conversion"""
        # Test edge cases
        assert confidence_to_color(0) == '#f3f4f6'  # gray for zero
        assert confidence_to_color(1.0) == '#172554'  # darkest blue for max
        
        # Test gradient levels
        assert confidence_to_color(0.1) == '#dbeafe'  # light blue
        assert confidence_to_color(0.5) == '#3b82f6'  # medium blue
        assert confidence_to_color(0.9) == '#1e3a8a'  # dark blue
        
        # Test bounds
        assert confidence_to_color(-0.1) == '#dbeafe'  # Should handle negative
        assert confidence_to_color(1.5) == '#172554'   # Should cap at max

    def test_relationship_type_color(self):
        """Test relationship type color mapping"""
        # Test all supported relationship types
        assert relationship_type_color('semantic_similar') == '#3b82f6'  # blue
        assert relationship_type_color('value_overlap') == '#10b981'     # green
        assert relationship_type_color('pattern_match') == '#f59e0b'     # yellow
        assert relationship_type_color('foreign_key') == '#ef4444'       # red
        assert relationship_type_color('cross_dataset_semantic') == '#8b5cf6'  # purple
        
        # Test unknown type
        assert relationship_type_color('unknown_type') == '#6b7280'  # gray default

    def test_relationship_icon(self):
        """Test relationship type icon mapping"""
        # Test all supported relationship types
        assert relationship_icon('semantic_similar') == '🔗'
        assert relationship_icon('value_overlap') == '📊'
        assert relationship_icon('pattern_match') == '🎯'
        assert relationship_icon('foreign_key') == '🔑'
        assert relationship_icon('cross_dataset_semantic') == '🌐'
        
        # Test unknown type
        assert relationship_icon('unknown_type') == '❓'

    def test_confidence_level(self):
        """Test confidence level categorization"""
        assert confidence_level(0.9) == "High"
        assert confidence_level(0.8) == "High"
        assert confidence_level(0.7) == "Medium"
        assert confidence_level(0.6) == "Medium"
        assert confidence_level(0.5) == "Low"
        assert confidence_level(0.4) == "Low"
        assert confidence_level(0.3) == "Very Low"
        assert confidence_level(0.1) == "Very Low"

    def test_high_confidence_count(self):
        """Test counting high confidence relationships"""
        relationships = [
            {'confidence': 0.8},
            {'confidence': 0.6},
            {'confidence': 0.9},
            {'confidence': 0.4},
            {'confidence': 0.75}
        ]
        
        assert high_confidence_count(relationships) == 3  # 0.8, 0.9, and 0.75 > 0.7
        assert high_confidence_count([]) == 0
        assert high_confidence_count(None) == 0

    def test_relationship_summary(self):
        """Test relationship summary generation"""
        relationships = [
            {'relationship_type': 'semantic_similar'},
            {'relationship_type': 'semantic_similar'},
            {'relationship_type': 'value_overlap'},
            {'relationship_type': 'foreign_key'},
            {'relationship_type': 'pattern_match'},
            {'relationship_type': 'pattern_match'}
        ]
        
        summary = relationship_summary(relationships, max_types=3)
        assert "2 Semantic Similar" in summary
        assert "2 Pattern Match" in summary
        assert "1 Value Overlap" in summary
        
        # Test with more types than max
        summary_limited = relationship_summary(relationships, max_types=2)
        assert "and 2 more" in summary_limited
        
        # Test empty relationships
        assert relationship_summary([]) == "No relationships"
        assert relationship_summary(None) == "No relationships"

    def test_format_evidence(self):
        """Test evidence formatting for display"""
        evidence = {
            'common_values_count': 5,
            'jaccard_similarity': 0.75,
            'overlap_ratio': 0.85,
            'common_semantics': ['person', 'identifier'],
            'shared_pattern': 'prefix:ID'
        }
        
        formatted = format_evidence(evidence)
        assert "5 common values" in formatted
        assert "Similarity: 0.75" in formatted
        assert "Overlap: 85.0%" in formatted
        assert "Semantics: person, identifier" in formatted
        assert "Pattern: prefix:ID" in formatted
        
        # Test empty evidence
        assert format_evidence({}) == ""
        assert format_evidence(None) == ""

    def test_cluster_color(self):
        """Test cluster color cycling"""
        # Test first 8 colors
        colors = [cluster_color(i) for i in range(8)]
        assert len(set(colors)) == 8  # All unique
        
        # Test cycling
        assert cluster_color(0) == cluster_color(8)  # Should cycle
        assert cluster_color(1) == cluster_color(9)

    def test_matrix_lookup(self):
        """Test matrix value lookup"""
        matrix = {
            'key1': {'value': 0.8},
            'key2': {'value': 0.6}
        }
        
        assert matrix_lookup(matrix, 'key1') == {'value': 0.8}
        assert matrix_lookup(matrix, 'nonexistent') == {}
        assert matrix_lookup(None, 'key1') == {}
        assert matrix_lookup(matrix, None) == {}

    def test_slugify_matrix_key(self):
        """Test matrix key creation"""
        assert slugify_matrix_key('col1', 'col2') == 'col1-col2'
        assert slugify_matrix_key('artist_id', 'creator_id') == 'artist_id-creator_id'

    def test_to_json(self):
        """Test JSON conversion"""
        data = {'key': 'value', 'number': 42}
        json_str = to_json(data)
        assert '"key": "value"' in json_str
        assert '"number": 42' in json_str
        
        # Test invalid data
        class NonSerializable:
            pass
        
        assert to_json(NonSerializable()) == '{}'

    def test_get_relationships_for_pair(self):
        """Test getting relationships for specific column pair"""
        relationships = [
            {
                'source_column': 'artist_id',
                'target_column': 'creator_id',
                'bidirectional': False
            },
            {
                'source_column': 'creator_id',
                'target_column': 'artist_id',
                'bidirectional': True
            },
            {
                'source_column': 'other_col',
                'target_column': 'another_col',
                'bidirectional': False
            }
        ]
        
        # Test direct match
        matches = get_relationships_for_pair(relationships, 'artist_id-creator_id')
        assert len(matches) == 2  # Both directions
        
        # Test bidirectional match
        matches_reverse = get_relationships_for_pair(relationships, 'creator_id-artist_id')
        assert len(matches_reverse) == 2  # Should find both directions
        
        # Test no match
        no_matches = get_relationships_for_pair(relationships, 'nonexistent-pair')
        assert len(no_matches) == 0


class TestRelationshipTemplateTagsIntegration(TestCase):
    """Integration tests for template tags in template context"""
    
    def test_confidence_to_color_in_template(self):
        """Test confidence_to_color filter in template"""
        template = Template(
            "{% load relationship_tags %}"
            "{{ confidence|confidence_to_color }}"
        )
        
        context = Context({'confidence': 0.8})
        rendered = template.render(context)
        assert rendered == '#1e40af'  # Expected color for 0.8 (level 8)

    def test_relationship_type_color_in_template(self):
        """Test relationship_type_color filter in template"""
        template = Template(
            "{% load relationship_tags %}"
            "{{ rel_type|relationship_type_color }}"
        )
        
        context = Context({'rel_type': 'cross_dataset_semantic'})
        rendered = template.render(context)
        assert rendered == '#8b5cf6'

    def test_relationship_summary_in_template(self):
        """Test relationship_summary filter in template"""
        template = Template(
            "{% load relationship_tags %}"
            "{{ relationships|relationship_summary }}"
        )
        
        relationships = [
            {'relationship_type': 'semantic_similar'},
            {'relationship_type': 'value_overlap'}
        ]
        
        context = Context({'relationships': relationships})
        rendered = template.render(context)
        assert "1 Semantic Similar" in rendered
        assert "1 Value Overlap" in rendered

    def test_format_evidence_in_template(self):
        """Test format_evidence filter in template"""
        template = Template(
            "{% load relationship_tags %}"
            "{{ evidence|format_evidence }}"
        )
        
        evidence = {
            'common_values_count': 3,
            'jaccard_similarity': 0.6
        }
        
        context = Context({'evidence': evidence})
        rendered = template.render(context)
        assert "3 common values" in rendered
        assert "Similarity: 0.60" in rendered

    def test_matrix_cell_template_tag(self):
        """Test relationship_matrix_cell template tag"""
        template = Template(
            "{% load relationship_tags %}"
            "{% relationship_matrix_cell matrix 'col1' 'col2' %}"
        )
        
        matrix = {'col1-col2': 0.85}
        context = Context({'matrix': matrix})
        rendered = template.render(context)
        assert rendered.strip() == '0.85'

    def test_relationship_badge_inclusion_tag(self):
        """Test relationship_badge inclusion tag"""
        # This would require the actual template file, so we test the context preparation
        from arkumu.metadata.templatetags.relationship_tags import relationship_badge
        
        relationship = {
            'relationship_type': 'cross_dataset_semantic',
            'confidence': 0.8
        }
        
        context = relationship_badge(relationship)
        assert context['relationship'] == relationship
        assert context['color'] == '#8b5cf6'
        assert context['icon'] == '🌐'

    def test_complex_template_with_cross_dataset_data(self):
        """Test complex template with cross-dataset relationship data"""
        template = Template("""
            {% load relationship_tags %}
            <div class="relationship-matrix">
                {% for rel in cross_dataset_relationships %}
                    <div class="relationship-item" 
                         style="background-color: {{ rel.relationship_type|relationship_type_color }}">
                        {{ rel.relationship_type|relationship_icon }}
                        {{ rel.source_column }} → {{ rel.target_column }}
                        ({{ rel.confidence|confidence_level }}: {{ rel.confidence|floatformat:2 }})
                        <small>{{ rel.evidence|format_evidence }}</small>
                    </div>
                {% endfor %}
            </div>
        """)
        
        cross_dataset_relationships = [
            {
                'relationship_type': 'cross_dataset_semantic',
                'source_column': 'artists.artist_id',
                'target_column': 'artworks.creator_id',
                'confidence': 0.85,
                'evidence': {
                    'similarity_score': 0.85,
                    'common_semantics': ['identifier', 'person']
                }
            }
        ]
        
        context = Context({'cross_dataset_relationships': cross_dataset_relationships})
        rendered = template.render(context)
        
        # Verify key elements are present
        assert 'relationship-matrix' in rendered
        assert '🌐' in rendered  # cross_dataset_semantic icon
        assert 'artists.artist_id' in rendered
        assert 'artworks.creator_id' in rendered
        assert 'High' in rendered  # confidence level
        assert '0.85' in rendered  # confidence score
        assert '#8b5cf6' in rendered  # cross_dataset_semantic color

    def test_matrix_visualization_template(self):
        """Test template for matrix visualization"""
        template = Template("""
            {% load relationship_tags %}
            <table class="relationship-matrix">
                {% for source_col in source_columns %}
                    <tr>
                        {% for target_col in target_columns %}
                            {% relationship_matrix_cell matrix source_col target_col as cell_value %}
                            <td style="background-color: {{ cell_value|confidence_to_color }}"
                                title="{{ source_col }} → {{ target_col }}: {{ cell_value|confidence_level }}">
                                {{ cell_value|floatformat:2 }}
                            </td>
                        {% endfor %}
                    </tr>
                {% endfor %}
            </table>
        """)
        
        context = Context({
            'source_columns': ['artists.artist_id', 'artists.artist_name'],
            'target_columns': ['artworks.creator_id', 'artworks.artwork_title'],
            'matrix': {
                'artists.artist_id-artworks.creator_id': 0.9,
                'artists.artist_name-artworks.artwork_title': 0.3,
                'artists.artist_id-artworks.artwork_title': 0.1,
                'artists.artist_name-artworks.creator_id': 0.2
            }
        })
        
        rendered = template.render(context)
        
        # Verify matrix structure
        assert 'relationship-matrix' in rendered
        assert '0.90' in rendered  # High confidence relationship
        assert '0.30' in rendered  # Lower confidence relationship
        assert 'artists.artist_id → artworks.creator_id: High' in rendered
        assert '#1e3a8a' in rendered or '#172554' in rendered  # High confidence color

    def test_error_handling_in_templates(self):
        """Test template tag error handling with invalid data"""
        template = Template("""
            {% load relationship_tags %}
            {{ invalid_confidence|confidence_to_color }}
            {{ none_value|relationship_summary }}
            {{ empty_dict|format_evidence }}
        """)
        
        context = Context({
            'invalid_confidence': 'not_a_number',
            'none_value': None,
            'empty_dict': {}
        })
        
        # Should not raise errors and handle gracefully
        try:
            rendered = template.render(context)
            # Basic checks that it rendered without errors
            assert rendered is not None
        except Exception as e:
            pytest.fail(f"Template should handle invalid data gracefully: {e}")


class TestCrossDatasetVisualizationTemplates:
    """Test templates specifically for cross-dataset relationship visualization"""
    
    def test_cross_dataset_relationship_display(self):
        """Test display of cross-dataset relationships"""
        template = Template("""
            {% load relationship_tags %}
            {% for rel in relationships %}
                <div class="cross-dataset-relation">
                    <span class="source-dataset">{{ rel.source_column|cut:'.0' }}</span>
                    <span class="target-dataset">{{ rel.target_column|cut:'.0' }}</span>
                    <span class="confidence">{{ rel.confidence|confidence_level }}</span>
                    <span class="type">{{ rel.relationship_type|relationship_icon }}</span>
                </div>
            {% endfor %}
        """)
        
        relationships = [
            {
                'source_column': 'artists.artist_id',
                'target_column': 'artworks.creator_id',
                'confidence': 0.9,
                'relationship_type': 'cross_dataset_semantic'
            }
        ]
        
        context = Context({'relationships': relationships})
        rendered = template.render(context)
        
        assert 'cross-dataset-relation' in rendered
        assert 'High' in rendered  # confidence level
        assert '🌐' in rendered  # relationship icon 