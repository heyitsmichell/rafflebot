import logging
import secrets
from dataclasses import dataclass, field

import twitchio
from twitchio.ext import commands
from supabase import Client

LOGGER = logging.getLogger("RaffleBot")


@dataclass
class RaffleState:
    is_active: bool = False
    is_open: bool = False
    participants: set[str] = field(default_factory=set)
    participant_names: dict[str, str] = field(default_factory=dict)

    def reset(self) -> None:
        self.is_active = False
        self.is_open = False
        self.participants.clear()
        self.participant_names.clear()

    def add_participant(self, user_id: str, display_name: str) -> bool:
        if user_id in self.participants:
            return False
        self.participants.add(user_id)
        self.participant_names[user_id] = display_name
        return True

    def draw_winner(self) -> str | None:
        if not self.participants:
            return None
        winner_id = secrets.choice(list(self.participants))
        return self.participant_names.get(winner_id, "Unknown")

    def to_db_format(self) -> dict:
        """Convert state to database-storable format."""
        participants_list = [
            {"user_id": uid, "display_name": name}
            for uid, name in self.participant_names.items()
        ]
        return {
            "is_active": self.is_active,
            "is_open": self.is_open,
            "participants": participants_list,
        }

    @classmethod
    def from_db_format(cls, data: dict) -> "RaffleState":
        """Create RaffleState from database record."""
        state = cls()
        state.is_active = data.get("is_active", False)
        state.is_open = data.get("is_open", False)
        
        participants_list = data.get("participants", [])
        for p in participants_list:
            state.participants.add(p["user_id"])
            state.participant_names[p["user_id"]] = p["display_name"]
        
        return state


class RaffleComponent(commands.Component):
    def __init__(self, bot: commands.Bot, supabase: Client) -> None:
        self.bot = bot
        self.supabase = supabase
        self.raffles: dict[str, RaffleState] = {}

    async def load_all_active_raffles(self) -> None:
        """Load all active raffles from database on startup."""
        try:
            result = self.supabase.table("raffles").select("*").eq("is_active", True).execute()
            
            for row in result.data:
                broadcaster_id = row["broadcaster_id"]
                self.raffles[broadcaster_id] = RaffleState.from_db_format(row)
                count = len(self.raffles[broadcaster_id].participants)
                LOGGER.info("Loaded raffle for broadcaster %s with %d participants", broadcaster_id, count)
            
            LOGGER.info("Loaded %d active raffles from database", len(result.data))
        except Exception as e:
            LOGGER.warning("Could not load raffles from database: %s", e)

    def get_raffle(self, broadcaster_id: str) -> RaffleState:
        if broadcaster_id not in self.raffles:
            self.raffles[broadcaster_id] = RaffleState()
        return self.raffles[broadcaster_id]

    async def save_raffle(self, broadcaster_id: str) -> None:
        """Save raffle state to database."""
        raffle = self.raffles.get(broadcaster_id)
        if not raffle:
            return
        
        try:
            data = raffle.to_db_format()
            data["broadcaster_id"] = broadcaster_id
            
            self.supabase.table("raffles").upsert(
                data, on_conflict="broadcaster_id"
            ).execute()
            LOGGER.debug("Saved raffle state for broadcaster %s", broadcaster_id)
        except Exception as e:
            LOGGER.error("Failed to save raffle state: %s", e)

    async def delete_raffle(self, broadcaster_id: str) -> None:
        """Delete raffle state from database."""
        try:
            self.supabase.table("raffles").delete().eq(
                "broadcaster_id", broadcaster_id
            ).execute()
            LOGGER.debug("Deleted raffle state for broadcaster %s", broadcaster_id)
        except Exception as e:
            LOGGER.error("Failed to delete raffle state: %s", e)

    def is_eligible(self, chatter: twitchio.Chatter) -> bool:
        return chatter.vip or chatter.subscriber or chatter.moderator or chatter.broadcaster

    def can_manage(self, chatter: twitchio.Chatter) -> bool:
        return chatter.moderator or chatter.broadcaster

    @commands.command(name="startraffle")
    async def start_raffle(self, ctx: commands.Context) -> None:
        if not self.can_manage(ctx.chatter):
            await ctx.reply("Only moderators and the broadcaster can start a raffle.")
            return

        raffle = self.get_raffle(ctx.broadcaster.id)

        if raffle.is_active:
            await ctx.reply("A raffle is already in progress.")
            return

        raffle.reset()
        raffle.is_active = True
        raffle.is_open = True

        await self.save_raffle(ctx.broadcaster.id)
        await ctx.send("Raffle started! VIPs, Subscribers, and Moderators can type !enter to enter.")

    @commands.command(name="enter")
    async def join_raffle(self, ctx: commands.Context) -> None:
        raffle = self.get_raffle(ctx.broadcaster.id)

        if ctx.chatter.id == str(self.bot.bot_id):
            return

        if not raffle.is_active:
            await ctx.reply("There is no raffle happening right now.")
            return

        if not raffle.is_open:
            await ctx.reply("Raffle entries are closed.")
            return

        if not self.is_eligible(ctx.chatter):
            await ctx.reply("Only VIPs, Subscribers, and Moderators can join.")
            return

        display_name = ctx.chatter.display_name or ctx.chatter.name

        if raffle.add_participant(ctx.chatter.id, display_name):
            await self.save_raffle(ctx.broadcaster.id)
        else:
            await ctx.reply(f"{display_name}, you have already joined.")

    @commands.command(name="endraffle")
    async def end_raffle(self, ctx: commands.Context) -> None:
        if not self.can_manage(ctx.chatter):
            await ctx.reply("Only moderators and the broadcaster can end a raffle.")
            return

        raffle = self.get_raffle(ctx.broadcaster.id)

        if not raffle.is_active:
            await ctx.reply("There is no raffle to end.")
            return

        if not raffle.is_open:
            await ctx.reply("Entries are already closed. Use !draw to pick a winner.")
            return

        raffle.is_open = False
        count = len(raffle.participants)

        await self.save_raffle(ctx.broadcaster.id)
        await ctx.send(f"Entries closed. {count} participant{'s' if count != 1 else ''} entered.")

    @commands.command(name="draw")
    async def draw_winner(self, ctx: commands.Context) -> None:
        if not self.can_manage(ctx.chatter):
            await ctx.reply("Only moderators and the broadcaster can draw a winner.")
            return

        raffle = self.get_raffle(ctx.broadcaster.id)

        if not raffle.is_active:
            await ctx.reply("No raffle active. Start one with !startraffle")
            return

        if raffle.is_open:
            raffle.is_open = False
            await ctx.send("Entries closed.")

        winner = raffle.draw_winner()

        if winner:
            await ctx.send(f"The winner is @{winner} !! Congratulations!")
        else:
            await ctx.send("No one entered the raffle.")
        
        raffle.reset()
        await self.delete_raffle(ctx.broadcaster.id)

    @commands.command(name="cancelraffle")
    async def cancel_raffle(self, ctx: commands.Context) -> None:
        if not self.can_manage(ctx.chatter):
            await ctx.reply("Only moderators and the broadcaster can cancel a raffle.")
            return

        raffle = self.get_raffle(ctx.broadcaster.id)

        if not raffle.is_active:
            await ctx.reply("There is no raffle to cancel.")
            return

        count = len(raffle.participants)
        raffle.reset()

        await self.delete_raffle(ctx.broadcaster.id)
        await ctx.send(f"Raffle cancelled. {count} participant{'s were' if count != 1 else ' was'} entered.")

    @commands.command(name="participants")
    async def show_participants(self, ctx: commands.Context) -> None:
        raffle = self.get_raffle(ctx.broadcaster.id)

        if not raffle.is_active:
            await ctx.reply("No raffle happening.")
            return

        count = len(raffle.participants)
        status = "Open" if raffle.is_open else "Closed"

        await ctx.reply(f"Status: {status} | Participants: {count}")

    @commands.command(name="rafflehelp")
    async def raffle_help(self, ctx: commands.Context) -> None:
        await ctx.send("Commands: !enter, !participants | Mods: !startraffle, !endraffle, !draw, !cancelraffle")
