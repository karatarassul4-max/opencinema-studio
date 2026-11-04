
"""Explicit duration allowlist; sampler-valid does not mean VRAM-tested."""

DURATIONS = {
    25: {
        'label': '25 frames · 1.04 s · baseline',
        'workflow': 'ltx13b-v2-api.json',
        'experimental': False,
    },
    49: {
        'label': '49 frames · 2.04 s · tested experimental',
        'workflow': 'ltx13b-v2-49f-experimental-api.json',
        'experimental': True,
    },
    73: {
        'label': '73 frames · 3.04 s · unverified experimental',
        'workflow': 'ltx13b-v2-73f-experimental-api.json',
        'experimental': True,
    },
    97: {
        'label': '97 frames · 4.04 s · untested experimental',
        'workflow': 'ltx13b-v2-97f-experimental-api.json',
        'experimental': True,
    },
}

FPS = 24


def duration_settings(frames=25):
    if type(frames) is not int or frames not in DURATIONS or (frames - 1) % 8:
        raise ValueError('Choose 25, 49, 73 or 97 frames.')

    return {
        **DURATIONS[frames],
        'frames': frames,
        'fps': FPS,
        'duration_seconds': frames / FPS,
    }
