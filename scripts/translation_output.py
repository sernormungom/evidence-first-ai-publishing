"""Parse translation content; canonical code owns all copied metadata."""
import json
import re
import yaml

import authoring


def assemble(response, canonical, english):
    text = response.strip()
    if text.startswith('```') and text.endswith('```'):
        text = re.sub(r'\A```(?:json)?\s*\n', '', text)
        text = text.rsplit('```', 1)[0].strip()
    # Some providers emit literal newlines/tabs inside JSON strings. Decoding
    # those whitespace characters verbatim changes no employee wording.
    data = json.loads(text, strict=False)
    def check_controls(value):
        if isinstance(value, str) and any(ord(c) < 32 and c not in '\n\r\t' for c in value):
            raise ValueError('Unexpected control character in translation')
        if isinstance(value, dict):
            for item in value.values():
                check_controls(item)
        if isinstance(value, list):
            for item in value:
                check_controls(item)
    check_controls(data)
    if isinstance(data, dict) and set(data) == {'title', 'answers', 'body'}:
        # Recover a missing non-reader field without claiming the translator
        # assessed ambiguity or changing any employee wording.
        data['notes'] = ('Coordinator recovery: translator omitted the notes field; '
                         'no translator ambiguity assessment was supplied.')
    required = {'title', 'answers', 'body', 'notes'}
    if not isinstance(data, dict) or set(data) != required:
        raise ValueError('Translation must contain exactly title, answers, body, notes')
    if not isinstance(data['title'], str) or not data['title'].strip():
        raise ValueError('Missing Swedish title')
    if (not isinstance(data['answers'], list) or
            len(data['answers']) != len(canonical.get('answers', [])) or
            any(not isinstance(q, str) or not q.strip() for q in data['answers'])):
        raise ValueError('Swedish answers must match canonical question count')
    if not isinstance(data['body'], str) or not isinstance(data['notes'], str):
        raise ValueError('Swedish body and notes must be text')
    body = data['body'].strip()
    if body.startswith('---') or '## Review notes' in body:
        raise ValueError('Body contains metadata or reviewer material')
    fm = dict(canonical)
    for key in ('review_notes_for_drafter', 'reader_design'):
        fm.pop(key, None)
    fm.update(title=data['title'], answers=data['answers'], language='sv',
              translated_from=authoring.translation_hash(english, 'reader-v1'),
              translation_hash_mode='reader-v1')
    return fm, '\n\n' + body + '\n', data['notes']
