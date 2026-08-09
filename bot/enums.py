from enum import Enum


class CaptionVariables(Enum):
    FILE_NAME = "title"
    MIME_TYPE = "mime_type"
    EXTENSION = "extension"
    FILE_SIZE = "size"
    QUALITY = "quality"
    DURATION = "duration"
    SUBTITLES_LANGUAGE = "subtitle"
    AUDIO_LANGUAGE = "audio"
    CAPTION = "caption"

    INFO = {
        FILE_NAME: "Name of the file, including the extension",
        MIME_TYPE: "MIME type of the file, indicating its media type",
        EXTENSION: "File extension (e.g., .mp4, .avi)",
        QUALITY: "Quality of the video (e.g., 720p, 1080p)",
        FILE_SIZE: "Size of the file",
        DURATION: "Duration of the video",
        SUBTITLES_LANGUAGE: "Language of the subtitles",
        AUDIO_LANGUAGE: "Language of the audio track",
        CAPTION: "Caption of the file",
    }


class FileUploadMode(Enum):
    DEFAULT = "default"
    VIDEO = "video"
    DOCUMENT = "document"


class TransferStatus(Enum):
    IN_PROGRESS = "in_progress"
    CANCELLED = "cancelled"
    SLEEPING = "sleeping"
