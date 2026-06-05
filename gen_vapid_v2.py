import base64
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

def generate_vapid_keys():
    # Generate a private key for use with ECDSA
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # Get private key in bytes
    private_bytes = private_key.private_numbers().private_value.to_bytes(32, 'big')
    # Get public key in uncompressed bytes (0x04 prefix)
    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )

    private_b64 = base64.urlsafe_b64encode(private_bytes).decode('utf-8').strip("=")
    public_b64 = base64.urlsafe_b64encode(public_bytes).decode('utf-8').strip("=")

    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print(f"VAPID_PRIVATE_KEY={private_b64}")

if __name__ == "__main__":
    generate_vapid_keys()
