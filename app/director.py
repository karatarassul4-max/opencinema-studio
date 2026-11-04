"""Deterministic direction with explicit camera text taking precedence.

Conservative cue detection suppresses camera defaults even for negative camera
instructions. It never rewrites user intent or tries to resolve contradictory
instructions inside the user's own description.
"""
import json
import re
from pathlib import Path

SCENES = json.loads((Path(__file__).resolve().parents[1] / 'config/scenes.json').read_text(encoding='utf-8'))
CAMERAS = {
    'dolly': 'A cinematic dolly inward toward the subject with continuous forward camera motion.',
    'orbit': 'A cinematic orbit around the subject with continuous lateral perspective change.',
    'crane': 'A crane upward gradually reveals the surrounding scene.',
    'static': 'A locked-off camera holds its position while the described subject motion unfolds.',
}
MOODS = {'calm': 'calm', 'dramatic': 'dramatic', 'warm': 'warm and inviting', 'mysterious': 'mysterious'}
# Broad cues deliberately prefer omission over appending a conflicting default.
CAMERA_CUES = re.compile(
    r"\b(camera|doll(?:y|ies|ying)|orbit(?:s|ing|al)?|crane|cranes|craning|"
    r"pan(?:s|ning)?|tilt(?:s|ing)?|zoom(?:s|ing)?|tracking|track|truck(?:ing)?|"
    r"handheld|steadicam|gimbal|push[ -]?in|pull[ -]?(?:out|back)|"
    r"locked[ -]?off|lock[ -]?off|static|stationary|aerial|drone|"
    r"viewpoint|perspective|point[ -]of[ -]view|pov)\b", re.IGNORECASE)
LIGHT_CUES = re.compile(r'\b(light(?:s|ing)?|lit|sun(?:rise|set|light)?|moon(?:light)?|dark(?:ness)?|shadow(?:s)?|neon|backlit|rimlit|candle(?:light)?)\b', re.IGNORECASE)


def direct(description, scene='product', camera='static', mood='calm'):
    if not description.strip() or len(description) > 3000:
        raise ValueError('Enter a description between 1 and 3000 characters.')
    if (scene is not None and scene not in SCENES) or camera not in CAMERAS or mood not in MOODS:
        raise ValueError('Choose a supported scene, camera and mood.')
    subject = ' '.join(description.split())
    explicit_camera = bool(CAMERA_CUES.search(subject))
    camera_text = ('Follow the camera directions and restrictions in the scene description.'
                   if explicit_camera else CAMERAS[camera])
    template = SCENES[scene] if scene else None
    lighting = (('Use the lighting described in the scene.' if LIGHT_CUES.search(subject)
                 else template['lighting']) if template else '')
    parts = dict(subject=subject, camera=camera_text, lighting=lighting,
                 environment=template['environment'] if template else '',
                 motion_constraints=template['motion'] if template else '',
                 mood=f"Use a {MOODS[mood]} tone where consistent with the described scene." if template else '')
    # One flowing paragraph; subject text is kept, only whitespace is normalized.
    prompt = ' '.join(value if value.endswith(('.', '!', '?')) else value + '.'
                      for value in parts.values() if value)
    return {**parts, 'prompt': prompt, 'camera_source': 'description' if explicit_camera else 'preset',
            'camera_note': ('Explicit camera wording takes precedence over the selected preset.'
                            if explicit_camera else 'Using the selected camera preset.')}
