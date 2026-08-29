(() => {
  const originalStopSpeech = stopSpeech;

  stopSpeech = function () {
    window.speechSynthesis?.cancel();
    originalStopSpeech();
  };

  speak = function (text, button) {
    stopSpeech();
    if (!('speechSynthesis' in window)) {
      setStatus('La synthèse vocale du navigateur n’est pas disponible.', true);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(String(text));
    utterance.lang = 'fr-FR';
    utterance.rate = 0.92;
    const original = button.innerHTML;
    button.disabled = true;
    button.textContent = '▶ Lecture…';
    utterance.onend = utterance.onerror = () => {
      button.disabled = false;
      button.innerHTML = original;
    };
    window.speechSynthesis.speak(utterance);
  };
})();
