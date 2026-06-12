"""Functional tests for client crypto modules."""
import base64
from pathlib import Path

import pytest
from nacl.exceptions import CryptoError
from nacl.public import Box
from nacl.signing import SigningKey

from client.crypto.encryption import EncryptionManager
from client.crypto.key_manager import KeyManager
from client.crypto.signature import SignatureManager


# ---------------------------------------------------------------------------
# KeyManager tests
# ---------------------------------------------------------------------------


class TestKeyManager:
    """Tests for KeyManager: generation, loading, user_id, base64 encoding."""

    def test_generate_keys_creates_files(self, tmp_path: Path):
        """generate_keys should create private and public key files."""
        km = KeyManager(keys_dir=tmp_path)
        km.generate_keys()

        assert (tmp_path / "private_key.bin").exists()
        assert (tmp_path / "public_key.bin").exists()

    def test_has_keys_false_initially(self, tmp_path: Path):
        """has_keys should be False before generating."""
        km = KeyManager(keys_dir=tmp_path)
        assert km.has_keys is False

    def test_has_keys_true_after_generate(self, tmp_path: Path):
        """has_keys should be True after generating keys."""
        km = KeyManager(keys_dir=tmp_path)
        km.generate_keys()
        assert km.has_keys is True

    def test_load_keys_after_generate(self, tmp_path: Path):
        """load_keys should populate signing_key and public_key."""
        km = KeyManager(keys_dir=tmp_path)
        km.generate_keys()
        km.load_keys()

        assert km.signing_key is not None
        assert km.public_key is not None

    def test_load_keys_raises_without_generate(self, tmp_path: Path):
        """load_keys should raise FileNotFoundError if no keys exist."""
        km = KeyManager(keys_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            km.load_keys()

    def test_get_or_create_keys_generates_when_missing(self, tmp_path: Path):
        """get_or_create_keys should generate and load when keys don't exist."""
        km = KeyManager(keys_dir=tmp_path)
        km.get_or_create_keys()

        assert km.has_keys is True
        assert km.signing_key is not None

    def test_user_id_derivation(self, tmp_path: Path):
        """user_id should be SHA256 hex digest of the public key bytes."""
        import hashlib

        km = KeyManager(keys_dir=tmp_path)
        km.generate_keys()
        km.load_keys()

        expected_user_id = hashlib.sha256(km.public_key_bytes).hexdigest()
        assert km.user_id == expected_user_id
        assert len(km.user_id) == 64

    def test_public_key_base64_encoding(self, tmp_path: Path):
        """public_key_base64 should be valid base64 encoding of the key bytes."""
        km = KeyManager(keys_dir=tmp_path)
        km.generate_keys()
        km.load_keys()

        decoded = base64.b64decode(km.public_key_base64)
        assert decoded == km.public_key_bytes
        assert len(decoded) == 32

    def test_public_key_bytes_length(self, tmp_path: Path):
        """public_key_bytes should be exactly 32 bytes."""
        km = KeyManager(keys_dir=tmp_path)
        km.generate_keys()
        km.load_keys()

        assert len(km.public_key_bytes) == 32

    def test_signing_key_raises_without_load(self, tmp_path: Path):
        """Accessing signing_key before load should raise RuntimeError."""
        km = KeyManager(keys_dir=tmp_path)
        km.generate_keys()
        # Don't load keys
        with pytest.raises(RuntimeError):
            _ = km.signing_key

    def test_reload_keys_persistence(self, tmp_path: Path):
        """Keys should be identical when loaded by a different KeyManager instance."""
        km1 = KeyManager(keys_dir=tmp_path)
        km1.generate_keys()
        km1.load_keys()
        user_id_1 = km1.user_id
        pub_b64_1 = km1.public_key_base64

        km2 = KeyManager(keys_dir=tmp_path)
        km2.load_keys()
        assert km2.user_id == user_id_1
        assert km2.public_key_base64 == pub_b64_1

    def test_base64_to_public_key(self, tmp_path: Path):
        """base64_to_public_key should convert base64 string to VerifyKey."""
        km = KeyManager(keys_dir=tmp_path)
        km.generate_keys()
        km.load_keys()

        verify_key = KeyManager.base64_to_public_key(km.public_key_base64)
        assert bytes(verify_key) == km.public_key_bytes

    def test_base64_to_public_key_invalid(self):
        """base64_to_public_key should raise ValueError for invalid input."""
        with pytest.raises(ValueError):
            KeyManager.base64_to_public_key("not-valid-base64!!!")

    def test_base64_to_public_key_wrong_length(self):
        """base64_to_public_key should raise ValueError for wrong key length."""
        short_key = base64.b64encode(b"tooshort").decode()
        with pytest.raises(ValueError):
            KeyManager.base64_to_public_key(short_key)

    def test_user_id_from_public_key(self, tmp_path: Path):
        """user_id_from_public_key should match user_id property."""
        km = KeyManager(keys_dir=tmp_path)
        km.generate_keys()
        km.load_keys()

        uid = KeyManager.user_id_from_public_key(km.public_key)
        assert uid == km.user_id

    def test_delete_keys(self, tmp_path: Path):
        """delete_keys should remove key files from disk."""
        km = KeyManager(keys_dir=tmp_path)
        km.generate_keys()
        km.load_keys()

        km.delete_keys()
        assert not (tmp_path / "private_key.bin").exists()
        assert not (tmp_path / "public_key.bin").exists()
        assert km.has_keys is False


# ---------------------------------------------------------------------------
# EncryptionManager tests
# ---------------------------------------------------------------------------


class TestEncryptionManager:
    """Tests for EncryptionManager: encrypt/decrypt with NaCl Box."""

    def test_encrypt_decrypt_roundtrip(self):
        """Encrypting then decrypting should return the original plaintext."""
        sender_sk = SigningKey.generate()
        recipient_sk = SigningKey.generate()

        sender_private = sender_sk.to_curve25519_private_key()
        recipient_public = recipient_sk.verify_key.to_curve25519_public_key()
        recipient_private = recipient_sk.to_curve25519_private_key()
        sender_public = sender_sk.verify_key.to_curve25519_public_key()

        plaintext = "Hello, E2E encryption!"
        ciphertext, nonce = EncryptionManager.encrypt_message(
            plaintext, sender_private, recipient_public
        )
        decrypted = EncryptionManager.decrypt_message(
            ciphertext, nonce, recipient_private, sender_public
        )
        assert decrypted == plaintext

    def test_encrypt_to_base64_decrypt_from_base64_roundtrip(self):
        """Base64 encrypt/decrypt roundtrip should work correctly."""
        sender_sk = SigningKey.generate()
        recipient_sk = SigningKey.generate()

        sender_private = sender_sk.to_curve25519_private_key()
        recipient_public = recipient_sk.verify_key.to_curve25519_public_key()
        recipient_private = recipient_sk.to_curve25519_private_key()
        sender_public = sender_sk.verify_key.to_curve25519_public_key()

        plaintext = "Base64 roundtrip test message"
        ct_b64, nonce_b64 = EncryptionManager.encrypt_to_base64(
            plaintext, sender_private, recipient_public
        )

        # Verify base64 strings are valid
        assert base64.b64decode(ct_b64)
        assert base64.b64decode(nonce_b64)
        assert len(base64.b64decode(nonce_b64)) == 24

        decrypted = EncryptionManager.decrypt_from_base64(
            ct_b64, nonce_b64, recipient_private, sender_public
        )
        assert decrypted == plaintext

    def test_decrypt_with_wrong_key_fails(self):
        """Decrypting with the wrong private key should raise CryptoError."""
        sender_sk = SigningKey.generate()
        recipient_sk = SigningKey.generate()
        wrong_sk = SigningKey.generate()

        sender_private = sender_sk.to_curve25519_private_key()
        recipient_public = recipient_sk.verify_key.to_curve25519_public_key()
        sender_public = sender_sk.verify_key.to_curve25519_public_key()
        wrong_private = wrong_sk.to_curve25519_private_key()

        plaintext = "Secret message"
        ciphertext, nonce = EncryptionManager.encrypt_message(
            plaintext, sender_private, recipient_public
        )

        with pytest.raises(CryptoError):
            EncryptionManager.decrypt_message(
                ciphertext, nonce, wrong_private, sender_public
            )

    def test_convert_ed25519_to_curve25519(self):
        """convert_ed25519_to_curve25519 should return a Curve25519 public key."""
        sk = SigningKey.generate()
        vk = sk.verify_key

        curve_pk = EncryptionManager.convert_ed25519_to_curve25519(vk)
        # Should be 32 bytes
        assert len(bytes(curve_pk)) == 32

    def test_different_messages_produce_different_ciphertexts(self):
        """Encrypting different plaintexts should yield different ciphertexts."""
        sender_sk = SigningKey.generate()
        recipient_sk = SigningKey.generate()

        sender_private = sender_sk.to_curve25519_private_key()
        recipient_public = recipient_sk.verify_key.to_curve25519_public_key()

        ct1, _ = EncryptionManager.encrypt_message(
            "message one", sender_private, recipient_public
        )
        ct2, _ = EncryptionManager.encrypt_message(
            "message two", sender_private, recipient_public
        )
        assert ct1 != ct2

    def test_same_message_different_nonces(self):
        """Encrypting the same plaintext twice should produce different nonces."""
        sender_sk = SigningKey.generate()
        recipient_sk = SigningKey.generate()

        sender_private = sender_sk.to_curve25519_private_key()
        recipient_public = recipient_sk.verify_key.to_curve25519_public_key()

        _, nonce1 = EncryptionManager.encrypt_message(
            "same message", sender_private, recipient_public
        )
        _, nonce2 = EncryptionManager.encrypt_message(
            "same message", sender_private, recipient_public
        )
        assert nonce1 != nonce2


# ---------------------------------------------------------------------------
# SignatureManager tests
# ---------------------------------------------------------------------------


class TestSignatureManager:
    """Tests for SignatureManager: sign/verify with Ed25519."""

    def test_sign_verify_roundtrip_string(self):
        """Signing a string message and verifying should succeed."""
        sk = SigningKey.generate()
        vk = sk.verify_key

        message = "Hello, sign me!"
        signature = SignatureManager.sign_message(message, sk)
        assert SignatureManager.verify_signature(message, signature, vk) is True

    def test_sign_verify_roundtrip_bytes(self):
        """Signing raw bytes and verifying should succeed."""
        sk = SigningKey.generate()
        vk = sk.verify_key

        message = b"\x00\x01\x02\x03binary data"
        signature = SignatureManager.sign_message(message, sk)
        assert SignatureManager.verify_signature(message, signature, vk) is True

    def test_tampered_message_fails_verification(self):
        """Verifying a tampered message with original signature should fail."""
        sk = SigningKey.generate()
        vk = sk.verify_key

        message = "original message"
        signature = SignatureManager.sign_message(message, sk)
        assert SignatureManager.verify_signature("tampered message", signature, vk) is False

    def test_wrong_key_fails_verification(self):
        """Verifying with a different public key should fail."""
        sk = SigningKey.generate()
        wrong_sk = SigningKey.generate()
        wrong_vk = wrong_sk.verify_key

        message = "message"
        signature = SignatureManager.sign_message(message, sk)
        assert SignatureManager.verify_signature(message, signature, wrong_vk) is False

    def test_sign_to_base64_verify_from_base64(self):
        """sign_to_base64/verify_from_base64 should roundtrip correctly."""
        sk = SigningKey.generate()
        vk = sk.verify_key

        message = "base64 signature test"
        sig_b64 = SignatureManager.sign_to_base64(message, sk)

        # Verify it's valid base64
        sig_bytes = base64.b64decode(sig_b64)
        assert len(sig_bytes) == 64

        assert SignatureManager.verify_from_base64(message, sig_b64, vk) is True

    def test_verify_from_base64_tampered(self):
        """verify_from_base64 with tampered message should return False."""
        sk = SigningKey.generate()
        vk = sk.verify_key

        message = "original"
        sig_b64 = SignatureManager.sign_to_base64(message, sk)
        assert SignatureManager.verify_from_base64("tampered", sig_b64, vk) is False

    def test_sign_encrypted_message(self):
        """sign_encrypted_message should produce a valid signature over ciphertext+nonce."""
        sk = SigningKey.generate()
        vk = sk.verify_key

        encrypted_message = b"fake_encrypted_data_here"
        nonce = b"n" * 24

        signature = SignatureManager.sign_encrypted_message(encrypted_message, nonce, sk)
        assert len(signature) == 64

        # Verify using verify_encrypted_message
        assert SignatureManager.verify_encrypted_message(
            encrypted_message, nonce, signature, vk
        ) is True

    def test_verify_encrypted_message_tampered_ciphertext(self):
        """verify_encrypted_message with modified ciphertext should fail."""
        sk = SigningKey.generate()
        vk = sk.verify_key

        encrypted_message = b"original_encrypted_data"
        nonce = b"n" * 24

        signature = SignatureManager.sign_encrypted_message(encrypted_message, nonce, sk)

        # Tamper with ciphertext
        tampered = b"tampered_encrypted_data"
        assert SignatureManager.verify_encrypted_message(
            tampered, nonce, signature, vk
        ) is False

    def test_verify_encrypted_message_tampered_nonce(self):
        """verify_encrypted_message with modified nonce should fail."""
        sk = SigningKey.generate()
        vk = sk.verify_key

        encrypted_message = b"encrypted_data"
        nonce = b"n" * 24

        signature = SignatureManager.sign_encrypted_message(encrypted_message, nonce, sk)

        # Tamper with nonce
        bad_nonce = b"x" * 24
        assert SignatureManager.verify_encrypted_message(
            encrypted_message, bad_nonce, signature, vk
        ) is False

    def test_signature_length(self):
        """Ed25519 signatures should always be 64 bytes."""
        sk = SigningKey.generate()
        sig = SignatureManager.sign_message("test", sk)
        assert len(sig) == 64
