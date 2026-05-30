from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config.settings import Settings
from app.db.models import MediaAsset, PostJob


class XPublisherError(RuntimeError):
    pass


@dataclass(frozen=True)
class XPublishResult:
    x_post_id: str
    media_ids: list[str]


class XPublisher:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._validate_credentials()

    def publish(self, post_job: PostJob) -> XPublishResult:
        import tweepy

        auth = tweepy.OAuth1UserHandler(
            self.settings.x_api_key,
            self.settings.x_api_secret,
            self.settings.x_access_token,
            self.settings.x_access_token_secret,
        )
        api = tweepy.API(auth)
        client = tweepy.Client(
            consumer_key=self.settings.x_api_key,
            consumer_secret=self.settings.x_api_secret,
            access_token=self.settings.x_access_token,
            access_token_secret=self.settings.x_access_token_secret,
        )

        media_ids = [self._upload_media(api, media_asset) for media_asset in post_job.media_assets]
        text = build_x_post_text(post_job)
        response = client.create_tweet(text=text, media_ids=media_ids, user_auth=True)
        data = getattr(response, "data", None) or {}
        x_post_id = data.get("id")
        if not x_post_id:
            raise XPublisherError("X投稿レスポンスにpost idが含まれていません")
        return XPublishResult(x_post_id=str(x_post_id), media_ids=media_ids)

    def _upload_media(self, api, media_asset: MediaAsset) -> str:
        if not media_asset.processed_path:
            raise XPublisherError("processed_pathが未設定のメディアは投稿できません")
        media_path = Path(media_asset.processed_path)
        if not media_path.exists():
            raise XPublisherError(f"投稿用メディアが存在しません: {media_path}")

        media_category = "tweet_video" if media_asset.media_type == "video" else "tweet_image"
        uploaded = api.media_upload(
            filename=str(media_path),
            media_category=media_category,
            chunked=media_asset.media_type == "video",
        )
        media_id = getattr(uploaded, "media_id_string", None) or getattr(uploaded, "media_id", None)
        if media_id is None:
            raise XPublisherError("Xメディアアップロードレスポンスにmedia_idが含まれていません")
        return str(media_id)

    def _validate_credentials(self) -> None:
        missing = [
            name
            for name, value in {
                "X_API_KEY": self.settings.x_api_key,
                "X_API_SECRET": self.settings.x_api_secret,
                "X_ACCESS_TOKEN": self.settings.x_access_token,
                "X_ACCESS_TOKEN_SECRET": self.settings.x_access_token_secret,
            }.items()
            if not value
        ]
        if missing:
            raise XPublisherError(f"X投稿に必要な環境変数が未設定です: {', '.join(missing)}")


def build_x_post_text(post_job: PostJob) -> str:
    parts = [post_job.caption or ""]
    if post_job.hashtags_json:
        import json

        hashtags = json.loads(post_job.hashtags_json)
        if hashtags:
            parts.append(" ".join(hashtags))
    return "\n\n".join(part for part in parts if part).strip()
