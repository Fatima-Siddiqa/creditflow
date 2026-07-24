import httpx

UGC_POSTS_URL = "https://api.linkedin.com/v2/ugcPosts"
REGISTER_UPLOAD_URL = "https://api.linkedin.com/v2/assets?action=registerUpload"


async def register_upload(access_token: str, member_urn: str) -> tuple[str, str]:
    """Returns (upload_url, asset_urn)."""
    body = {"registerUploadRequest": {"recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                                       "owner": member_urn, "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}]}}
    async with httpx.AsyncClient() as client:
        resp = await client.post(REGISTER_UPLOAD_URL, json=body, headers={"Authorization": f"Bearer {access_token}"})
        resp.raise_for_status()
        data = resp.json()["value"]
        return data["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"], data["asset"]


async def upload_binary(upload_url: str, access_token: str, image_bytes: bytes) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.put(upload_url, content=image_bytes, headers={"Authorization": f"Bearer {access_token}"})
        resp.raise_for_status()


async def publish_ugc_post(access_token: str, member_urn: str, text: str, asset_urn: str | None = None) -> str:
    """Returns the LinkedIn post URN. asset_urn=None -> text-only post."""
    media = [{"status": "READY", "media": asset_urn}] if asset_urn else []
    body = {
        "author": member_urn, "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": {
            "shareCommentary": {"text": text},
            "shareMediaCategory": "IMAGE" if asset_urn else "NONE",
            "media": media,
        }},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(UGC_POSTS_URL, json=body, headers={"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0"})
        resp.raise_for_status()
        return resp.headers.get("x-restli-id", resp.json().get("id", ""))