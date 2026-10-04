"""PINs, ΑΦΜ checks, QR codes and the device registration codes."""
import pytest

from app import security


def test_pin_hash_round_trip():
    h = security.hash_pin("482916")
    assert h != "482916"
    assert security.verify_pin(h, "482916")
    assert not security.verify_pin(h, "482917")
    assert not security.verify_pin("not-a-hash", "482916")


@pytest.mark.parametrize("pin", ["123456", "987654", "111111", "121212", "000000"])
def test_easy_pins_are_weak(pin):
    assert security.weak_pin(pin)


@pytest.mark.parametrize("pin", ["482916", "730194"])
def test_normal_pins_are_not_weak(pin):
    assert not security.weak_pin(pin)


def test_generated_pins_are_valid_and_not_weak():
    for _ in range(200):
        pin = security.generate_pin()
        assert security.valid_pin_format(pin)
        assert not security.weak_pin(pin)


@pytest.mark.parametrize("pin, ok", [("482916", True), ("48291", False), ("4829167", False), ("48a916", False), ("", False)])
def test_pin_format(pin, ok):
    assert security.valid_pin_format(pin) is ok


@pytest.mark.parametrize("afm, ok", [("123456783", True), ("123456789", False), ("000000000", False),
                                     ("12345678", False), ("12345678a", False)])
def test_afm_checksum(afm, ok):
    assert security.valid_afm(afm) is ok


def test_qr_codes_are_unique_and_recognised():
    a, b = security.new_qr_code(), security.new_qr_code()
    assert a != b
    assert security.normalize_qr(a) == a
    assert security.normalize_qr(" " + a.lower() + " ") == a
    assert security.normalize_qr("hello") is None


def test_ergani_qr_is_parsed():
    eq = security.parse_ergani_qr("﻿erg|nm:ΜΑΡΙΑ;ln:ΠΑΠΑΔΟΠΟΥΛΟΥ;afm:900000001;id:12345")
    assert eq["afm"] == "900000001"
    assert eq["ln"] == "ΠΑΠΑΔΟΠΟΥΛΟΥ"
    assert eq["id"] == "12345"
    assert security.parse_ergani_qr("CK1:SOMETHING") is None


def test_surname_match_ignores_accents_and_case():
    assert security.name_key("Παπαδοπούλου") == security.name_key("ΠΑΠΑΔΟΠΟΥΛΟΥ")


def test_qr_svg_is_an_svg():
    assert security.qr_svg(security.new_qr_code()).lstrip().startswith("<svg")


def test_enroll_codes_avoid_confusable_characters():
    code = security.new_enroll_code()
    assert len(code) == 8
    assert not set(code) & set("01OIL")
    assert security.normalize_enroll_code(code[:4].lower() + "-" + code[4:]) == code
