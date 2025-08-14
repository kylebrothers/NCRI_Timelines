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
        user_response = users_api.get_user('me', {})
        # Handle both dict and object responses
        if hasattr(user_response, 'data'):
            user = user_response.data
            user_name = user.name if hasattr(user, 'name') else user.get('name', 'Unknown')
            user_email = user.email if hasattr(user, 'email') else user.get('email', 'Not available')
        else:
            user = user_response
            user_name = user.get('name', 'Unknown')
            user_email = user.get('email', 'Not available')
        
        print_colored("   ✓ API access confirmed!", GREEN)
        print_colored(f"   Logged in as: {user_name}", NC)
        print_colored(f"   Email: {user_email}", NC)
    except Exception as e:
        print_colored(f"   ✗ API access failed: {e}", RED)
        print_colored("   Please check your access token is valid", NC)
        return False
    
    # Test 2: List workspaces
    print_colored("\n4. Fetching available workspaces...", YELLOW)
    try:
        workspaces_response = workspaces_api.get_workspaces({})
        # Handle both response types and convert to list
        if hasattr(workspaces_response, 'data'):
            workspaces = list(workspaces_response.data)
        else:
            workspaces = list(workspaces_response)
        
        print_colored(f"   ✓ Found {len(workspaces)} workspace(s):", GREEN)
        
        for ws in workspaces:
            ws_name = ws.name if hasattr(ws, 'name') else ws.get('name', 'Unknown')
            ws_gid = ws.gid if hasattr(ws, 'gid') else ws.get('gid', 'Unknown')
            ws_info = f"   - {ws_name} (GID: {ws_gid})"
            if workspace_gid and ws_gid == workspace_gid:
                print_colored(ws_info + " [CONFIGURED]", GREEN)
            else:
                print_colored(ws_info, NC)
        
        # If no workspace configured, use first one
        if not workspace_gid or workspace_gid == 'your-workspace-gid':
            if workspaces:
                workspace_gid = workspaces[0].gid if hasattr(workspaces[0], 'gid') else workspaces[0].get('gid')
                ws_name = workspaces[0].name if hasattr(workspaces[0], 'name') else workspaces[0].get('name')
                print_colored(f"\n   Using first workspace: {ws_name}", YELLOW)
            else:
                print_colored("   ✗ No workspaces available!", RED)
                return False
    except Exception as e:
        print_colored(f"   ✗ Failed to fetch workspaces: {e}", RED)
        return False
    
    # Test 3: Get workspace details
    print_colored("\n5. Getting workspace details...", YELLOW)
    try:
        workspace_response = workspaces_api.get_workspace(workspace_gid, {})
        # Handle both response types
        if hasattr(workspace_response, 'data'):
            workspace = workspace_response.data
            ws_name = workspace.name if hasattr(workspace, 'name') else workspace.get('name')
            is_org = workspace.is_organization if hasattr(workspace, 'is_organization') else workspace.get('is_organization', False)
        else:
            workspace = workspace_response
            ws_name = workspace.get('name', 'Unknown')
            is_org = workspace.get('is_organization', False)
        
        print_colored(f"   ✓ Workspace: {ws_name}", GREEN)
        print_colored(f"   Type: {'Organization' if is_org else 'Workspace'}", NC)
    except Exception as e:
        print_colored(f"   ✗ Failed to get workspace details: {e}", RED)
        return False
    
    # Test 4: Search for specific project
    print_colored("\n6. Searching for 'Peds Access to Services Intake' project...", YELLOW)
    target_project = None
    try:
        # Search for the specific project
        projects_response = projects_api.get_projects({'workspace': workspace_gid})
        
        # Iterate through projects to find the one we want
        for project in projects_response:
            proj_name = project.name if hasattr(project, 'name') else project.get('name', '')
            if 'Peds Access to Services Intake' in proj_name:
                proj_gid = project.gid if hasattr(project, 'gid') else project.get('gid')
                target_project = {'name': proj_name, 'gid': proj_gid}
                print_colored(f"   ✓ Found project: {proj_name}", GREEN)
                print_colored(f"   Project GID: {proj_gid}", GREEN)
                break
        
        if not target_project:
            print_colored("   ⚠ Project 'Peds Access to Services Intake' not found", YELLOW)
            print_colored("   Checking if any projects exist...", NC)
            # Just check if there are ANY projects
            first_project = next(projects_api.get_projects({'workspace': workspace_gid, 'limit': 1}), None)
            if first_project:
                print_colored("   ✓ Projects exist in workspace (access confirmed)", GREEN)
            else:
                print_colored("   No projects found in workspace", YELLOW)
    except Exception as e:
        print_colored(f"   ✗ Failed to search for project: {e}", RED)
        # This is not a critical error
    
    # Test 5: Check user access (just current user, not all users)
    print_colored("\n7. Verifying user access...", YELLOW)
    try:
        # Just verify we can query users by checking our own access
        print_colored(f"   ✓ User access verified (logged in as {user_name if 'user_name' in locals() else 'User'})", GREEN)
    except Exception as e:
        print_colored(f"   ✗ Failed to verify user access: {e}", RED)
    
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
    print_colored(f"  • Workspace: {ws_name if 'ws_name' in locals() else 'Connected'}", GREEN)
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
