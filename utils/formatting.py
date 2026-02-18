"""Output formatting utilities for DoD budget tools.

Provides reusable functions for:
- Formatting currency amounts
- Text snippet extraction and highlighting
- Tabular report output
- Data serialization for display
"""

from typing import Optional, List, Dict, Any


def format_amount(value: Optional[float], precision: int = 0,
                 thousands_sep: bool = True) -> str:
    """Format a dollar amount for display.

    Args:
        value: Amount in dollars (can be None or 0)
        precision: Decimal places (default: 0 for whole dollars)
        thousands_sep: Add thousands separator (default: True)

    Returns:
        Formatted string like "$1,234,567" or "$1.23M"

    Examples:
        format_amount(1234567) -> "$1,234,567"
        format_amount(1234567, precision=2) -> "$1,234,567.00"
        format_amount(None) -> "-"
    """
    if value is None or value == 0:
        return "-"

    # For very large amounts, use compact notation
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"

    # Standard currency format
    if thousands_sep:
        return f"${value:,.{precision}f}"
    else:
        return f"${value:.{precision}f}"


def format_percent(value: Optional[float], precision: int = 1) -> str:
    """Format a percentage for display.

    Args:
        value: Percentage value (0.0 to 100.0)
        precision: Decimal places (default: 1)

    Returns:
        Formatted string like "42.5%"

    Examples:
        format_percent(42.5) -> "42.5%"
        format_percent(0) -> "0.0%"
        format_percent(None) -> "-"
    """
    if value is None:
        return "-"
    return f"{value:.{precision}f}%"


def format_count(value: Optional[int]) -> str:
    """Format a count with thousands separator.

    Args:
        value: Integer count

    Returns:
        Formatted string like "1,234,567"

    Examples:
        format_count(1234567) -> "1,234,567"
        format_count(123) -> "123"
        format_count(None) -> "-"
    """
    if value is None:
        return "-"
    return f"{value:,d}"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to maximum length with ellipsis.

    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add if truncated (default: "...")

    Returns:
        Truncated text if longer than max_length, original text otherwise

    Examples:
        truncate_text("Long text here", 10) -> "Long te..."
        truncate_text("Short", 10) -> "Short"
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def extract_snippet(text: str, query_terms: List[str], context_chars: int = 80,
                   max_length: int = 300) -> str:
    """Extract text snippet around query terms with context.

    Finds the first occurrence of any query term and extracts a snippet
    with surrounding context.

    Args:
        text: Full text to extract from
        query_terms: List of terms to search for
        context_chars: Characters of context before/after term
        max_length: Maximum snippet length

    Returns:
        Snippet string with ellipsis if truncated

    Examples:
        extract_snippet("The missile defense system is important",
                       ["defense"], 20, 50)
        -> "...ile defense system..."
    """
    if not text or not query_terms:
        return text[:max_length]

    text_lower = text.lower()

    # Find first occurrence of any term
    best_pos = len(text)
    for term in query_terms:
        pos = text_lower.find(term.lower())
        if pos != -1 and pos < best_pos:
            best_pos = pos

    # Extract context around the term
    start = max(0, best_pos - context_chars)
    end = min(len(text), best_pos + context_chars)

    snippet = text[start:end].strip()

    # Add ellipsis if needed
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return truncate_text(snippet, max_length, "...")


def highlight_terms(text: str, terms: List[str], marker: str = ">>>") -> str:
    """Highlight search terms in text.

    Simple text highlighting by wrapping terms with markers.
    Case-insensitive search, preserves original case in output.

    Args:
        text: Text to highlight
        terms: List of terms to highlight
        marker: Marker to use (default: ">>>")

    Returns:
        Text with terms highlighted like ">>>term<<<"

    Examples:
        highlight_terms("The missile defense system", ["defense"])
        -> "The missile >>>defense<<< system"
    """
    result = text
    for term in terms:
        # Case-insensitive replacement
        import re
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        replacement = f"{marker}\\g<0>{marker}"
        result = pattern.sub(replacement, result)
    return result


class TableFormatter:
    """Formats data as aligned tabular output."""

    def __init__(self, columns: List[str], column_widths: Optional[List[int]] = None):
        """Initialize table formatter.

        Args:
            columns: List of column headers
            column_widths: Optional list of column widths (auto-calculated if None)
        """
        self.columns = columns
        self.column_widths = column_widths or [len(col) for col in columns]
        self.rows: List[List[str]] = []

    def add_row(self, values: List[Any]) -> None:
        """Add a row to the table.

        Args:
            values: List of values matching column count

        Raises:
            ValueError: If value count doesn't match column count
        """
        if len(values) != len(self.columns):
            raise ValueError(f"Expected {len(self.columns)} values, got {len(values)}")

        # Convert to strings and track widths
        str_values = []
        for i, val in enumerate(values):
            str_val = str(val) if val is not None else "-"
            str_values.append(str_val)
            # Update column width if needed
            if len(str_val) > self.column_widths[i]:
                self.column_widths[i] = len(str_val)

        self.rows.append(str_values)

    def _format_row(self, values: List[str], is_header: bool = False) -> str:
        """Format a single row as aligned text.

        Args:
            values: List of cell values
            is_header: If True, use header alignment (left)

        Returns:
            Formatted row string
        """
        cells = []
        for i, val in enumerate(values):
            width = self.column_widths[i]
            # Headers are left-aligned, data is right-aligned for numbers, left for text
            if is_header:
                cells.append(val.ljust(width))
            else:
                # Try to right-align if numeric
                try:
                    float(val)
                    cells.append(val.rjust(width))
                except ValueError:
                    cells.append(val.ljust(width))

        return "  ".join(cells)

    def to_string(self, show_header: bool = True, show_separator: bool = True) -> str:
        """Format table as multi-line string.

        Args:
            show_header: Include header row (default: True)
            show_separator: Add separator line after header (default: True)

        Returns:
            Formatted table as string
        """
        lines = []

        if show_header:
            lines.append(self._format_row(self.columns, is_header=True))
            if show_separator:
                sep = "  ".join("-" * w for w in self.column_widths)
                lines.append(sep)

        for row in self.rows:
            lines.append(self._format_row(row))

        return "\n".join(lines)

    def print_table(self, show_header: bool = True, show_separator: bool = True) -> None:
        """Print table to stdout.

        Args:
            show_header: Include header row (default: True)
            show_separator: Add separator line after header (default: True)
        """
        print(self.to_string(show_header, show_separator))


class ReportFormatter:
    """Formats data as a structured report with sections."""

    def __init__(self, title: str = ""):
        """Initialize report formatter.

        Args:
            title: Report title
        """
        self.title = title
        self.sections: List[Dict[str, Any]] = []

    def add_section(self, heading: str, content: Any, level: int = 1) -> None:
        """Add a section to the report.

        Args:
            heading: Section heading
            content: Section content (string, list, dict, or callable)
            level: Heading level (1-3) for indentation
        """
        self.sections.append({
            "heading": heading,
            "content": content,
            "level": level
        })

    def _format_content(self, content: Any) -> List[str]:
        """Format section content as lines.

        Args:
            content: Content to format

        Returns:
            List of formatted lines
        """
        if isinstance(content, str):
            return [content]

        if isinstance(content, (list, tuple)):
            return [f"  • {item}" for item in content]

        if isinstance(content, dict):
            lines = []
            for key, value in content.items():
                lines.append(f"  {key}: {value}")
            return lines

        if callable(content):
            return self._format_content(content())

        return [str(content)]

    def to_string(self) -> str:
        """Format report as multi-line string.

        Returns:
            Formatted report
        """
        lines = []

        if self.title:
            lines.append(self.title)
            lines.append("=" * len(self.title))
            lines.append("")

        for section in self.sections:
            indent = "  " * (section["level"] - 1)
            heading = section["heading"]
            content = section["content"]

            # Format heading
            if section["level"] == 1:
                lines.append(heading)
                lines.append("-" * len(heading))
            elif section["level"] == 2:
                lines.append(f"  {heading}")
            else:
                lines.append(f"    • {heading}")

            # Format content
            content_lines = self._format_content(content)
            lines.extend(content_lines)
            lines.append("")

        return "\n".join(lines)

    def print_report(self) -> None:
        """Print report to stdout."""
        print(self.to_string())
