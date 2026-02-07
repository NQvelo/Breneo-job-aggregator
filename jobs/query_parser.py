"""
Natural Language Processing module for job search queries.

Converts natural language queries into structured search syntax following Google-like rules:
- Software → match jobs containing "software" in the title
- Software Engineer → match jobs containing "software" AND "engineer"
- "Software Engineer" → match jobs containing "software engineer" as exact phrase
- Software OR Engineer → match jobs containing "software" OR "engineer"
- -"Software Engineer" → exclude jobs containing "software engineer" as exact phrase
"""

import re
from typing import List, Dict, Tuple, Optional
from collections import namedtuple

# Structured representation of parsed query components
QueryComponents = namedtuple('QueryComponents', [
    'title_filter',      # String format for title_filter parameter
    'django_q_filters',  # Django Q objects for filtering
    'keywords',          # List of keywords extracted
    'exact_phrases',     # List of exact phrases (quoted)
    'exclusions',        # List of terms/phrases to exclude
    'or_groups',         # Groups of OR terms
])


class JobQueryParser:
    """
    Parses natural language job search queries into structured search syntax.
    """
    
    # Common exclusion indicators
    EXCLUSION_KEYWORDS = ['not', 'exclude', 'without', 'except', 'minus']
    
    # Common company indicators (case-insensitive patterns)
    COMPANY_INDICATORS = [
        r'\bat\s+([A-Z][a-zA-Z\s]+)',  # "at Google", "at Meta"
        r'jobs\s+at\s+([A-Z][a-zA-Z\s]+)',  # "jobs at Google"
        r'from\s+([A-Z][a-zA-Z\s]+)',  # "from Stripe"
    ]
    
    # Common job title patterns
    JOB_TITLE_PATTERNS = [
        r'(backend|frontend|full.?stack|software|senior|junior|lead|principal)',
        r'(developer|engineer|architect|designer|manager)',
        r'(jobs?|positions?|roles?|openings?)',
    ]
    
    def __init__(self):
        """Initialize the parser with compiled regex patterns."""
        self.exact_phrase_pattern = re.compile(r'"([^"]+)"')
        self.exclusion_pattern = re.compile(r'-\s*"?([^"\s]+(?:\s+[^"\s]+)*)"?')
        self.or_pattern = re.compile(r'\bOR\b', re.IGNORECASE)
        
    def parse(self, query: str) -> QueryComponents:
        """
        Parse a natural language query into structured components.
        
        Args:
            query: Natural language search query
            
        Returns:
            QueryComponents namedtuple with parsed components
        """
        if not query or not query.strip():
            return self._empty_components()
        
        query = query.strip()
        
        # Extract exact phrases (quoted strings)
        exact_phrases = self._extract_exact_phrases(query)
        query = self._remove_exact_phrases(query)
        
        # Extract exclusions (terms prefixed with -)
        exclusions, query = self._extract_exclusions(query)
        
        # Extract OR groups and remove OR parts from query
        or_groups = self._extract_or_groups(query)
        if or_groups:
            # If we have OR groups, remove all OR terms from query for keyword extraction
            query = self._remove_or_terms(query, or_groups)
        else:
            query = self._remove_or_operators(query)
        
        # Extract remaining keywords (AND logic)
        keywords = self._extract_keywords(query)
        
        # Build title_filter string
        title_filter = self._build_title_filter(keywords, exact_phrases, exclusions, or_groups)
        
        # Build Django Q filters
        django_q_filters = self._build_django_filters(keywords, exact_phrases, exclusions, or_groups)
        
        return QueryComponents(
            title_filter=title_filter,
            django_q_filters=django_q_filters,
            keywords=keywords,
            exact_phrases=exact_phrases,
            exclusions=exclusions,
            or_groups=or_groups,
        )
    
    def _extract_exact_phrases(self, query: str) -> List[str]:
        """Extract quoted phrases from query."""
        phrases = []
        for match in self.exact_phrase_pattern.finditer(query):
            phrases.append(match.group(1))
        return phrases
    
    def _remove_exact_phrases(self, query: str) -> str:
        """Remove quoted phrases from query."""
        return self.exact_phrase_pattern.sub('', query).strip()
    
    def _extract_exclusions(self, query: str) -> Tuple[List[str], str]:
        """Extract exclusion terms (prefixed with -) and remove them from query."""
        exclusions = []
        
        # Find explicit exclusions with - prefix
        for match in self.exclusion_pattern.finditer(query):
            exclusions.append(match.group(1))
        
        # Remove exclusion patterns from query
        query = self.exclusion_pattern.sub('', query)
        
        # Handle natural language exclusions (e.g., "not senior", "without remote")
        query_lower = query.lower()
        for exclusion_word in self.EXCLUSION_KEYWORDS:
            pattern = rf'\b{exclusion_word}\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)*)'
            for match in re.finditer(pattern, query_lower):
                exclusion_term = match.group(1)
                if exclusion_term not in ['or', 'and', 'at']:  # Skip common words
                    exclusions.append(exclusion_term)
                    # Remove from original query (case-insensitive)
                    query = re.sub(rf'\b{exclusion_word}\s+{re.escape(exclusion_term)}\b', '', query, flags=re.IGNORECASE)
        
        return list(set(exclusions)), query.strip()
    
    def _extract_or_groups(self, query: str) -> List[List[str]]:
        """
        Extract OR groups from query.
        
        Returns a list where each element is a list of terms that are ORed together.
        For "backend OR frontend", returns [['backend', 'frontend']]
        """
        # Check if query contains OR operators
        if not re.search(r'\bOR\b', query, re.IGNORECASE):
            return []
        
        # Split by OR (case-insensitive)
        parts = re.split(r'\s+OR\s+', query, flags=re.IGNORECASE)
        
        if len(parts) > 1:
            # Found OR operators - all parts form a single OR group
            or_terms = []
            for part in parts:
                part = part.strip()
                if part:
                    # Remove quotes if present (they're handled separately)
                    part = part.strip('"\'')
                    if part and len(part) > 1:
                        or_terms.append(part)
            
            if len(or_terms) > 1:
                return [or_terms]
        
        return []
    
    def _remove_or_operators(self, query: str) -> str:
        """Remove OR operators from query (used when processing AND terms)."""
        return re.sub(r'\s+OR\s+', ' ', query, flags=re.IGNORECASE).strip()
    
    def _remove_or_terms(self, query: str, or_groups: List[List[str]]) -> str:
        """Remove OR terms from query to avoid duplication in keyword extraction."""
        # Remove all OR-related content
        for or_group in or_groups:
            for term in or_group:
                # Remove the term and surrounding OR operators
                pattern = rf'\b{re.escape(term)}\s+OR\s+|\s+OR\s+{re.escape(term)}\b|\b{re.escape(term)}\b'
                query = re.sub(pattern, '', query, flags=re.IGNORECASE)
        # Clean up any remaining OR operators and extra spaces
        query = re.sub(r'\s+OR\s+', ' ', query, flags=re.IGNORECASE)
        query = re.sub(r'\s+', ' ', query).strip()
        return query
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract keywords from query (excluding stop words)."""
        # Common stop words to filter out
        stop_words = {
            'a', 'an', 'the', 'at', 'is', 'are', 'was', 'were', 'been', 'be',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should',
            'may', 'might', 'must', 'can', 'could', 'find', 'jobs', 'job',
            'position', 'positions', 'opening', 'openings', 'role', 'roles',
        }
        
        # Split into words and filter
        words = query.split()
        keywords = [
            word.strip().lower()
            for word in words
            if word.strip() and word.strip().lower() not in stop_words and len(word.strip()) > 1
        ]
        
        return keywords
    
    def _build_title_filter(self, keywords: List[str], exact_phrases: List[str], 
                           exclusions: List[str], or_groups: List[List[str]]) -> str:
        """
        Build title_filter string following Google-like search rules.
        
        Rules:
        - Keywords: space-separated = AND
        - Exact phrases: "phrase"
        - OR groups: term1 OR term2
        - Exclusions: -term or -"phrase"
        """
        parts = []
        
        # Add exact phrases
        for phrase in exact_phrases:
            parts.append(f'"{phrase}"')
        
        # Add OR groups (all OR groups are separate, ORed together conceptually)
        # But for title_filter format, we'll use "term1 OR term2" syntax
        for or_group in or_groups:
            if len(or_group) > 1:
                parts.append(' OR '.join(or_group))
            elif len(or_group) == 1:
                parts.append(or_group[0])
        
        # Add regular keywords (AND logic - space-separated)
        # Only add keywords that are NOT part of OR groups
        if keywords:
            parts.extend(keywords)
        
        # Add exclusions
        for exclusion in exclusions:
            # Check if it's a phrase (contains spaces)
            if ' ' in exclusion:
                parts.append(f'-"{exclusion}"')
            else:
                parts.append(f'-{exclusion}')
        
        # Join all parts with spaces (AND logic)
        title_filter = ' '.join(parts)
        
        return title_filter.strip()
    
    def _build_django_filters(self, keywords: List[str], exact_phrases: List[str],
                             exclusions: List[str], or_groups: List[List[str]]) -> 'Q':
        """
        Build Django Q objects for filtering job titles and skills.
        
        Returns:
            Django Q object representing the filter logic
        """
        from django.db.models import Q
        
        # Start with a base Q object (always True)
        q_filter = Q()
        
        # Handle exact phrases - must match title or skills (case-insensitive)
        if exact_phrases:
            phrase_q = Q()
            for phrase in exact_phrases:
                # Match exact phrase in title OR in skills_required
                phrase_q |= Q(title__icontains=phrase) | Q(skills_required__icontains=phrase)
            q_filter &= phrase_q
        
        # Handle OR groups and keywords together
        # If we have OR groups, combine with keywords using AND logic
        if or_groups or keywords:
            combined_q = Q()
            
            # If we have keywords, they must all be present (AND logic)
            if keywords:
                keywords_q = Q()
                for keyword in keywords:
                    # Keyword can be in title OR skills_required
                    term_q = Q(title__icontains=keyword) | Q(skills_required__icontains=keyword)
                    keywords_q &= term_q
                combined_q = keywords_q
            
            # If we have OR groups, combine with keywords
            if or_groups:
                or_group_q = Q()
                for or_group in or_groups:
                    group_q = Q()
                    for term in or_group:
                        # Term can be in title OR skills_required
                        group_q |= Q(title__icontains=term) | Q(skills_required__icontains=term)
                    or_group_q |= group_q
                
                # Combine OR groups with keywords
                if keywords:
                    # Keywords AND (OR groups)
                    combined_q = combined_q & or_group_q
                else:
                    combined_q = or_group_q
            
            q_filter &= combined_q
        
        # Handle exclusions (must not contain any exclusion terms)
        if exclusions:
            exclusion_q = Q()
            for exclusion in exclusions:
                exclusion_q |= Q(title__icontains=exclusion) | Q(skills_required__icontains=exclusion)
            q_filter &= ~exclusion_q  # Negate exclusions
        
        return q_filter
    
    def _empty_components(self) -> QueryComponents:
        """Return empty components for empty queries."""
        from django.db.models import Q
        return QueryComponents(
            title_filter='',
            django_q_filters=Q(),
            keywords=[],
            exact_phrases=[],
            exclusions=[],
            or_groups=[],
        )


def parse_query_to_search_params(user_query: str, offset: int = 0, limit: int = 100) -> Dict:
    """
    Main function to parse user query and return structured search parameters.
    
    Args:
        user_query: Natural language query from user
        offset: Offset for pagination (default: 0)
        limit: Number of results per page (default: 100, max: 100)
    
    Returns:
        Dictionary containing:
            - title_filter: String format for title filtering
            - django_q_filters: Django Q object for filtering
            - offset: Pagination offset
            - limit: Number of results (capped at 100)
            - parsed_components: Detailed parsed components
    """
    # Validate and cap limit
    limit = max(1, min(100, limit))
    offset = max(0, offset)
    
    # Parse the query
    parser = JobQueryParser()
    components = parser.parse(user_query)
    
    return {
        'title_filter': components.title_filter,
        'django_q_filters': components.django_q_filters,
        'offset': offset,
        'limit': limit,
        'parsed_components': {
            'keywords': components.keywords,
            'exact_phrases': components.exact_phrases,
            'exclusions': components.exclusions,
            'or_groups': components.or_groups,
        }
    }
