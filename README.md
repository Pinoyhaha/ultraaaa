# Telegram Activity Bot v2

A Telegram group bot that tracks **videos and documents/files** from members who join after the bot is installed.

## Commands

- `/message` — admins can view members who posted a qualifying video/file today.
- `/kick` — admins can preview members with no qualifying activity today and request confirmation.
- `/kick_confirm` — alias for `/kick`.

## Automatic video copying

When `DESTINATION_CHAT_ID` is configured, the bot automatically copies every **video message** from the monitored source group to that one destination group. The original caption is preserved. Videos are copied directly through Telegram, so the bot does not need to download them to Railway.

The bot must be added to the destination group and must have permission to send messages there.

## Railway setup

1. Create a Railway service from this GitHub repository.
2. Add the environment variable `BOT_TOKEN` using the token from BotFather.
3. Add `DESTINATION_CHAT_ID` with the destination group's chat ID. For a supergroup, this commonly looks like `-1001234567890`.
4. Optional: set `DB_PATH=/data/activity.db` and attach a Railway Volume mounted at `/data` so activity survives redeploys.
5. Deploy using the `worker` process from the Procfile.

## Telegram setup

- Add the bot to both the monitored source group and the destination group.
- Make the bot an administrator in the destination group with permission to send messages.
- Make the bot an administrator in the source group with permission to restrict/ban members if using the kick feature.
- Disable BotFather privacy mode (`/setprivacy` -> Disable), otherwise the bot may not receive ordinary video/file messages.
- The bot only adds users to its tracked roster when it receives a join event after installation. Existing members are not automatically added.
- Telegram administrators cannot normally be removed by the bot; review the list before confirming.

## Notes

The bot uses Asia/Manila dates and SQLite. A qualifying activity is a video message or a document/file message. The current implementation requires an admin confirmation before removals.
