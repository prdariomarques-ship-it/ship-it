"""FAKE -- an empty stand-in class, only so jobs/handlers.py's
`isinstance(provider, EvolutionProvider)` check has something real to
check against. FAKE_PROVIDER (the one actually returned by
get_whatsapp_provider in this test suite) is deliberately NOT an
instance of this, so send_whatsapp_text takes its generic
`provider.send_text(to, content)` branch -- the simpler, more common
path, sufficient for proving zero-calls under the blocking conditions
this round is about."""


class EvolutionProvider:
    pass
