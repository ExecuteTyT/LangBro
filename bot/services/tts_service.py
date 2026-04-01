import asyncio
import hashlib
import logging
import time
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)

VOICE_CACHE_DIR = Path("voice_cache")
CACHE_TTL_DAYS = 30

VOICES = {
    "us_male": "en-US-GuyNeural",
    "us_female": "en-US-AriaNeural",
    "uk_male": "en-GB-RyanNeural",
    "uk_female": "en-GB-SoniaNeural",
    "au_male": "en-AU-WilliamNeural",
}


class TTSService:
    """Text-to-Speech via Edge TTS with local OGG Opus caching."""

    def __init__(self) -> None:
        VOICE_CACHE_DIR.mkdir(exist_ok=True)

    @staticmethod
    def _cache_key(text: str, voice_id: str, rate: str) -> str:
        return hashlib.md5(f"{text}:{voice_id}:{rate}".encode()).hexdigest()

    async def generate_voice(
        self, text: str, voice: str = "us_male", rate: str = "+0%"
    ) -> Path:
        """Generate an OGG Opus voice file. Returns cached path if available."""
        voice_id = VOICES.get(voice, VOICES["us_male"])
        key = self._cache_key(text, voice_id, rate)
        ogg_path = VOICE_CACHE_DIR / f"{key}.ogg"

        if ogg_path.exists():
            return ogg_path

        mp3_path = VOICE_CACHE_DIR / f"{key}.mp3"
        try:
            communicate = edge_tts.Communicate(text=text, voice=voice_id, rate=rate)
            await communicate.save(str(mp3_path))

            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", str(mp3_path),
                "-c:a", "libopus", "-b:a", "48k",
                str(ogg_path), "-y",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.wait()

            if proc.returncode != 0:
                logger.error("ffmpeg conversion failed for key %s", key)
                raise RuntimeError("ffmpeg conversion failed")

            return ogg_path
        finally:
            if mp3_path.exists():
                mp3_path.unlink(missing_ok=True)

    async def generate_wotd_voice(
        self, word: str, example: str, voice: str = "us_male"
    ) -> Path:
        """Word (slow) + 1s pause + example (normal speed)."""
        combined_key = hashlib.md5(
            f"wotd:{word}:{example}:{voice}".encode()
        ).hexdigest()
        combined_path = VOICE_CACHE_DIR / f"wotd_{combined_key}.ogg"

        if combined_path.exists():
            return combined_path

        word_path = await self.generate_voice(word, voice, rate="-30%")
        example_path = await self.generate_voice(example, voice, rate="+0%")

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-i", str(word_path),
            "-i", str(example_path),
            "-filter_complex",
            "[0]apad=pad_dur=1[a];[a][1]concat=n=2:v=0:a=1",
            "-c:a", "libopus", "-b:a", "48k",
            str(combined_path), "-y",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

        if proc.returncode != 0:
            logger.error("ffmpeg wotd concat failed for word '%s'", word)
            raise RuntimeError("ffmpeg wotd concat failed")

        return combined_path

    async def cleanup_expired_cache(self) -> int:
        """Delete cache files older than TTL. Returns count of deleted files."""
        cutoff = time.time() - CACHE_TTL_DAYS * 86400
        deleted = 0
        for f in VOICE_CACHE_DIR.glob("*.ogg"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                deleted += 1
        logger.info("TTS cache cleanup: deleted %d expired files", deleted)
        return deleted
