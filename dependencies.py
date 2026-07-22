"""
Dependency Injection
Centralized dependencies for request handling
"""

from typing import Optional


class RequestContext:
    """Context object for request information"""
    
    def __init__(self, user_role: Optional[str] = None, user_id: Optional[str] = None):
        self.user_role = user_role
        self.user_id = user_id


def get_request_context() -> RequestContext:
    """
    Get the current request context
    Can be extended with authentication later
    """
    return RequestContext()
