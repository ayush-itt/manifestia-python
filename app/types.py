from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

ReelRatio = Literal["9:16", "16:9"]
ReelType = Literal["ai_video", "stock_media", "images_only"]
StockReelMode = Literal["mixed", "images_only"]
ReelStatus = Literal["queued", "generating", "completed", "failed"]
SessionStatus = Literal["pending", "generating", "completed", "failed"]
SceneStatus = Literal["queued", "generating", "ready", "failed"]
SceneMediaType = Literal["ai_video", "stock_image", "stock_video"]
StockKind = Literal["video", "image"]
StockSourceId = Literal["pexels", "pixabay", "unsplash", "coverr", "nasa"]
KenBurnsAnimation = Literal[
    "zoom-in",
    "zoom-out",
    "pan-left",
    "pan-right",
    "pan-up",
    "pan-down",
    "ken-burns",
    "ken-burns-slow-zoom",
    "parallax",
    "static",
]


class StockCandidate(TypedDict):
    id: str
    source: StockSourceId
    sourceId: str
    sourceUrl: str
    downloadUrl: str
    previewUrl: str
    kind: StockKind
    width: int
    height: int
    durationSec: NotRequired[float | None]
    creator: str
    license: str
    tags: list[str]
    previewOnly: bool
    extra: NotRequired[dict[str, str]]


class DownloadedStock(TypedDict):
    candidate: StockCandidate
    path: str


class MusicTrack(TypedDict):
    id: str
    title: str
    mood: str
    tags: list[str]
    durationSec: float
    durationLabel: str
    fileName: str
    absolutePath: str
    fileUrl: str
    score: NotRequired[float]


class StoryReferenceImage(TypedDict):
    file: str
    role: str
    promptLabel: str


class StoryScene(TypedDict):
    sceneId: int
    title: str
    timecode: str
    duration: float
    prompt: str
    stockQuery: str
    voiceover: str
    referenceImages: list[StoryReferenceImage]
    localVideo: NotRequired[str]
    personalizedStill: NotRequired[str]
    generalizedStill: NotRequired[str]


class StoryTemplate(TypedDict):
    id: str
    title: str
    ratio: ReelRatio
    mood: str
    tags: list[str]
    script: str
    scenes: list[StoryScene]


class DeviceRow(TypedDict):
    device_id: str
    created_at: str
    last_seen_at: str


class SessionRow(TypedDict):
    session_id: str
    device_id: str
    onboarding_answers: str
    created_at: str
    completed_at: str | None
    status: SessionStatus


class ReelRow(TypedDict):
    reel_id: str
    session_id: str
    type: ReelType
    status: ReelStatus
    output_path: str | None
    duration_sec: float | None
    music_track_id: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    error_message: str | None
    progress: int


class SceneRow(TypedDict):
    scene_id: str
    reel_id: str
    scene_index: int
    title: str | None
    prompt: str | None
    voiceover: str | None
    reference_images: str
    media_type: SceneMediaType | None
    media_path: str | None
    duration_sec: float | None
    status: SceneStatus
    stock_query: str | None
    stock_source: str | None
    error_message: str | None
    created_at: str


class LibraryReelRow(ReelRow):
    device_id: str
    onboarding_answers: str
    session_status: SessionStatus
