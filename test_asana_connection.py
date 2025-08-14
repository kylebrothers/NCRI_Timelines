#!/usr/bin/env python3
"""
Simple Asana API connection test script
Tests API access by fetching workspace info and listing projects
"""

import os
import sys
import json
from dotenv import load_dotenv
import asana
from datetime import datetime

# Color codes for terminal output
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'  # No Color

def print_colored(message, color=NC):
    """Print colored message to terminal"""
    print(f"{color}{message}{NC}")

def test_asana_connection():
    """Test Asana API connection and basic operations"""
    
    print_colored("\n" + "="*60, BLUE)
    print_colored("       ASANA API CONNECTION TEST", BLUE)
    print_colored("="*60 + "\n", BLUE)
    
    # Load environment variables
    print_colored("1. Loading environment variables...", YELLOW)
    
    # Try multiple locations for .env file
    env_paths = ['.env', '../.env', '../../.env']
    env_loaded = False
    
    for path in env_paths:
        if os.path.exists(path):
            load_dotenv(path)
            print_colored(f"   ✓ Loaded from {path}", GREEN)
            env_loaded = True
            break
    
    if not env_loaded:
        print_colored("   ✗ No .env file found!", RED)
        print_colored("   Please create a .env file with:", NC)
        print_colored("     ASANA_ACCESS_TOKEN=your-token-here", NC)
        print_colored("     ASANA_WORKSPACE_GID=your-workspace-gid (optional)", NC)
        return False
    
    # Get API credentials
    access_token = os.environ.get('ASANA_ACCESS_TOKEN')
    workspace_gid = os.environ.get('ASANA_WORKSPACE_GID')
    
    # Check if token exists
    if not access_token or access_token == 'your-asana-personal-access-token':
        print_colored("   ✗ ASANA_ACCESS_TOKEN not configured!", RED)
        print_colored("   Please add your Asana Personal Access Token to .env", NC)
        return False
    
    # Show token info (masked)
    masked_token = access_token[:4] + '*' * (len(access_token) - 8) + access_token[-4:]
    print_colored(f"   Token: {masked_token}", NC)
    if workspace_gid and workspace_gid != 'your-workspace-gid':
        print_colored(f"   Workspace GID: {workspace_gid}", NC)
    
    # Initialize Asana client
    print_colored("\n2. Initializing Asana client...", YELLOW)
    try:
        configuration = asana.Configuration()
        configuration.access_token = access_token
        api_client = asana.ApiClient(configuration)
        
        # Create API instances
        users_api = asana.UsersApi(api_client)
        workspaces_api = asana.WorkspacesApi(api_client)
        projects_api = asana.ProjectsApi(api_client)
        tasks_api = asana.TasksApi(api_client)
        
        print_colored("   ✓ Client initialized", GREEN)
    except Exception as e:
        print_colored(f"   ✗ Failed to initialize client: {e}", RED)
        return False
    
    # Test 1: Get current user
    print_colored("\n3. Testing API access - Getting current user...", YELLOW)
    try:
        user = users_api.get_user('me', {})
        print_colored("   ✓ API access confirmed!", GREEN)
        print_colored(f"   Logged in as: {user.data.name}", NC)
        print_colored(f"   Email: {user.data.email if hasattr(user.data, 'email') else 'Not available'}", NC)
    except Exception as e:
        print_colored(f"   ✗ API access failed: {e}", RED)
        print_colored("   Please check your access token is valid", NC)
        return False
    
    # Test 2: List workspaces
    print_colored("\n4. Fetching available workspaces...", YELLOW)
    try:
        workspaces_response = workspaces_api.get_workspaces({})
        workspaces = workspaces_response.data
        print_colored(f"   ✓ Found {len(workspaces)} workspace(s):", GREEN)
        
        for ws in workspaces:
            ws_info = f"   - {ws.name} (GID: {ws.gid})"
            if workspace_gid and ws.gid == workspace_gid:
                print_colored(ws_info + " [CONFIGURED]", GREEN)
            else:
                print_colored(ws_info, NC)
        
        # If no workspace configured, use first one
        if not workspace_gid or workspace_gid == 'your-workspace-gid':
            if workspaces:
                workspace_gid = workspaces[0].gid
                print_colored(f"\n   Using first workspace: {workspaces[0].name}", YELLOW)
            else:
                print_colored("   ✗ No workspaces available!", RED)
                return False
    except Exception as e:
        print_colored(f"   ✗ Failed to fetch workspaces: {e}", RED)
        return False
    
    # Test 3: Get workspace details
    print_colored("\n5. Getting workspace details...", YELLOW)
    try:
        workspace = workspaces_api.get_workspace(workspace_gid, {})
        print_colored(f"   ✓ Workspace: {workspace.data.name}", GREEN)
        print_colored(f"   Type: {'Organization' if getattr(workspace.data, 'is_organization', False) else 'Workspace'}", NC)
    except Exception as e:
        print_colored(f"   ✗ Failed to get workspace details: {e}", RED)
        return False
    
    # Test 4: List projects
    print_colored("\n6. Fetching projects...", YELLOW)
    try:
        projects_response = projects_api.get_projects({'workspace': workspace_gid, 'limit': 5})
        projects = projects_response.data
        print_colored(f"   ✓ Found {len(projects)} project(s) (showing max 5):", GREEN)
        
        if projects:
            for project in projects:
                print_colored(f"   - {project.name}", NC)
        else:
            print_colored("   No projects found (this is normal for new workspaces)", YELLOW)
    except Exception as e:
        print_colored(f"   ✗ Failed to fetch projects: {e}", RED)
        # This is not a critical error
    
    # Test 5: List users
    print_colored("\n7. Fetching workspace users...", YELLOW)
    try:
        users_response = users_api.get_users({'workspace': workspace_gid, 'limit': 5})
        users = users_response.data
        print_colored(f"   ✓ Found {len(users)} user(s) (showing max 5):", GREEN)
        
        for user in users:
            print_colored(f"   - {user.name}", NC)
    except Exception as e:
        print_colored(f"   ✗ Failed to fetch users: {e}", RED)
        # This is not a critical error
    
    # Test 6: Try to create a test task (optional)
    print_colored("\n8. Testing write access...", YELLOW)
    try:
        # Create a test task
        task_data = {
            'data': {
                'name': f'API Test Task - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                'notes': 'This is a test task created by the API connection test script.',
                'workspace': workspace_gid
            }
        }
        
        test_task = tasks_api.create_task(task_data, {})
        print_colored("   ✓ Successfully created test task", GREEN)
        print_colored(f"   Task GID: {test_task.data.gid}", NC)
        
        # Delete the test task
        tasks_api.delete_task(test_task.data.gid, {})
        print_colored("   ✓ Successfully deleted test task", GREEN)
        print_colored("   Write access confirmed!", GREEN)
    except Exception as e:
        print_colored(f"   ⚠ Could not test write access: {e}", YELLOW)
        print_colored("   This might be due to permissions or project requirements", NC)
    
    # Summary
    print_colored("\n" + "="*60, GREEN)
    print_colored("       ✓ API CONNECTION TEST SUCCESSFUL!", GREEN)
    print_colored("="*60, GREEN)
    
    print_colored("\nSummary:", BLUE)
    print_colored(f"  • API Token: Valid", GREEN)
    print_colored(f"  • Workspace: {workspace.data.name}", GREEN)
    print_colored(f"  • Access Level: {'Read/Write' if 'test_task' in locals() else 'Read'}", GREEN)
    print_colored(f"  • Projects Available: {len(projects) if 'projects' in locals() else 0}", NC)
    print_colored(f"  • Users in Workspace: {len(users) if 'users' in locals() else 0}", NC)
    
    print_colored("\nYour Asana API connection is working correctly! ✓\n", GREEN)
    
    # Save configuration suggestion
    if not os.environ.get('ASANA_WORKSPACE_GID') or os.environ.get('ASANA_WORKSPACE_GID') == 'your-workspace-gid':
        print_colored("💡 Tip: Add this to your .env file:", YELLOW)
        print_colored(f"   ASANA_WORKSPACE_GID={workspace_gid}", NC)
        print_colored("")
    
    return True

def main():
    """Main entry point"""
    try:
        # Check if asana library is installed
        try:
            import asana
        except ImportError:
            print_colored("✗ Asana library not installed!", RED)
            print_colored("Please install it with:", NC)
            print_colored("  pip install python-asana", YELLOW)
            print_colored("  or", NC)
            print_colored("  make install", YELLOW)
            sys.exit(1)
        
        # Check if dotenv is installed
        try:
            from dotenv import load_dotenv
        except ImportError:
            print_colored("✗ python-dotenv not installed!", RED)
            print_colored("Please install it with:", NC)
            print_colored("  pip install python-dotenv", YELLOW)
            sys.exit(1)
        
        # Run the test
        success = test_asana_connection()
        
        # Exit with appropriate code
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print_colored("\n\n✗ Test interrupted by user", YELLOW)
        sys.exit(130)
    except Exception as e:
        print_colored(f"\n✗ Unexpected error: {e}", RED)
        sys.exit(1)

if __name__ == "__main__":
    main()
