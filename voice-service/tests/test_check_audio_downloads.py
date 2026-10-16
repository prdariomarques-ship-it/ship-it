"""check_audio_downloads: arquivos reais minúsculos (WAV/Ogg montados à mão); só lê, nunca altera a pasta."""
import struct
import wave

from scripts import check_audio_downloads as cad


def _wav(path, seconds=1, rate=8000):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x01\x00" * (seconds * rate))
    return path


def _ogg(path, *, eos=True):
    def page(flags):
        return b"OggS" + bytes([0, flags]) + b"\x00" * 8 + b"\x01\x00\x00\x00" + b"\x00" * 4 + b"\x00\x00\x00\x00" + b"\x01\x01" + b"x"
    path.write_bytes(page(0x02) + page(0x00) + page(0x04 if eos else 0x00))
    return path


def test_wav_completo_passa_e_cortado_falha(tmp_path):
    good = _wav(tmp_path / "a.wav")
    assert cad.check_file(good) is None
    cut = tmp_path / "b.wav"
    cut.write_bytes(good.read_bytes()[:5000])
    assert "cortado" in cad.check_file(cut)
    junk = tmp_path / "c.wav"
    junk.write_bytes(b"isso nao e wav" * 3)
    assert "inválido" in cad.check_file(junk)


def test_ogg_com_fim_de_fluxo_passa_e_sem_ele_falha(tmp_path):
    assert cad.check_file(_ogg(tmp_path / "ok.ogg")) is None
    assert "cortado" in cad.check_file(_ogg(tmp_path / "cut.ogg", eos=False))
    bad = tmp_path / "x.ogg"
    bad.write_bytes(b"ABCD" * 20)
    assert "OggS" in cad.check_file(bad)


def test_vazio_parcial_e_tamanho_diferente_do_esperado(tmp_path):
    empty = tmp_path / "e.mp3"
    empty.write_bytes(b"")
    assert cad.check_file(empty) == "arquivo vazio"
    part = tmp_path / "f.ogg.part"
    part.write_bytes(b"x")
    assert "andamento" in cad.check_file(part)
    mp3 = tmp_path / "m.mp3"
    mp3.write_bytes(b"x" * 100)
    assert cad.check_file(mp3) is None and cad.check_file(mp3, 100) is None
    assert "esperado 150" in cad.check_file(mp3, 150)


def test_run_separa_completos_incompletos_e_faltando_sem_mexer_na_pasta(tmp_path):
    _wav(tmp_path / "ok.wav")
    (tmp_path / "cortado.wav").write_bytes((tmp_path / "ok.wav").read_bytes()[:3000])
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    expected = {"ok.wav": None, "cortado.wav": None, "nunca_veio.ogg": None}
    ok, problems, missing = cad.run(tmp_path, expected)
    assert ok == ["ok.wav"] and [n for n, _ in problems] == ["cortado.wav"] and missing == ["nunca_veio.ogg"]
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_main_grava_so_os_que_precisam_ser_refeitos(tmp_path, capsys):
    pasta = tmp_path / "audios"
    pasta.mkdir()
    _wav(pasta / "ok.wav")
    (pasta / "cortado.wav").write_bytes((pasta / "ok.wav").read_bytes()[:3000])
    lista = tmp_path / "lista.txt"
    lista.write_text("ok.wav\ncortado.wav\nfalta.ogg,123\n# comentario\n", encoding="utf-8")
    assert cad.main(["--pasta", str(pasta), "--esperados", str(lista), "--saida", str(tmp_path / "faltam.txt")]) == 1
    assert (tmp_path / "faltam.txt").read_text(encoding="utf-8").split() == ["cortado.wav", "falta.ogg"]
    assert cad.main(["--pasta", str(tmp_path / "nao_existe")]) == 2
    (pasta / "cortado.wav").write_bytes((pasta / "ok.wav").read_bytes())
    assert cad.main(["--pasta", str(pasta), "--saida", str(tmp_path / "f2.txt")]) == 0
    assert (tmp_path / "f2.txt").read_text(encoding="utf-8") == ""
