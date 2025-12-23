# Twitch Raffle Bot

A Twitch chat bot that runs raffles during livestreams. Only **VIPs**, **Subscribers**, and **Moderators** can participate.

## Features

- Role-based participation (VIP/Sub/Mod only)
- One entry per raffle
- Random winner selection
- Mod controls for raffle management
- Supabase for token storage

## Commands

| Command | Aliases | Description | Who Can Use |
|---------|---------|-------------|-------------|
| `!startraffle` | `!sr` | Start a new raffle | Broadcaster/Mods |
| `!join` | `!enter` | Join the raffle | VIP/Sub/Mod only |
| `!endraffle` | `!er` | Close entries | Broadcaster/Mods |
| `!draw` | `!pickwinner` | Pick a winner | Broadcaster/Mods |
| `!cancelraffle` | `!cr` | Cancel raffle | Broadcaster/Mods |
| `!participants` | `!count` | Show entry count | Anyone |
| `!rafflehelp` | `!rh` | Show commands | Anyone |

## Setup

### 1. Twitch Application

1. Go to [Twitch Developer Console](https://dev.twitch.tv/console)
2. Create an application with OAuth redirect: `https://YOUR-RENDER-APP.onrender.com/oauth/callback`
3. Note your **Client ID** and **Client Secret**

### 2. Get User IDs

Use [this tool](https://www.streamweasels.com/tools/convert-twitch-username-to-user-id/) to get IDs for your bot and channel accounts.

### 3. Supabase Setup

1. Create a project at [supabase.com](https://supabase.com)
2. Run this SQL to create the tokens table:
   ```sql
   CREATE TABLE twitch_tokens (
       user_id TEXT PRIMARY KEY,
       token TEXT NOT NULL,
       refresh TEXT NOT NULL
   );
   ```
3. Get your **Project URL** and **anon key** from Project Settings → API

### 4. Deploy to Render

1. Fork/clone this repo
2. Create a **Background Worker** on [Render](https://render.com)
3. Add environment variables (see below)
4. Deploy!

### Environment Variables

| Variable | Description |
|----------|-------------|
| `TWITCH_CLIENT_ID` | Twitch app Client ID |
| `TWITCH_CLIENT_SECRET` | Twitch app Client Secret |
| `TWITCH_BOT_ID` | Bot account User ID |
| `TWITCH_OWNER_ID` | Channel owner User ID |
| `TWITCH_CHANNEL` | Channel name to join |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon key |

### 5. Authorize Bot

After deployment, authorize both accounts:
- **Bot account**: `https://YOUR-APP.onrender.com/oauth?scopes=user:read:chat%20user:write:chat%20user:bot&force_verify=true`
- **Channel owner**: `https://YOUR-APP.onrender.com/oauth?scopes=channel:bot&force_verify=true`

## License

MIT
