import asyncio
import datetime
import os
import random

import ffmpeg


async def asyncio_command_exec(command_to_exec):
    process = await asyncio.create_subprocess_exec(
        *command_to_exec,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    return stdout, stderr


async def sync_to_async(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


async def get_video_details(video_path):
    """Gets video information like width, height, and duration.

    Args:
        video_path: The path to the video file.

    Returns:
        A dictionary containing the video information.
    """

    try:
        # video_info = ffmpeg.probe(video_path)
        video_info = await sync_to_async(ffmpeg.probe, video_path)
    except ffmpeg.Error as e:
        print(e.stderr.decode())
        raise e
    for stream in video_info["streams"]:
        if stream["codec_type"] == "video":
            width = stream["width"]
            height = stream["height"]
            duration = stream.get("duration", 0)
            if not duration:
                duration = video_info.get("format", {}).get("duration", 0)

            duration = str(duration)
            return width, height, int(duration.split(".")[0])
    return 0, 0, 0


async def create_thumbnail(inputpath):
    """Creates a thumbnail for a video file."""
    _, __, duration = await get_video_details(inputpath)
    if not duration:
        duration = 5
    random_duration = random.randint(1, duration)
    # make timestamp HH:MM:SS
    random_duration = str(datetime.timedelta(seconds=random_duration))

    def random_string(length):
        return "".join(random.choices("0123456789", k=length))

    outputpath = f"downloads/{random_string(10)}.jpg"
    try:
        await asyncio_command_exec(
            [
                "ffmpeg",
                "-ss",
                random_duration,
                "-i",
                inputpath,
                "-vframes",
                "1",
                outputpath,
            ]
        )
    except Exception as e:
        print(e)
        return None
    if not os.path.exists(outputpath):
        return None
    return outputpath


async def extract_media_languages(input_path):
    """
    Extracts the languages of the video, audio, and subtitle streams from a video file,
    including the stream index.

    Args:
        input_path: The path to the video file.

    Returns:
        A dictionary containing lists of dictionaries with index and language for each stream type.
        E.g., {'video': [{'index': 0, 'language': 'eng'}],
               'audio': [{'index': 1, 'language': 'eng'}, {'index': 2, 'language': 'fra'}],
               'subtitles': [{'index': 3, 'language': 'eng'}]}
    """
    try:
        video_info = await sync_to_async(ffmpeg.probe, input_path)
    except ffmpeg.errors as e:
        print(e.stderr.decode())
        raise e

    media_languages = {"video": [], "audio": [], "subtitles": []}
    audio_index, subtitle_index, video_index = 0, 0, 0

    for stream in video_info["streams"]:
        if "tags" in stream and "language" in stream["tags"]:
            # index be the total len of audio steams
            language_info = {
                "index": stream["index"],
                "language": stream["tags"]["language"],
            }
            if stream["codec_type"] == "video":
                language_info["index"] = video_index
                media_languages["video"].append(language_info)
                video_index += 1
            elif stream["codec_type"] == "audio":
                language_info["index"] = audio_index
                media_languages["audio"].append(language_info)
                audio_index += 1
            elif stream["codec_type"] == "subtitle":
                language_info["index"] = subtitle_index
                media_languages["subtitles"].append(language_info)
                subtitle_index += 1
    return media_languages


async def change_subtitle_tag_title(
    input_path, output_path, subtitle_titles, return_command=False
):
    """
    Changes the title tag of subtitle streams in a video file.

    Args:
        input_path: The path to the input video file.
        output_path: The path to the output video file.
        subtitle_titles: A dictionary where keys are subtitle stream indices (starting from 0)
                         and values are the new titles for those subtitle streams.
        return_command: If True, returns the command as a list of strings instead of executing it.

    Returns:
        The path to the output video file or the command list.
    """
    i_command = ["ffmpeg", "-i", input_path]
    command = []

    for index, title in subtitle_titles.items():
        command.extend([f"-metadata:s:s:{index}", f"title={title}"])

    if return_command:
        return command

    command = i_command + command
    command.extend([output_path])

    await asyncio_command_exec(command)

    if not os.path.exists(output_path):
        return None

    return output_path


async def change_audio_tag_title(
    input_path, output_path, audio_titles, return_command=False
):
    """
    Changes the title tag of audio streams in a video file.

    Args:
        input_path: The path to the input video file.
        output_path: The path to the output video file.
        audio_titles: A dictionary where keys are audio stream indices (starting from 0)
                      and values are the new titles for those audio streams.
        return_command: If True, returns the command as a list of strings instead of executing it.

    Returns:
        The path to the output video file or the command list.
    """
    i_command = ["ffmpeg", "-i", input_path]
    command = []

    for index, title in audio_titles.items():
        command.extend([f"-metadata:s:a:{index}", f"title={title}"])

    if return_command:
        return command

    command = i_command + command
    command.extend([output_path])

    await asyncio_command_exec(command)

    if not os.path.exists(output_path):
        return None

    return output_path


async def change_video_tag_title(
    input_path, output_path, video_titles, return_command=False
):
    """
    Changes the title tag of video streams in a video file.

    Args:
        input_path: The path to the input video file.
        output_path: The path to the output video file.
        video_titles: A dictionary where keys are video stream indices (starting from 0)
                      and values are the new titles for those video streams.
        return_command: If True, returns the command as a list of strings instead of executing it.

    Returns:
        The path to the output video file or the command list.
    """
    i_command = ["ffmpeg", "-i", input_path]
    command = []

    for index, title in video_titles.items():
        command.extend([f"-metadata:s:v:{index}", f"title={title}"])

    if return_command:
        return command

    command = i_command + command
    command.extend([output_path])

    await asyncio_command_exec(command)

    if not os.path.exists(output_path):
        return None

    return output_path


async def change_format_tag_title(input_path, output_path, title, return_command=False):
    """
    Changes the title tag in the format metadata of a video file.

    Args:
        input_path: The path to the input video file.
        output_path: The path to the output video file.
        title: The new title for the format metadata.
        return_command: If True, returns the command as a list of strings instead of executing it.

    Returns:
        The path to the output video file or the command list.
    """
    i_command = ["ffmpeg", "-i", input_path]
    command = []

    # Set the format title metadata
    command.extend(["-metadata", f"title={title}"])

    if return_command:
        return command

    command.extend([output_path])

    await asyncio_command_exec(i_command + command)

    if not os.path.exists(output_path):
        return None

    return output_path


async def apply_metadata(file_path: str, user: dict):
    command = []

    metadata = user["metadata"]
    title = metadata["title"]
    artist = metadata["artist"]
    author = metadata["author"]
    audio = metadata["audio"]
    subtitle = metadata["subtitle"]

    if not any(
        [
            title["status"],
            artist["status"],
            author["status"],
            audio["status"],
            subtitle["status"],
        ]
    ):
        return file_path

    media_languages = await extract_media_languages(file_path)
    audio_languages = media_languages["audio"]
    subtitle_languages = media_languages["subtitles"]
    video_languages = media_languages["video"]

    if audio["status"] and audio_languages and audio["text"]:
        audio_info = {}
        for audio_language in audio_languages:
            new_title = (
                f"{audio['text']} - {get_lang_from_code(audio_language['language'])}"
            )
            audio_info[audio_language["index"]] = new_title

        command.extend(
            await change_audio_tag_title(
                file_path, file_path, audio_info, return_command=True
            )
        )

    if subtitle["status"] and subtitle_languages and subtitle["text"]:
        subtitle_info = {}
        for subtitle_language in subtitle_languages:
            new_title = f"{subtitle['text']} - {get_lang_from_code(subtitle_language['language'])}"
            subtitle_info[subtitle_language["index"]] = new_title

        command.extend(
            await change_subtitle_tag_title(
                file_path, file_path, subtitle_info, return_command=True
            )
        )

    if title["status"] and title["text"]:
        command.extend(
            await change_format_tag_title(
                file_path, file_path, title["text"], return_command=True
            )
        )

        video_info = {}
        for video_language in video_languages:
            new_title = (
                f"{title['text']} - {get_lang_from_code(video_language['language'])}"
            )
            video_info[video_language["index"]] = new_title

        command.extend(
            await change_video_tag_title(
                file_path, file_path, video_info, return_command=True
            )
        )

    filename = os.path.basename(file_path)
    output_path = f"downloads/output_{filename}"
    i_command = ["ffmpeg", "-i", file_path, "-c", "copy", "-y", "-map", "0"]
    command = i_command + command
    command.extend([output_path])
    print(" ".join(command))
    await asyncio_command_exec(command)
    os.remove(file_path)
    return output_path


def get_lang_from_code(code: str) -> str:
    # Dictionary mapping language codes to language names
    data = {
        "eng": "English",
        "hin": "Hindi",
        "tam": "Tamil",
        "tel": "Telugu",
        "bn": "Bengali",
        "kan": "Kannada",
        "mal": "Malayalam",
        "mar": "Marathi",
        "guj": "Gujarati",
        "pun": "Punjabi",
        "odi": "Odia",
        "as": "Assamese",
        "urd": "Urdu",
        "sa": "Sanskrit",
    }

    # Return the language name corresponding to the code, or 'Unknown' if the code is not found
    return data.get(code, "Unknown")
