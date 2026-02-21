import discord
from discord import app_commands
from discord.ext import commands
import os
import aiohttp
from io import BytesIO
from PIL import Image, ImageDraw, ImageOps
from flask import Flask
from threading import Thread

# --- WEB SERVER FOR RENDER/UPTIMEROBOT ---
app = Flask('')

@app.route('/')
def home():
    return "Bounty Board is Online!"

def run():
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
        self.session = None 
        super().__init__(
            command_prefix="!", 
            intents=intents,
            activity=discord.Game(name="Hunting Outlaws...")
        )

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
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

# --- HELPER FUNCTION: DECORATED POSTER ---
async def create_wanted_poster(avatar_url, mc_name):
    try:
        async with bot.session.get(avatar_url) as resp:
            if resp.status != 200: return None
            data = await resp.read()
        
        avatar = Image.open(BytesIO(data)).convert("RGBA")
        poster = Image.new('RGB', (400, 550), color=(225, 198, 153))
        draw = ImageDraw.Draw(poster)
        
        # Decorations
        draw.rectangle([15, 15, 385, 25], fill=(60, 40, 0))   
        draw.rectangle([15, 525, 385, 535], fill=(60, 40, 0)) 
        draw.text((145, 45), "WANTED", fill=(60, 40, 0), stroke_width=1)
        draw.text((175, 75), "DEAD", fill=(60, 40, 0))

        # Avatar Sepia Effect
        avatar = avatar.resize((260, 260))
        avatar = ImageOps.grayscale(avatar)
        avatar = ImageOps.colorize(avatar, black=(45, 35, 15), white=(255, 245, 210))
        avatar = ImageOps.expand(avatar, border=10, fill=(60, 40, 0)) 
        poster.paste(avatar, (60, 120))
        
        # Text
        draw.text((130, 425), "LAST KNOWN AS:", fill=(80, 60, 20))
        draw.text((135, 450), f"{mc_name.upper()}", fill=(100, 0, 0), stroke_width=1)
        draw.text((115, 500), "REWARD UPON VERIFIED KILL", fill=(60, 40, 0))

        buffer = BytesIO()
        poster.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Poster error: {e}")
        return None

# --- SLASH COMMANDS ---

@bot.tree.command(name="set_bounty", description="Place a bounty on a player.")
async def set_bounty(interaction: discord.Interaction, target_discord: discord.Member, target_mc: str, reward: str):
    global active_bounty
    if active_bounty["target_discord"]:
        return await interaction.response.send_message("❌ A bounty is already active!", ephemeral=True)
    if target_discord == interaction.user:
        return await interaction.response.send_message("You cannot bounty yourself!", ephemeral=True)

    await interaction.response.defer()
    active_bounty = {"target_discord": target_discord, "target_mc": target_mc, "reward": reward, "setter": interaction.user, "proof_url": None}

    poster_buffer = await create_wanted_poster(target_discord.display_avatar.url, target_mc)
    embed = discord.Embed(title="⚔️ WANTED DEAD", color=discord.Color.dark_red())
    embed.add_field(name="Target", value=f"`{target_mc}` ({target_discord.mention})", inline=False)
    embed.add_field(name="Reward", value=f"💰 {reward}", inline=False)
    
    if poster_buffer:
        file = discord.File(fp=poster_buffer, filename="poster.png")
        embed.set_image(url="attachment://poster.png")
        await interaction.followup.send(file=file, embed=embed)
    else:
        await interaction.followup.send(embed=embed)

@bot.tree.command(name="status", description="Check the active bounty")
async def status(interaction: discord.Interaction):
    if not active_bounty["target_discord"]:
        return await interaction.response.send_message("The board is empty.", ephemeral=True)
    
    embed = discord.Embed(title="📜 Current Contract", color=discord.Color.blue())
    embed.add_field(name="Target", value=f"`{active_bounty['target_mc']}`", inline=True)
    embed.add_field(name="Reward", value=active_bounty['reward'], inline=True)
    if active_bounty["proof_url"]:
        embed.set_image(url=active_bounty["proof_url"])
        embed.set_footer(text="⚠️ Proof has been submitted!")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="claim", description="Submit proof of the kill")
async def claim(interaction: discord.Interaction, mc_username: str, proof_image: discord.Attachment):
    global active_bounty
    if not active_bounty["target_discord"]:
        return await interaction.response.send_message("No active bounty.", ephemeral=True)
    if interaction.user.id == active_bounty["target_discord"].id:
        return await interaction.response.send_message("Nice try, outlaw.", ephemeral=True)

    active_bounty["proof_url"] = proof_image.url
    await interaction.response.send_message(f"🚩 {interaction.user.mention} (`{mc_username}`) claimed the bounty! Check `/status`.")

@bot.tree.command(name="cancel", description="Cancel the bounty")
async def cancel(interaction: discord.Interaction):
    global active_bounty
    if not active_bounty["target_discord"]:
        return await interaction.response.send_message("Nothing to cancel.", ephemeral=True)
    
    if interaction.user == active_bounty["setter"] or interaction.user.guild_permissions.manage_messages:
        for key in active_bounty: active_bounty[key] = None
        await interaction.response.send_message("🚫 Bounty revoked.")
    else:
        await interaction.response.send_message("No permission.", ephemeral=True)

@bot.tree.command(name="finalize", description="Confirm the kill (Mod Only)")
@app_commands.checks.has_permissions(manage_messages=True)
async def finalize(interaction: discord.Interaction, winner_discord: discord.Member, winner_mc: str):
    global active_bounty
    if not active_bounty["target_discord"]:
        return await interaction.response.send_message("No active bounty.", ephemeral=True)

    # 1. Main Channel Message
    embed = discord.Embed(title="🏆 BOUNTY COLLECTED", color=discord.Color.green())
    embed.description = f"**{active_bounty['target_mc']}** has been neutralized by {winner_discord.mention}!"
    await interaction.response.send_message(embed=embed)

    # 2. History Logging
    history_channel = discord.utils.get(interaction.guild.channels, name="bounty-history")
    if history_channel:
        log = discord.Embed(title="💀 Hunt Log", color=discord.Color.dark_grey())
        log.add_field(name="Target", value=active_bounty['target_mc'], inline=True)
        log.add_field(name="Hunter", value=f"{winner_mc} ({winner_discord.mention})", inline=True)
        log.add_field(name="Payout", value=active_bounty['reward'], inline=False)
        if active_bounty["proof_url"]:
            log.set_image(url=active_bounty["proof_url"])
        await history_channel.send(embed=log)

    # Reset
    for key in active_bounty: active_bounty[key] = None

# --- STARTUP ---
if __name__ == "__main__":
    token = os.environ.get('DISCORD_TOKEN')
    if token:
        keep_alive() 
        bot.run(token)
