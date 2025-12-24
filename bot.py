import asyncio
import logging
import os

import twitchio
from twitchio import eventsub
from twitchio.ext import commands
from twitchio.web import AiohttpAdapter
from aiohttp import web
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

LOGGER = logging.getLogger("RaffleBot")

CLIENT_ID = os.getenv("TWITCH_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET", "")
BOT_ID = os.getenv("TWITCH_BOT_ID", "")
OWNER_ID = os.getenv("TWITCH_OWNER_ID", "")
CHANNEL = os.getenv("TWITCH_CHANNEL", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
PORT = int(os.getenv("PORT", "10000"))
RENDER_URL = os.getenv("RENDER_URL", "")


async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="RaffleBot Running!", status=200)


class HealthCheckAdapter(AiohttpAdapter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_routes([
            web.get("/", health_check),
            web.get("/health", health_check),
        ])


class RaffleBot(commands.AutoBot):
    def __init__(self, *, supabase_client: Client, subs: list[eventsub.SubscriptionPayload]) -> None:
        self.supabase = supabase_client
        
        adapter = HealthCheckAdapter(host="0.0.0.0", port=PORT, domain=RENDER_URL if RENDER_URL else None)
        
        super().__init__(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            bot_id=BOT_ID,
            owner_id=OWNER_ID,
            prefix="!",
            subscriptions=subs,
            force_subscribe=True,
            adapter=adapter,
        )

    async def setup_hook(self) -> None:
        from raffle import RaffleComponent
        raffle_component = RaffleComponent(self, self.supabase)
        await raffle_component.load_all_active_raffles()
        await self.add_component(raffle_component)
        LOGGER.info("Loaded RaffleComponent")
        
        if CHANNEL:
            LOGGER.info("Target channel: %s", CHANNEL)
            await self._subscribe_to_channel(CHANNEL)
    
    async def _subscribe_to_channel(self, channel_name: str) -> None:
        try:
            users = await self.fetch_users(logins=[channel_name])
            if not users:
                LOGGER.error("Could not find channel: %s", channel_name)
                return
            
            channel_id = users[0].id
            LOGGER.info("Found channel %s (ID: %s)", channel_name, channel_id)
            
            subs = [eventsub.ChatMessageSubscription(broadcaster_user_id=channel_id, user_id=self.bot_id)]
            resp = await self.multi_subscribe(subs)
            
            if resp.errors:
                LOGGER.warning("Subscribe error: %r", resp.errors)
            else:
                LOGGER.info("Subscribed to channel: %s", channel_name)
        except Exception as e:
            LOGGER.error("Error: %s", e)

    async def event_oauth_authorized(self, payload: twitchio.authentication.UserTokenPayload) -> None:
        await self.add_token(payload.access_token, payload.refresh_token)

        if not payload.user_id or payload.user_id == self.bot_id:
            return

        subs = [eventsub.ChatMessageSubscription(broadcaster_user_id=payload.user_id, user_id=self.bot_id)]
        resp = await self.multi_subscribe(subs)
        
        if resp.errors:
            LOGGER.warning("Failed to subscribe: %r", resp.errors)

    async def add_token(self, token: str, refresh: str) -> twitchio.authentication.ValidateTokenPayload:
        resp = await super().add_token(token, refresh)

        try:
            self.supabase.table("twitch_tokens").upsert({
                "user_id": resp.user_id,
                "token": token,
                "refresh": refresh
            }, on_conflict="user_id").execute()
            LOGGER.info("Saved token for user: %s", resp.user_id)
        except Exception as e:
            LOGGER.error("Failed to save token: %s", e)

        return resp

    async def event_ready(self) -> None:
        LOGGER.info("Bot ready! ID: %s, Channel: %s, Port: %s", self.bot_id, CHANNEL, PORT)


def load_tokens(supabase: Client) -> tuple[list[tuple[str, str]], list[eventsub.SubscriptionPayload]]:
    tokens = []
    subs = []

    try:
        result = supabase.table("twitch_tokens").select("*").execute()
        
        for row in result.data:
            tokens.append((row["token"], row["refresh"]))
            if row["user_id"] != BOT_ID:
                subs.append(eventsub.ChatMessageSubscription(broadcaster_user_id=row["user_id"], user_id=BOT_ID))
        
        LOGGER.info("Loaded %d tokens", len(tokens))
    except Exception as e:
        LOGGER.warning("Could not load tokens: %s", e)

    return tokens, subs


def main() -> None:
    if not all([CLIENT_ID, CLIENT_SECRET, BOT_ID, OWNER_ID]):
        print("ERROR: Missing Twitch environment variables!")
        return
    
    if not all([SUPABASE_URL, SUPABASE_KEY]):
        print("ERROR: Missing Supabase environment variables!")
        return

    twitchio.utils.setup_logging(level=logging.INFO)
    LOGGER.info("Starting bot on 0.0.0.0:%s", PORT)

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    LOGGER.info("Connected to Supabase")

    tokens, subs = load_tokens(supabase)

    async def runner() -> None:
        async with RaffleBot(supabase_client=supabase, subs=subs) as bot:
            for pair in tokens:
                await bot.add_token(*pair)
            await bot.start(load_tokens=False)

    try:
        asyncio.run(runner())
    except KeyboardInterrupt:
        LOGGER.warning("Shutting down")


if __name__ == "__main__":
    main()
