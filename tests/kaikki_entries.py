"""Kaikki (wiktextract) entries in the real layout, trimmed to the fields the loader reads."""

ENGLISH = [
    {"word": "read", "lang_code": "en", "pos": "verb", "senses": [{"glosses": ["To look at and interpret letters or other information."]}],
     "sounds": [{"ipa": "/ɹiːd/"}], "etymology_templates": [{"name": "inh", "args": {"1": "en", "2": "enm", "3": "reden"}}]},
    {"word": "read", "lang_code": "en", "pos": "noun", "senses": [{"glosses": ["A reading or interpretation."]}]},
    {"word": "readable", "lang_code": "en", "pos": "adj", "senses": [{"glosses": ["Able to be read."]}, {"glosses": ["Pleasant to read."]}],
     "etymology_templates": [{"name": "suffix", "args": {"1": "en", "2": "read", "3": "able"}, "expansion": "read + -able"}]},
    {"word": "unhappy", "lang_code": "en", "pos": "adj", "senses": [{"glosses": ["Not happy."]}],
     "etymology_templates": [{"name": "prefix", "args": {"1": "en", "2": "un", "3": "happy"}}]},
    {"word": "eyeball", "lang_code": "en", "pos": "noun", "senses": [{"glosses": ["The ball of the eye."]}],
     "etymology_templates": [{"name": "compound", "args": {"1": "en", "2": "eye", "3": "ball"}}]},
    {"word": "eyes", "lang_code": "en", "pos": "noun", "senses": [{"glosses": ["plural of eye"], "form_of": [{"word": "eye"}], "tags": ["form-of", "plural"]}]},
    {"word": "dictionary", "lang_code": "en", "pos": "noun", "senses": [{"glosses": ["A reference work."]}],
     "etymology_templates": [
         {"name": "der", "args": {"1": "en", "2": "la-med", "3": "dictiōnārium"}},
         {"name": "af", "args": {"1": "la", "2": "dīcō<t:to say>", "3": "-tiō"}},
         {"name": "surf", "args": {"1": "en", "2": "diction", "3": "-ary"}}]},
    {"word": "Wörterbuch", "lang_code": "de", "pos": "noun", "senses": [{"glosses": ["dictionary"]}]},
]

DUTCH = [
    {"word": "woordenboek", "lang_code": "nl", "pos": "noun", "senses": [{"glosses": ["dictionary"]}],
     "etymology_templates": [{"name": "af", "args": {"1": "nl", "2": "woord", "3": "-en-", "4": "boek", "t1": "word"}}]},
    {"word": "leesbaar", "lang_code": "nl", "pos": "adj", "senses": [{"glosses": ["readable"]}],
     "etymology_templates": [{"name": "af", "args": {"1": "nl", "2": "lezen", "3": "-baar"}}]},
]
