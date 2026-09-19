import re

def sanitize_custom_css(css_text: str) -> str:
    """
    Sanitize custom CSS input to prevent Stored XSS, HTML tag breakout, and malicious execution.
    - Strips all HTML tags including </style>, <script>, etc.
    - Disallows javascript:, expression(), and @import directives.
    """
    if not css_text:
        return ""
    
    # 1. Strip all < and > characters to completely prevent HTML tag injection and breakout
    sanitized = re.sub(r'[<>]', '', str(css_text))
    
    # 2. Neutralize javascript: and vbscript: URLs
    sanitized = re.sub(r'(?i)javascript\s*:', 'blocked-javascript:', sanitized)
    sanitized = re.sub(r'(?i)vbscript\s*:', 'blocked-vbscript:', sanitized)
    
    # 3. Neutralize IE dynamic CSS expressions
    sanitized = re.sub(r'(?i)expression\s*\(', 'blocked-expression(', sanitized)
    
    # 4. Block external @import to prevent loading arbitrary remote hostile stylesheets
    sanitized = re.sub(r'(?i)@\s*import', '/* blocked @import */', sanitized)
    
    return sanitized.strip()
