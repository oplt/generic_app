import mimetypes
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.core.config import settings
from backend.core.storage import ObjectStorageError, StorageNotConfiguredError, object_storage
from backend.core.uploads import UploadTooLargeError, detect_image_content_type, read_upload_limited
from backend.modules.identity_access.models import User
from backend.modules.profile.schemas import ProfileResponse, ProfileUpdate
from backend.modules.profile.serializers import profile_to_response
from backend.modules.profile.service import ProfileService

router = APIRouter()


def _build_avatar_object_key(user_id: str, content_type: str) -> str:
    suffix = mimetypes.guess_extension(content_type) or ".bin"
    return f"avatars/{user_id}/{uuid4().hex}{suffix}"


@router.get("", response_model=ProfileResponse)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ProfileService(db)
    return await service.get_profile_response(current_user.id)


@router.put("", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ProfileService(db)
    profile = await service.update_profile(
        current_user.id, payload.bio, payload.location, payload.website
    )
    return profile_to_response(profile)


@router.post("/avatar", response_model=ProfileResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        payload = await read_upload_limited(
            file,
            max_bytes=settings.STORAGE_AVATAR_MAX_BYTES,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    if not payload:
        raise HTTPException(status_code=400, detail="Uploaded avatar file is empty")
    detected_content_type = detect_image_content_type(payload)
    if detected_content_type is None:
        raise HTTPException(status_code=400, detail="Avatar is not a supported image file")

    object_key = _build_avatar_object_key(current_user.id, detected_content_type)
    try:
        avatar_url = await object_storage.upload_bytes(
            object_key=object_key,
            body=payload,
            content_type=detected_content_type,
        )
    except StorageNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ObjectStorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    service = ProfileService(db)
    try:
        profile, previous_key = await service.replace_avatar(
            current_user.id,
            avatar_url=avatar_url,
            storage_key=object_key,
        )
    except Exception:
        await object_storage.delete_object(object_key)
        raise

    if previous_key and previous_key != object_key:
        await object_storage.delete_object(previous_key)
    return profile_to_response(profile)


@router.delete("/avatar", status_code=204)
async def delete_avatar(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = ProfileService(db)
    previous_key = await service.clear_avatar(current_user.id)
    await object_storage.delete_object(previous_key)
