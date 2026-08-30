import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def legal_format(value):
    """Render plain legal text with escaped paragraphs and numbered headings."""
    blocks = [block.strip() for block in str(value or "").split("\n\n") if block.strip()]
    rendered = []
    for index, block in enumerate(blocks):
        safe = escape(block).replace("\n", "<br>")
        if index == 0:
            rendered.append(f"<h2>{safe}</h2>")
        elif re.match(r"^\d+\.\s+", block):
            rendered.append(f"<h3>{safe}</h3>")
        else:
            rendered.append(f"<p>{safe}</p>")
    return mark_safe("".join(rendered))
