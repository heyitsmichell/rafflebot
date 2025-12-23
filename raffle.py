import random
from dataclasses import dataclass, field

import twitchio
from twitchio.ext import commands


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
        winner_id = random.choice(list(self.participants))
        return self.participant_names.get(winner_id, "Unknown")


class RaffleComponent(commands.Component):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.raffles: dict[str, RaffleState] = {}

    def get_raffle(self, broadcaster_id: str) -> RaffleState:
        if broadcaster_id not in self.raffles:
            self.raffles[broadcaster_id] = RaffleState()
        return self.raffles[broadcaster_id]

    def is_eligible(self, chatter: twitchio.Chatter) -> bool:
        return chatter.vip or chatter.subscriber or chatter.moderator or chatter.broadcaster

    def can_manage(self, chatter: twitchio.Chatter) -> bool:
        return chatter.moderator or chatter.broadcaster

    @commands.command(name="startraffle", aliases=["sr"])
    async def start_raffle(self, ctx: commands.Context) -> None:
        if not self.can_manage(ctx.chatter):
            await ctx.reply("❌ Only moderators and the broadcaster can start a raffle!")
            return

        raffle = self.get_raffle(ctx.broadcaster.id)

        if raffle.is_active:
            await ctx.reply("⚠️ A raffle is already in progress!")
            return

        raffle.reset()
        raffle.is_active = True
        raffle.is_open = True

        await ctx.send("🎉 RAFFLE STARTED! 🎉 VIPs, Subscribers, and Moderators can type !join to enter! 🍀")

    @commands.command(name="join", aliases=["enter"])
    async def join_raffle(self, ctx: commands.Context) -> None:
        raffle = self.get_raffle(ctx.broadcaster.id)

        if ctx.chatter.id == str(self.bot.bot_id):
            return

        if not raffle.is_active:
            await ctx.reply("❌ There's no raffle happening right now!")
            return

        if not raffle.is_open:
            await ctx.reply("❌ Raffle entries are closed!")
            return

        if not self.is_eligible(ctx.chatter):
            await ctx.reply("❌ Only VIPs, Subscribers, and Moderators can join! 💜")
            return

        display_name = ctx.chatter.display_name or ctx.chatter.name

        if raffle.add_participant(ctx.chatter.id, display_name):
            await ctx.reply(f"✅ {display_name}, you're in! Good luck! 🎲")
        else:
            await ctx.reply(f"⚠️ {display_name}, you've already joined!")

    @commands.command(name="endraffle", aliases=["er", "closeraffle"])
    async def end_raffle(self, ctx: commands.Context) -> None:
        if not self.can_manage(ctx.chatter):
            await ctx.reply("❌ Only moderators and the broadcaster can end a raffle!")
            return

        raffle = self.get_raffle(ctx.broadcaster.id)

        if not raffle.is_active:
            await ctx.reply("❌ There's no raffle to end!")
            return

        if not raffle.is_open:
            await ctx.reply("⚠️ Entries already closed! Use !draw to pick a winner.")
            return

        raffle.is_open = False
        count = len(raffle.participants)

        await ctx.send(f"🔒 ENTRIES CLOSED! {count} participant{'s' if count != 1 else ''} entered! Use !draw 🎯")

    @commands.command(name="draw", aliases=["pickwinner"])
    async def draw_winner(self, ctx: commands.Context) -> None:
        if not self.can_manage(ctx.chatter):
            await ctx.reply("❌ Only moderators and the broadcaster can draw!")
            return

        raffle = self.get_raffle(ctx.broadcaster.id)

        if not raffle.is_active:
            await ctx.reply("❌ No raffle active! Start one with !startraffle")
            return

        if raffle.is_open:
            raffle.is_open = False
            await ctx.send("🔒 Entries closed!")

        winner = raffle.draw_winner()

        if winner:
            await ctx.send(f"🎊🎉 THE WINNER IS... 🥁🥁🥁 🏆 {winner} 🏆 Congratulations! 🎉🎊")
        else:
            await ctx.send("😢 No one entered the raffle!")
        
        raffle.reset()

    @commands.command(name="cancelraffle", aliases=["cr"])
    async def cancel_raffle(self, ctx: commands.Context) -> None:
        if not self.can_manage(ctx.chatter):
            await ctx.reply("❌ Only moderators and the broadcaster can cancel!")
            return

        raffle = self.get_raffle(ctx.broadcaster.id)

        if not raffle.is_active:
            await ctx.reply("❌ No raffle to cancel!")
            return

        count = len(raffle.participants)
        raffle.reset()

        await ctx.send(f"❌ Raffle cancelled. {count} participant{'s were' if count != 1 else ' was'} entered.")

    @commands.command(name="participants", aliases=["count", "entries"])
    async def show_participants(self, ctx: commands.Context) -> None:
        raffle = self.get_raffle(ctx.broadcaster.id)

        if not raffle.is_active:
            await ctx.reply("❌ No raffle happening!")
            return

        count = len(raffle.participants)
        status = "🟢 OPEN" if raffle.is_open else "🔴 CLOSED"

        await ctx.reply(f"📊 {status} | 👥 {count} participants")

    @commands.command(name="rafflehelp", aliases=["rh"])
    async def raffle_help(self, ctx: commands.Context) -> None:
        await ctx.send("🎰 !join - Enter | !participants - Count | [Mods] !startraffle !endraffle !draw !cancelraffle")
