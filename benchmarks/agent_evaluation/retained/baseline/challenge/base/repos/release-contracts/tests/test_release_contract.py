from scripts.verify_checksum import verify_checksum

def test_release_checksum_contract():
    assert verify_checksum('a', 'a')
