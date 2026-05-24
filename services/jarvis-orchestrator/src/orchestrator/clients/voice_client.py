"""Client gRPC pour communiquer avec jarvis-voice (service Rust).

Usage :

    from orchestrator.clients.voice_client import ping_voice
    resp = ping_voice(client_id="orchestrator-test")
    print(resp)
"""

from __future__ import annotations

from dataclasses import dataclass

import grpc

from orchestrator.proto_gen import voice_pb2, voice_pb2_grpc


DEFAULT_VOICE_ADDRESS = "127.0.0.1:50051"


@dataclass
class PingResult:
    """Résultat d'un appel Ping vers jarvis-voice."""

    ok: bool
    message: str
    version: str


def ping_voice(
    *,
    client_id: str = "orchestrator",
    address: str = DEFAULT_VOICE_ADDRESS,
    timeout_s: float = 5.0,
) -> PingResult:
    """Ping le service jarvis-voice et retourne sa réponse.

    Args:
        client_id: identifiant du client (loggé côté serveur).
        address: adresse host:port du serveur gRPC voice. Par défaut 127.0.0.1:50051.
        timeout_s: timeout en secondes.

    Returns:
        PingResult avec ok=True si la réponse a un status code OK.

    Raises:
        grpc.RpcError: si le service est inaccessible ou répond une erreur.
    """
    with grpc.insecure_channel(address) as channel:
        stub = voice_pb2_grpc.VoiceServiceStub(channel)
        request = voice_pb2.PingRequest(client_id=client_id)
        response = stub.Ping(request, timeout=timeout_s)

        status = response.status
        # Code 1 = OK (cf proto/common.proto Status.Code.OK)
        is_ok = status.code == 1

        return PingResult(
            ok=is_ok,
            message=status.message,
            version=response.version,
        )


def main() -> int:
    """Entry point CLI pour tester rapidement le ping vers jarvis-voice.

    Usage : python -m orchestrator.clients.voice_client
    """
    import sys

    try:
        result = ping_voice(client_id="cli-test")
    except grpc.RpcError as exc:
        print(f"❌ Erreur gRPC : {exc.code().name} — {exc.details()}", file=sys.stderr)
        print(f"   Vérifie que jarvis-voice tourne sur {DEFAULT_VOICE_ADDRESS}", file=sys.stderr)
        print(f"   (cargo run -p jarvis-voice dans un autre terminal)", file=sys.stderr)
        return 2

    status_icon = "✅" if result.ok else "❌"
    print(f"{status_icon} Ping/Pong avec jarvis-voice :")
    print(f"   message  : {result.message}")
    print(f"   version  : {result.version}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
