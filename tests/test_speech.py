import subprocess
import unittest
from pathlib import Path

from french_learning.speech import (
    MacOSFrenchSpeech,
    SpeechUnavailableError,
    SpeechValidationError,
)


class FrenchSpeechTest(unittest.TestCase):
    def test_renders_thomas_voice_as_m4a_and_caches_it(self):
        commands = []

        def runner(command, **kwargs):
            commands.append((command, kwargs))
            output = Path(command[command.index("-o") + 1]) if command[0].endswith("say") else Path(command[-1])
            output.write_bytes(b"aiff" if command[0].endswith("say") else b"m4a-audio")
            return subprocess.CompletedProcess(command, 0)

        speech = MacOSFrenchSpeech(runner=runner)
        first = speech.render(" Bonjour   à tous. ")
        second = speech.render("Bonjour à tous.")

        self.assertEqual(b"m4a-audio", first)
        self.assertEqual(first, second)
        self.assertEqual(2, len(commands))
        self.assertEqual("Thomas", commands[0][0][commands[0][0].index("-v") + 1])
        self.assertEqual("aac ", commands[1][0][commands[1][0].index("-d") + 1])
        self.assertTrue(all(call[1]["check"] for call in commands))
        self.assertTrue(all(call[1]["capture_output"] for call in commands))

    def test_rejects_empty_non_text_and_oversized_input(self):
        speech = MacOSFrenchSpeech(runner=lambda *_args, **_kwargs: None)
        for value in (None, "", " " * 5, "x" * 501):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(SpeechValidationError):
                    speech.render(value)

    def test_hides_subprocess_details_when_rendering_fails(self):
        def runner(_command, **_kwargs):
            raise subprocess.CalledProcessError(1, "say", stderr=b"private detail")

        with self.assertRaisesRegex(SpeechUnavailableError, "voix française locale") as caught:
            MacOSFrenchSpeech(runner=runner).render("Bonjour")
        self.assertNotIn("private detail", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
