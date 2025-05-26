from supabase import create_client, Client
import os

# Load environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Function to link a LeetCode user to a Discord ID
def link_leetcode_user(discord_id: str, leetcode_username: str, private_channel_id: int = None):
    data, count = supabase.table("users").upsert({
        "discord_id": discord_id,
        "leetcode_username": leetcode_username,
        "private_channel_id": private_channel_id 
    }).execute()
    return data, count

# Function to get user data by Discord ID
def get_user(discord_id: str):
    data = supabase.table("users").select("*").eq("discord_id", discord_id).execute()
    if data.data:
        return data.data[0]
    return None

# Add more functions as needed (e.g., update progress, fetch leaderboard, etc.)
