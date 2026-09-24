# Telegram Activity Bot v2

A Telegram group bot that tracks **videos and documents/files** from members who join after the bot is installed.

## Commands

- `/message` — admins can view members who posted a qualifying video/file today.
- `/kick` — admins can preview members with no qualifying activity today and request confirmation.
- `/kick_confirm` — alias for `/kick`.

## Railway setup

1. Create a Railway service from this GitHub repository.
2. Add the environment variable `BOT_TOKEN` using the token from BotFather.
3. Optional: set `DB_PATH=/data/activity.db` and attach a Railway Volume mounted at `/data` so activity survives redeploys.
4. Deploy using the `worker` process from the Procfile.

## Telegram setup

- Make the bot an administrator with permission to restrict/ban members.
- Disable BotFather privacy mode (`/setprivacy` -> Disable), otherwise the bot may not receive ordinary video/file messages.
- The bot only adds users to its tracked roster when it receives a join event after installation. Existing members are not automatically added.
- Telegram administrators cannot normally be removed by the bot; review the list before confirming.

## Notes

The bot uses Asia/Manila dates and SQLite. A qualifying activity is a video message or a document/file message. The current implementation requires an admin confirmation before removals.
