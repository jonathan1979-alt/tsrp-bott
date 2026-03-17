import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN environment variable not set.")

STAFF_ROLE_ID      = 1483128933103960178
IA_ROLE_ID         = 1483128933086920772
MANAGEMENT_ROLE_ID = 1483128933103960176

TICKET_TYPES = {
    "general": {
        "label": "General Ticket",
        "description": "General questions and support",
        "emoji": "🎫",
        "ping_role_ids": [STAFF_ROLE_ID, IA_ROLE_ID, MANAGEMENT_ROLE_ID],
        "color": discord.Color.blue(),
        "category_name": "General Tickets",
    },
    "internal_affairs": {
        "label": "Internal Affairs Ticket",
        "description": "Internal affairs reports and inquiries",
        "emoji": "🔍",
        "ping_role_ids": [IA_ROLE_ID, MANAGEMENT_ROLE_ID],
        "color": discord.Color.red(),
        "category_name": "Internal Affairs Tickets",
    },
    "management": {
        "label": "Management Ticket",
        "description": "Management-level concerns and escalations",
        "emoji": "👔",
        "ping_role_ids": [MANAGEMENT_ROLE_ID],
        "color": discord.Color.gold(),
        "category_name": "Management Tickets",
    },
}


async def get_or_create_category(guild: discord.Guild, name: str):
    category = discord.utils.get(guild.categories, name=name)
    if category:
        return category
    try:
        return await guild.create_category(name)
    except discord.Forbidden:
        return None


async def create_ticket_channel(interaction: discord.Interaction, ticket_key: str, issue: str):
    info = TICKET_TYPES[ticket_key]
    guild = interaction.guild
    member = interaction.user

    category = await get_or_create_category(guild, info["category_name"])

    safe_name = member.name.lower().replace(" ", "-")
    channel_name = f"ticket-{safe_name}"[:90]

    ping_roles = [r for rid in info["ping_role_ids"] if (r := guild.get_role(rid))]

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
        ),
        guild.me: discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            manage_channels=True,
            read_message_history=True,
        ),
    }
    for role in ping_roles:
        overwrites[role] = discord.PermissionOverwrite(
            read_messages=True,
            send_messages=True,
            read_message_history=True,
        )

    try:
        if category:
            ticket_channel = await category.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                topic=f"Ticket by {member.display_name} | Type: {info['label']} | Unclaimed",
            )
        else:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                overwrites=overwrites,
                topic=f"Ticket by {member.display_name} | Type: {info['label']} | Unclaimed",
            )
    except discord.Forbidden:
        await interaction.followup.send(
            "❌ The bot is missing the **Manage Channels** permission. "
            "Please give the bot Administrator (or Manage Channels) permission in your server settings, then try again.",
            ephemeral=True,
        )
        return

    pings = member.mention
    for role in ping_roles:
        pings += f" {role.mention}"

    description = (
        "**Hello there and thank you for contacting the Texas State Roleplay staff team.**\n\n"
        "We are always glad to assist you with your ticket. We as a staff team assist you with any "
        "questions that you may have for our staff members. To get the right assistance, please "
        "provide more information in regards to your ticket.\n\n"
        f"**Issue**\n> {issue}"
    )

    embed = discord.Embed(
        title=f"{info['emoji']} {info['label']}",
        description=description,
        color=info["color"],
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(
        text=f"Opened by {member.display_name}",
        icon_url=member.display_avatar.url,
    )

    control_view = TicketControlView()
    await ticket_channel.send(content=pings, embed=embed, view=control_view)

    await interaction.followup.send(
        f"✅ Your ticket has been created: {ticket_channel.mention}",
        ephemeral=True,
    )


class TicketIssueModal(discord.ui.Modal, title="Open a Ticket"):
    def __init__(self, ticket_key: str):
        super().__init__()
        self.ticket_key = ticket_key

    issue = discord.ui.TextInput(
        label="Describe your issue",
        placeholder="Please briefly describe what you need help with...",
        required=True,
        max_length=1000,
        style=discord.TextStyle.paragraph,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await create_ticket_channel(
            interaction,
            self.ticket_key,
            issue=self.issue.value,
        )


class RenameModal(discord.ui.Modal, title="Rename Ticket"):
    new_name = discord.ui.TextInput(
        label="New channel name",
        placeholder="e.g. ticket-john-doe",
        min_length=1,
        max_length=90,
        style=discord.TextStyle.short,
    )

    async def on_submit(self, interaction: discord.Interaction):
        safe = self.new_name.value.lower().replace(" ", "-")
        try:
            await interaction.channel.edit(name=safe, reason=f"Renamed by {interaction.user}")
            await interaction.response.send_message(
                f"✏️ Ticket renamed to **{safe}**.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to rename this channel.", ephemeral=True
            )


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.success,
        emoji="✋",
        custom_id="claim_ticket",
    )
    async def claim_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        member = interaction.user
        try:
            await interaction.channel.edit(
                topic=f"Claimed by {member.display_name} ({member.id})",
                reason=f"Ticket claimed by {member}",
            )
        except discord.Forbidden:
            pass

        button.label = f"Claimed by {member.display_name}"
        button.disabled = True
        button.style = discord.ButtonStyle.secondary

        await interaction.response.edit_message(view=self)
        await interaction.channel.send(
            f"✋ This ticket has been claimed by {member.mention}."
        )

    @discord.ui.button(
        label="Rename",
        style=discord.ButtonStyle.primary,
        emoji="✏️",
        custom_id="rename_ticket",
    )
    async def rename_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(RenameModal())

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="close_ticket",
    )
    async def close_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            f"🔒 Ticket closed by {interaction.user.mention}. Deleting in 5 seconds..."
        )
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.Forbidden:
            await interaction.channel.send(
                "❌ I don't have permission to delete this channel. "
                "Please make sure the bot has the **Manage Channels** permission."
            )
        except discord.NotFound:
            pass


class TicketTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=info["label"],
                value=key,
                description=info["description"],
                emoji=info["emoji"],
            )
            for key, info in TICKET_TYPES.items()
        ]
        super().__init__(
            placeholder="Select a ticket type...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_type_select",
        )

    async def callback(self, interaction: discord.Interaction):
        ticket_key = self.values[0]
        await interaction.response.send_modal(TicketIssueModal(ticket_key=ticket_key))


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect())


class TicketBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(TicketPanelView())
        self.add_view(TicketControlView())
        await self.tree.sync()
        print("Slash commands synced.")

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print("Bot is ready!\n")

        for guild in self.guilds:
            me = guild.me
            perms = me.guild_permissions
            print(f"=== Permission check for: {guild.name} ===")
            checks = {
                "Manage Channels (required to create/delete/rename ticket channels)": perms.manage_channels,
                "Read Messages":        perms.read_messages,
                "Send Messages":        perms.send_messages,
                "Manage Roles":         perms.manage_roles,
                "Read Message History": perms.read_message_history,
            }
            all_ok = True
            for label, has_perm in checks.items():
                status = "✅" if has_perm else "❌ MISSING"
                print(f"  {status}  {label}")
                if not has_perm:
                    all_ok = False
            if all_ok:
                print("  All permissions look good!")
            else:
                print(
                    "\n  ⚠️  Fix: Go to Server Settings → Roles → bot role → enable missing permissions.\n"
                    "  Or give the bot Administrator for easiest setup.\n"
                )
            print()


bot = TicketBot()


@bot.tree.command(name="panel", description="Send the ticket panel to this channel.")
@app_commands.checks.has_permissions(administrator=True)
async def panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎟️ Texas State Roleplay — Support Tickets",
        description=(
            "Need help from our staff team? Open a ticket below!\n\n"
            "🎫 **General Ticket** — General questions and support\n"
            "🔍 **Internal Affairs Ticket** — IA reports and inquiries\n"
            "👔 **Management Ticket** — Management-level concerns\n\n"
            "Select a category from the dropdown menu to open your ticket."
        ),
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Texas State Roleplay | Support System")

    view = TicketPanelView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Ticket panel sent!", ephemeral=True)


@panel.error
async def panel_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You need Administrator permissions to use this command.", ephemeral=True
        )


bot.run(TOKEN)
