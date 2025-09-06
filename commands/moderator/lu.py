import discord
from discord.ext import commands
import sqlite3
import json
from datetime import datetime

DB_PATH = "data/scrims.db"

# --- Hilfsfunktionen ---
def fetch_signups():
    """Liest alle Signups aus der DB und gruppiert sie nach (hour, team)"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT hour, team, role, user_ids FROM signups")
    rows = cur.fetchall()
    conn.close()

    grouped = {}
    for row in rows:
        key = (row["hour"], row["team"])
        if key not in grouped:
            grouped[key] = []

        raw = str(row["user_ids"]).strip()
        if raw.startswith("["):
            try:
                user_list = json.loads(raw)
            except json.JSONDecodeError:
                user_list = []
        else:
            user_list = [u.strip() for u in raw.split(",") if u.strip()]

        for uid in user_list:
            grouped[key].append((uid, row["role"]))

    return grouped

# --- UI-Elemente ---
class HourTeamSelect(discord.ui.Select):
    def __init__(self, grouped):
        options = []
        for (hour, team), users in grouped.items():
            if len(users) >= 6:
                options.append(discord.SelectOption(label=f"{hour} Uhr {team}", value=f"{hour}|{team}"))
        super().__init__(placeholder="Scrim auswählen", options=options)
        self.grouped = grouped

    async def callback(self, interaction: discord.Interaction):
        hour_str, team = self.values[0].split("|")
        hour = int(hour_str)
        players = self.grouped.get((hour, team), [])

        if len(players) < 6:
            await interaction.response.send_message("Nicht genügend Spieler für dieses Team", ephemeral=True)
            return

        view = LUSelect(interaction.guild, hour, team, players)

        if len(players) == 6:
            view.selected_players = players  # alle Spieler automatisch auswählen
            await interaction.response.send_modal(LUModal(view))
        else:
            await interaction.response.send_message(
                f"Team {team} für {hour} Uhr gewählt. Spieler auswählen:",
                view=view,
                ephemeral=True
            )

class PlayerSelect(discord.ui.Select):
    def __init__(self, guild, hour, team, players, parent_view):
        sorted_players = sorted(players, key=lambda x: 0 if x[1]=="main" else 1)
        options = []
        for uid, _ in sorted_players:
            try:
                member = guild.get_member(int(uid))
                name = member.display_name if member else f"Unknown({uid})"
            except ValueError:
                name = f"Unknown({uid})"
            options.append(discord.SelectOption(label=name, value=uid, default=True))
        super().__init__(
            placeholder="Wähle die Spieler aus (min. 6)",
            min_values=6,
            max_values=len(options),
            options=options
        )
        self.hour = hour
        self.team = team
        self.players = sorted_players
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        selected_uids = set(self.values)
        self.parent_view.selected_players = [
            (uid, role) for uid, role in self.players if uid in selected_uids
        ]
        await interaction.response.send_modal(LUModal(self.parent_view))

class LUModal(discord.ui.Modal):
    def __init__(self, view):
        super().__init__(title="Scrim Informationen")
        self.view = view
        self.add_item(discord.ui.InputText(label="Host", placeholder="Unser Team oder Gegner", value="WEC"))
        self.add_item(discord.ui.InputText(label="Gegner-Name", placeholder="Name des Gegners", required=True))
        self.add_item(discord.ui.InputText(label="Gegner-Tag", placeholder="Tag z.B. #1234", required=True))
        self.add_item(discord.ui.InputText(label="Open", placeholder="Optional", required=False, value=":00"))

    async def callback(self, interaction: discord.Interaction):
        self.view.host = self.children[0].value.strip() if self.children[0].value.strip() else "WEC"
        self.view.opponent_name = self.children[1].value.strip()
        self.view.opponent_tag = self.children[2].value.strip()
        self.view.open = self.children[3].value.strip() if self.children[3].value.strip() else ":00"
        await self.view.finalize(interaction)

class FinalizeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Erstelle Line-Up", style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        view: LUSelect = self.view
        if not view.selected_players:
            await interaction.response.send_message("Keine Spieler ausgewählt!", ephemeral=True)
            return
        await interaction.response.send_modal(LUModal(view))

class LUSelect(discord.ui.View):
    def __init__(self, guild, hour, team, players):
        super().__init__(timeout=None)
        self.guild = guild
        self.hour = hour
        self.team = team
        self.players = players
        self.selected_players = []
        self.host = None
        self.opponent_name = None
        self.opponent_tag = None
        self.open = ":00"

        self.add_item(PlayerSelect(guild, hour, team, players, self))
        self.add_item(FinalizeButton())

    async def finalize(self, interaction: discord.Interaction):
        created_at = datetime.now().strftime("%d.%m.%Y")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # --- Scrim Meta einfügen (Name + Tag getrennt) ---
        cur.execute(
            "INSERT INTO scrim_meta (hour, created_at, host, opponent_name, opponent_tag, open, finalized) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (self.hour, created_at, self.host, self.opponent_name, self.opponent_tag, self.open, 1)
        )
        scrim_id = cur.lastrowid

        # --- Scrim Teilnehmer einfügen und aus Signups entfernen ---
        for uid, role in self.selected_players:
            cur.execute(
                "INSERT INTO scrim (id, hour, team, role, user_id) VALUES (?, ?, ?, ?, ?)",
                (scrim_id, self.hour, self.team, role, uid)
            )
            cur.execute(
                "SELECT user_ids FROM signups WHERE hour=? AND team=? AND role=?",
                (self.hour, self.team, role)
            )
            row = cur.fetchone()
            if row:
                try:
                    current_ids = json.loads(row[0])
                except json.JSONDecodeError:
                    current_ids = [x.strip() for x in row[0].split(",") if x.strip()]
                if uid in current_ids:
                    current_ids.remove(uid)
                cur.execute(
                    "UPDATE signups SET user_ids=? WHERE hour=? AND team=? AND role=?",
                    (json.dumps(current_ids), self.hour, self.team, role)
                )

        conn.commit()
        conn.close()

        # --- LU alphabetisch sortieren nach DisplayName ---
        lines = []
        for uid, _ in self.selected_players:
            try:
                member = interaction.guild.get_member(int(uid))
                name = member.display_name if member else f"Unknown({uid})"
            except ValueError:
                name = f"Unknown({uid})"
            lines.append((name.lower(), f"<@{uid}>"))
        lines.sort(key=lambda x: x[0])
        lu_line = ", ".join(ping for _, ping in lines)

        # Gegner im Embed als Name - Tag
        opponent_text = f" vs. {self.opponent_name} - {self.opponent_tag}" if self.opponent_name and self.opponent_tag else ""

        embed = discord.Embed(
            title=f"Scrim#{scrim_id} {self.team}{opponent_text} am {created_at} um {self.hour} Uhr",
            description=f"LU: {lu_line}\nHost: {self.host} | Open: {self.open}",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed)

# --- Cog ---
class LineUp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="lu",
        description="Erstellt ein Line-Up (nur für Organisatoren)"
    )
    async def lu(self, ctx: discord.ApplicationContext):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.respond("❌ Keine Berechtigung!", ephemeral=True)
            return

        grouped = fetch_signups()
        if not grouped:
            await ctx.respond("Keine Anmeldungen gefunden!", ephemeral=True)
            return

        view = discord.ui.View()
        view.add_item(HourTeamSelect(grouped))
        await ctx.respond("Scrim auswählen:", view=view, ephemeral=True)

def setup(bot):
    bot.add_cog(LineUp(bot))
