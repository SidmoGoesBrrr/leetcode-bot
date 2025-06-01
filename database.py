from supabase import create_client, Client
import os

# Load environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Link LeetCode username to Discord ID
def link_leetcode_user(discord_id: str, leetcode_username: str):
    data, count = supabase.table("users").upsert({
        "discord_id": discord_id,
        "leetcode_username": leetcode_username,
    }).execute()
    return data, count

# Get user by Discord ID
def get_user(discord_id: str):
    data = supabase.table("users").select("*").eq("discord_id", discord_id).execute()
    if data.data:
        return data.data[0]
    return None

# Get all users for leaderboard
def get_all_users():
    data = supabase.table("users").select("*").execute()
    return data.data

# Update user progress (streak, total_solved, etc.)
def update_user(discord_id: str, updates: dict):
    supabase.table("users").update(updates).eq("discord_id", discord_id).execute()

# OPTIONAL: Create a new user if not exists (for registration)
def create_user(discord_id: str, leetcode_username: str):
    existing = get_user(discord_id)
    if not existing:
        supabase.table("users").insert({
            "discord_id": discord_id,
            "leetcode_username": leetcode_username,
            "streak_count": 0,
            "last_solved_date": None,
            "total_solved": 0
        }).execute()
