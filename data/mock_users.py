"""
Mock Users Database
Temporary user data for Phase 4 development
"""

from typing import Optional, Dict, Any


class MockUser:
    """Mock user model"""
    
    def __init__(self, id: str, name: str, email: str, password: str, role: str):
        self.id = id
        self.name = name
        self.email = email
        self.password = password
        self.role = role


# Mock users for authentication
MOCK_USERS = {
    "admin@vyon.com": MockUser(
        id="admin_001",
        name="John Doe",
        email="admin@vyon.com",
        password="password123",
        role="admin"
    ),
    "trainer@vyon.com": MockUser(
        id="trainer_001",
        name="Sarah Mitchell",
        email="trainer@vyon.com",
        password="password123",
        role="trainer"
    ),
    "member@vyon.com": MockUser(
        id="member_001",
        name="Robert Wilson",
        email="member@vyon.com",
        password="password123",
        role="member"
    ),
}


def get_user_by_email(email: str) -> Optional[MockUser]:
    """Retrieve user by email"""
    return MOCK_USERS.get(email)


def verify_credentials(email: str, password: str) -> Optional[MockUser]:
    """Verify user credentials"""
    user = get_user_by_email(email)
    if user and user.password == password:
        return user
    return None
