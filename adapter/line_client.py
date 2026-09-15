import os

from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    MarkMessagesAsReadByTokenRequest,
    PushMessageRequest,
    ReplyMessageRequest,
    ShowLoadingAnimationRequest,
    TextMessage,
)


def _configuration() -> Configuration:
    return Configuration(access_token=os.environ["LINE_CHANNEL_ACCESS_TOKEN"])


async def reply_text(reply_token: str, text: str) -> None:
    async with AsyncApiClient(_configuration()) as client:
        await AsyncMessagingApi(client).reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=text)])
        )


async def push_text(user_id: str, text: str) -> None:
    async with AsyncApiClient(_configuration()) as client:
        await AsyncMessagingApi(client).push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
        )


async def mark_as_read(mark_as_read_token: str) -> None:
    """Mark the user's message (and anything before it) as read.

    Only has a visible effect when "Chat" is enabled in LINE Official
    Account Manager's Response settings — otherwise LINE already
    auto-marks messages as read and this is a harmless no-op.
    """
    async with AsyncApiClient(_configuration()) as client:
        await AsyncMessagingApi(client).mark_messages_as_read_by_token(
            MarkMessagesAsReadByTokenRequest(mark_as_read_token=mark_as_read_token)
        )


async def show_loading_animation(user_id: str, loading_seconds: int = 60) -> None:
    """Show the "..." loading indicator in a 1:1 chat.

    It disappears automatically once a reply/push message is sent (or
    after loading_seconds, whichever comes first), so it's safe to just
    set the max (60s) as a ceiling for slow agent turns. 1:1 chats only.
    """
    async with AsyncApiClient(_configuration()) as client:
        await AsyncMessagingApi(client).show_loading_animation(
            ShowLoadingAnimationRequest(chat_id=user_id, loading_seconds=loading_seconds)
        )
