import discord
from discord import app_commands
from discord.ext import commands
import os
from flask import Flask
from threading import Thread

# --- WEB SERVER FOR RENDER/UPTIMEROBOT ---
app = Flask('')

@app.route('/')
def home():
    return "I am alive!"

def run():
    # Render uses the PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- BOT CONFIGURATION ---
class BountyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True 
        # Setting a custom activity status
        super().__init__(
            command_prefix="!", 
            intents=intents,
            activity=discord.Game(name="Hunting Outlaws...")
        )

    async def setup_hook(self):
        await self.tree.sync()
        print(f"Synced slash commands for {self.user}")

bot = BountyBot()

active_bounty = {
    "target_discord": None,
    "target_mc": None,
    "reward": None,
    "setter": None,
    "proof_url": None
}

# --- SLASH COMMANDS ---

@bot.tree.command(name="set_bounty", description="Place a bounty on a player.")
@app_commands.describe(target_discord="Discord user", target_mc="MC Username", reward="Prize")
async def set_bounty(interaction: discord.Interaction, target_discord: discord.Member, target_mc: str, reward: str):
    global active_bounty
    if active_bounty["target_discord"] is not None:
        await interaction.response.send_message(f"❌ A bounty is already active!", ephemeral=True)
        return
    if target_discord == interaction.user:
        await interaction.response.send_message("You cannot put a bounty on yourself!", ephemeral=True)
        return

    active_bounty = {
        "target_discord": target_discord, "target_mc": target_mc,
        "reward": reward, "setter": interaction.user, "proof_url": None
    }
    embed = discord.Embed(title="⚔️ WANTED", color=discord.Color.dark_red())
    embed.add_field(name="Target (MC)", value=f"`{target_mc}`", inline=True)
    embed.add_field(name="Target (Discord)", value=target_discord.mention, inline=True)
    embed.add_field(name="Reward", value=f"💰 {reward}", inline=False)
    embed.set_thumbnail(url=target_discord.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="status", description="Check the details of the currently active bounty")
async def status(interaction: discord.Interaction):
    if active_bounty["target_discord"] is None:
        await interaction.response.send_message("There are currently no active bounties.", ephemeral=True)
        return
    embed = discord.Embed(title="📜 Current Bounty Details", color=discord.Color.blue())
    embed.add_field(name="Target", value=f"`{active_bounty['target_mc']}` ({active_bounty['target_discord'].mention})", inline=False)
    embed.add_field(name="Reward", value=active_bounty['reward'], inline=True)
    embed.add_field(name="Placed By", value=active_bounty['setter'].mention, inline=True)
    if active_bounty["proof_url"]:
        embed.set_footer(text="⚠️ A claim has been submitted!")
        embed.set_image(url=active_bounty["proof_url"])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="claim", description="Submit proof of the hunt")
async def claim(interaction: discord.Interaction, mc_username: str, proof_image: discord.Attachment):
    global active_bounty
    if active_bounty["target_discord"] is None:
        await interaction.response.send_message("No active bounties.", ephemeral=True)
        return
    if interaction.user.id == active_bounty["target_discord"].id:
        await interaction.response.send_message("🛑 You cannot claim a bounty on yourself.", ephemeral=True)
        return
    active_bounty["proof_url"] = proof_image.url
    await interaction.response.send_message(f"🚩 {interaction.user.mention} (`{mc_username}`) has submitted proof! Check `/status`.")

@bot.tree.command(name="cancel", description="Cancel the current bounty (Setter or Mod only)")
async def cancel(interaction: discord.Interaction):
    global active_bounty
    if active_bounty["target_discord"] is None:
        await interaction.response.send_message("Nothing to cancel.", ephemeral=True)
        return
    is_setter = interaction.user.id == active_bounty["setter"].id
    is_mod = interaction.user.guild_permissions.manage_messages
    if not (is_setter or is_mod):
        await interaction.response.send_message("Only the setter or a Mod can cancel.", ephemeral=True)
        return
    target_name = active_bounty["target_mc"]
    for key in active_bounty: active_bounty[key] = None
    await interaction.response.send_message(f"🚫 The bounty on `{target_name}` has been cancelled.")

@bot.tree.command(name="finalize", description="Confirm the kill (Mod Only)")
@app_commands.checks.has_permissions(manage_messages=True)
async def finalize(interaction: discord.Interaction, winner_discord: discord.Member, winner_mc: str):
    global active_bounty
    if active_bounty["target_discord"] is None:
        await interaction.response.send_message("No active bounty.", ephemeral=True)
        return
    embed = discord.Embed(title="🏆 HUNT COMPLETE", color=discord.Color.green())
    embed.description = f"**{active_bounty['target_mc']}** neutralized by {winner_discord.mention} (`{winner_mc}`)!"
    embed.add_field(name="Reward", value=active_bounty["reward"])
    for key in active_bounty: active_bounty[key] = None
    await interaction.response.send_message(embed=embed)

# --- START THE BOT ---
if __name__ == "__main__":
    token = os.environ.get('DISCORD_TOKEN')
    if token:
        keep_alive()  # This starts the Flask web server
        bot.run(token)
    else:
        print("ERROR: No DISCORD_TOKEN found in environment variables.")
