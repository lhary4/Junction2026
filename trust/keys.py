"""The three ES256 keys (manager, agent, merchant) and the two primitives everything signs with.

Private keys are jwcrypto JWK objects and never leave their owner. Public keys travel as plain dicts (JWK JSON).
The demo keys live in contract/fixtures/keys/: DEMO ONLY, they protect nothing real.
"""

import json
from pathlib import Path

from ap2.sdk.utils import b64url_decode
from jwcrypto.jwk import JWK
from jwcrypto.jws import JWS

from trust import TrustError

KEYS_DIR = Path(__file__).resolve().parent.parent / "contract" / "fixtures" / "keys"
NAMES = ("manager", "agent", "merchant")
MERCHANT_ID = "valio-aimo"


def write_demo_keys(directory: Path = KEYS_DIR) -> list[str]:
    """Create the keys that are missing, never overwrite one. Returns the names it created."""
    directory.mkdir(parents=True, exist_ok=True)
    created = []
    for name in NAMES:
        path = directory / f"{name}.json"
        if not path.exists():
            key = JWK.generate(kty="EC", crv="P-256", kid=name)
            path.write_text(json.dumps(key.export_private(as_dict=True), indent=2) + "\n", encoding="utf-8")
            created.append(name)
    return created


def private_key(name: str, directory: Path = KEYS_DIR) -> JWK:
    return JWK(**json.loads((directory / f"{name}.json").read_text(encoding="utf-8")))


def public_jwk(name: str, directory: Path = KEYS_DIR) -> dict:
    return private_key(name, directory).export_public(as_dict=True)


def public_jwks() -> dict:
    """What the gateway serves at /.well-known/jwks.json: Valio's public key only."""
    return {"keys": [public_jwk("merchant")]}


def sign(payload: dict, key: JWK) -> str:
    """A compact ES256 JWT, with the key id in the header so a verifier can pick the key from a JWKS."""
    jws = JWS(json.dumps(payload).encode("utf-8"))
    jws.add_signature(key, alg="ES256", protected=json.dumps({"alg": "ES256", "typ": "JWT", "kid": key.get("kid")}))
    return jws.serialize(compact=True)


def verify(token: str, jwks: dict) -> dict:
    """Check an ES256 JWT against the key its header names in `jwks`. Returns the payload or raises TrustError."""
    try:
        header = json.loads(b64url_decode(token.split(".")[0]))
    except ValueError as e:
        raise TrustError("not a JWT") from e
    if not isinstance(header, dict):
        raise TrustError("malformed JWT header")
    keys = [k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")]
    if header.get("alg") != "ES256" or len(keys) != 1:
        raise TrustError(f"no single ES256 key for kid {header.get('kid')!r}")
    jws = JWS()
    try:
        jws.deserialize(token)
        jws.verify(JWK(**keys[0]), alg="ES256")
        return json.loads(jws.payload)
    except Exception as e:  # jwcrypto raises several types for a bad token or signature
        raise TrustError(f"bad signature ({type(e).__name__})") from e
