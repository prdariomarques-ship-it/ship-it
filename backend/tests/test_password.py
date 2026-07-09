from auth.password import hash_password, verify_password


def test_hash_and_verify_roundtrip():
    hashed = hash_password("minha-senha-segura")
    assert hashed != "minha-senha-segura"
    assert verify_password("minha-senha-segura", hashed)
    assert not verify_password("senha-errada", hashed)


def test_verify_rejects_malformed_hash():
    assert not verify_password("qualquer", "not-a-valid-hash")
    assert not verify_password("qualquer", "")


def test_hashes_are_salted():
    assert hash_password("mesma-senha") != hash_password("mesma-senha")
