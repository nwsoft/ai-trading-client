"""Account-local presentation preferences, separate from trading settings/approval."""
import json
import os
import tempfile
from pathlib import Path


def normalize_locale(value):
    return 'en' if str(value or '').lower().split('-')[0]=='en' else 'ko'


def read_preferences(directory):
    try:
        data=json.loads((Path(directory)/'display_preferences.json').read_text(encoding='utf-8'))
        return {'locale':normalize_locale(data.get('locale')),'saved':True}
    except (OSError,ValueError,TypeError,AttributeError):
        return {'locale':'ko','saved':False}


def save_preferences(directory,locale):
    if locale not in ('ko','en'):raise ValueError('unsupported_display_locale')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='display-preferences-',suffix='.tmp',dir=directory)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump({'locale':locale},stream);stream.flush();os.fsync(stream.fileno())
        os.replace(name,directory/'display_preferences.json')
    finally:
        if os.path.exists(name):os.unlink(name)
    return read_preferences(directory)
