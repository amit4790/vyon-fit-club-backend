"""
Mock data for VYON FIT CLUB demo.
This file contains sample data using Python dictionaries and lists.
"""

# Mock Admin Data
admin_data = {
    "id": 1,
    "name": "Admin User",
    "email": "admin@vyonfitclub.com",
    "role": "admin",
    "dashboard_stats": {
        "total_members": 150,
        "active_trainers": 12,
        "revenue_month": "$15,000",
        "occupancy_rate": "85%"
    }
}

# Mock Trainer Data
trainers_data = [
    {
        "id": 1,
        "name": "John Smith",
        "email": "john@vyonfitclub.com",
        "specialization": "Strength Training",
        "clients": 8,
        "rating": 4.8
    },
    {
        "id": 2,
        "name": "Sarah Johnson",
        "email": "sarah@vyonfitclub.com",
        "specialization": "Cardio & HIIT",
        "clients": 10,
        "rating": 4.9
    },
    {
        "id": 3,
        "name": "Mike Davis",
        "email": "mike@vyonfitclub.com",
        "specialization": "Flexibility & Yoga",
        "clients": 6,
        "rating": 4.7
    }
]

# Mock Member Data
members_data = [
    {
        "id": 1,
        "name": "Alice Wilson",
        "email": "alice@email.com",
        "membership_type": "Premium",
        "join_date": "2023-01-15",
        "status": "active"
    },
    {
        "id": 2,
        "name": "Bob Johnson",
        "email": "bob@email.com",
        "membership_type": "Standard",
        "join_date": "2023-06-20",
        "status": "active"
    },
    {
        "id": 3,
        "name": "Carol Martinez",
        "email": "carol@email.com",
        "membership_type": "Premium",
        "join_date": "2023-03-10",
        "status": "active"
    }
]

# Mock classes/programs data
classes_data = [
    {
        "id": 1,
        "name": "Morning Yoga",
        "trainer": "Sarah Johnson",
        "schedule": "Mon, Wed, Fri - 6:00 AM",
        "capacity": 20,
        "enrolled": 18
    },
    {
        "id": 2,
        "name": "Evening Strength",
        "trainer": "John Smith",
        "schedule": "Tue, Thu - 6:30 PM",
        "capacity": 25,
        "enrolled": 22
    },
    {
        "id": 3,
        "name": "HIIT Bootcamp",
        "trainer": "Sarah Johnson",
        "schedule": "Wed, Sat - 7:00 AM",
        "capacity": 15,
        "enrolled": 14
    }
]
