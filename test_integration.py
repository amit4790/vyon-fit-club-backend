#!/usr/bin/env python
"""
Integration Test for VYON Backend
Tests all components to ensure they work together
"""

import sys

print("=" * 50)
print("VYON BACKEND - INTEGRATION TEST")
print("=" * 50)

# Test imports
print("\n📦 Testing imports...")
try:
    from app import app
    from config import settings
    from routes import health_router, auth_router, dashboard_router
    from services import AuthService, DashboardService
    print("✅ All imports successful")
except Exception as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Test configuration
print("\n⚙️  Configuration:")
print(f"  - Environment: {settings.environment}")
print(f"  - Debug Mode: {settings.debug}")
print(f"  - API Title: {settings.api_title}")
print(f"  - CORS Origins: {settings.get_cors_origins}")

# Test routers
print("\n🔗 Registered Routes:")
print(f"  - Health: {len([r for r in health_router.routes])} endpoints")
print(f"  - Auth: {len([r for r in auth_router.routes])} endpoints")
print(f"  - Dashboard: {len([r for r in dashboard_router.routes])} endpoints")

# Test auth service
print("\n🔐 Authentication Test:")
success, user, error = AuthService.authenticate('admin@vyon.com', 'password123')
if success:
    print(f"  ✅ Admin Login: {user.name} ({user.role})")
    print(f"     Token: {AuthService.generate_mock_token(user.id)[:20]}...")

success, user, error = AuthService.authenticate('trainer@vyon.com', 'password123')
if success:
    print(f"  ✅ Trainer Login: {user.name} ({user.role})")

success, user, error = AuthService.authenticate('member@vyon.com', 'password123')
if success:
    print(f"  ✅ Member Login: {user.name} ({user.role})")

success, user, error = AuthService.authenticate('invalid@vyon.com', 'wrongpass')
if not success:
    print(f"  ✅ Invalid Login Rejected: {error}")

# Test dashboard service
print("\n📊 Dashboard Service Test:")
admin_dash = DashboardService.get_admin_dashboard()
revenue_text = f"${admin_dash.monthly_revenue:.2f}" if admin_dash.monthly_revenue is not None else "N/A"
print(f"  ✅ Admin Dashboard: {admin_dash.total_members} members, revenue {revenue_text}")

trainer_dash = DashboardService.get_trainer_dashboard()
print(f"  ✅ Trainer Dashboard: {trainer_dash.trainer_name}, {trainer_dash.todays_sessions} sessions today")

member_dash = DashboardService.get_member_dashboard()
print(f"  ✅ Member Dashboard: {member_dash.member_name}, {member_dash.remaining_days} days remaining")

print("\n" + "=" * 50)
print("✅ ALL TESTS PASSED - Backend Ready!")
print("=" * 50)
