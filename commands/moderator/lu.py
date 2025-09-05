import discord
from discord.ext import commands
import sqlite3
import json
from datetime import datetime

DB_PATH = "data/scrims.db"

# --- Hilfsfunktionen ---
def fetch_signups():
    """Liest alle Signups aus der DB und filtert Spieler, die bereits in einem finalisierten LU für diese Stunde sind"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT hour, team, role, user_ids FROM signups")
    rows = cur.fetchall()

    # Finalisierte LUs
    cur.execute("SELECT hour, user_id FROM scrim_meta m JOIN scrim s ON m.id=s.id WHERE m.finalized=1")
    final_uids = {}
    for row in cur.fetchall():
        final_uids.setdefault(row["hour"], set()).add(row["user_id"])

    conn.close()

    grouped = {}
    for row in rows:
        key = (row["hour"], row["team"])
        if key not in grouped:
            grouped[key] = []

        try:
            user_list = json.loads(row["user_ids"])
        except (json.JSONDecodeError, TypeError):
            user_list = []

        # Entferne bereits finalisierte User
        filtered = [uid for uid in user_list if uid not in final_uids.get(row["hour"], set())]

        for uid in filtered:
            grouped[key].append((uid, row["role"]))

    return grouped

# --- UI-Elemente ---
class PlayerSelect(discord.ui.Select):
    def __init__(self, guild, hour, team, players, parent_view):
        sorted_players = sorted(players, key=lambda x: 0 if x[1] == "main" else 1)
        options = []
        for uid, _ in sorted_players:
            try:
                member = guild.get_member(int(uid))
                name = member.display_name if member else f"Unknown({uid})"
            except ValueError:
                name = f"Unknown({uid})"
            options.append(discord.SelectOption(label=name, value=uid))
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
        self.add_item(discord.ui.InputText(label="Host", placeholder="Unser Team oder Gegner", value=view.team))
        self.add_item(discord.ui.InputText(label="Gegnername", placeholder="Gegner muss angegeben werden"))
        self.add_item(discord.ui.InputText(label="Open", placeholder="Optional", value=":00", required=False))

    async def callback(self, interaction: discord.Interaction):
        self.view.host = self.children[0].value.strip() or self.view.team
        self.view.opponent = self.children[1].value.strip()
        self.view.open = self.children[2].value.strip() or ":00"
        await self.view.finalize(interaction)

class FinalizeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Finalize Line-Up", style=discord.ButtonStyle.green)

    async def callback(self, interaction: discord.Interaction):
        view: LUSelect = self.view
        if not view.selected_players:
            await interaction.response.send_message("⚠️ Keine Spieler ausgewählt.", ephemeral=True)
            return
        await interaction.response.send_modal(LUModal(view))

class HourTeamSelect(discord.ui.Select):
    def __init__(self, grouped):
        options = []
        for (hour, team), users in grouped.items():
            if len(users) >= 6:
                options.append(discord.SelectOption(label=f"{hour}:00 {team}", value=f"{hour}|{team}"))
        super().__init__(placeholder="Stunde und Team wählen", options=options)
        self.grouped = grouped

    async def callback(self, interaction: discord.Interaction):
        await interaction.message.delete()
        hour_str, team = self.values[0].split("|")
        hour = int(hour_str)
        players = self.grouped.get((hour, team), [])

        if len(players) < 6:
            await interaction.response.send_message("⚠️ Nicht genug Spieler für dieses Team.", ephemeral=True)
            return

        view = LUSelect(interaction.guild, hour, team, players)
        if len(players) == 6:
            view.selected_players = players
            await interaction.response.send_modal(LUModal(view))
        else:
            await interaction.response.send_message(
                f"Team {team} für {hour} Uhr gewählt. Spieler auswählen:",
                view=view,
                ephemeral=True
            )

class LUSelect(discord.ui.View):
    def __init__(self, guild, hour, team, players):
        super().__init__(timeout=None)
        self.guild = guild
        self.hour = hour
        self.team = team
        self.players = players
        self.selected_players = []
        self.host = None
        self.opponent = None
        self.open = ":00"

        self.add_item(PlayerSelect(guild, hour, team, players, self))
        self.add_item(FinalizeButton())

    async def finalize(self, interaction: discord.Interaction):
        created_at = datetime.now().strftime("%d.%m.%Y")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # Scrim Meta einfügen
        cur.execute(
            "INSERT INTO scrim_meta (hour, created_at, host, opponent, open, finalized) VALUES (?, ?, ?, ?, ?, ?)",
            (self.hour, created_at, self.host, self.opponent, self.open, 1)
        )
        scrim_id = cur.lastrowid

        # Scrim Teilnehmer einfügen & aus Signups entfernen
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
            current_ids = []
            if row and row[0]:
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

        # LU alphabetisch sortieren nach DisplayName
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

        opponent_text = f" vs. {self.opponent}" if self.opponent else ""
        embed = discord.Embed(
            title=f"Scrim#{scrim_id} {self.team}{opponent_text} am {created_at} um {self.hour} Uhr",
            description=f"LU: {lu_line}\nHost: {self.host}   Open: {self.open}",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed)

# --- Cog ---
class LineUp(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(
        name="lu",
        description="Erstellt ein interaktives Line-Up (nur für Moderatoren)"
    )
    async def lu(self, ctx: discord.ApplicationContext):
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.respond("❌ Keine Berechtigung.", ephemeral=True)
            return

        grouped = fetch_signups()
        if not grouped:
            await ctx.respond("⚠️ Keine Signups gefunden.", ephemeral=True)
            return

        view = discord.ui.View()
        view.add_item(HourTeamSelect(grouped))
        await ctx.respond("Bitte Stunde und Team wählen:", view=view, ephemeral=True)

def setup(bot):
    bot.add_cog(LineUp(bot))
