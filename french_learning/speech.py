"""Offline macOS French speech synthesis with a small in-memory cache."""
from __future__ import annotations

import subprocess
import tempfile
from collections import OrderedDict
from pathlib import Path


class SpeechValidationError(ValueError):
    pass


class SpeechUnavailableError(RuntimeError):
    pass


class MacOSFrenchSpeech:
    voice = "Thomas"
    rate = 165

    def __init__(self, runner=subprocess.run, cache_size=128):
        self.runner = runner
        self.cache_size = cache_size
        self.cache = OrderedDict()

    def render(self, text):
        if not isinstance(text, str):
            raise SpeechValidationError("Texte invalide")
        text = " ".join(text.split())
        if not text or len(text) > 500:
            raise SpeechValidationError("Le texte doit contenir entre 1 et 500 caractères")
        if text in self.cache:
            self.cache.move_to_end(text)
            return self.cache[text]

        try:
            with tempfile.TemporaryDirectory(prefix="french-speech-") as folder:
                aiff_path = Path(folder) / "speech.aiff"
                m4a_path = Path(folder) / "speech.m4a"
                self.runner(
                    [
                        "/usr/bin/say",
                        "-v",
                        self.voice,
                        "-r",
                        str(self.rate),
                        "-o",
                        str(aiff_path),
                        text,
                    ],
                    check=True,
                    capture_output=True,
                    timeout=20,
                )
                self.runner(
                    [
                        "/usr/bin/afconvert",
                        "-f",
                        "m4af",
                        "-d",
                        "aac ",
                        "-q",
                        "127",
                        str(aiff_path),
                        str(m4a_path),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=20,
                )
                audio = m4a_path.read_bytes()
        except (OSError, subprocess.SubprocessError) as exc:
            raise SpeechUnavailableError("La voix française locale est indisponible") from exc

        if not audio:
            raise SpeechUnavailableError("La voix française locale n'a produit aucun son")
        self.cache[text] = audio
        self.cache.move_to_end(text)
        while len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return audio
